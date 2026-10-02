#!/usr/bin/env python3
"""legal-traps: flag common legal mistakes in consumer apps. Read-only, stdlib.

Line rules fire on a matching line. Repo rules fire when a feature exists in
the repo but its required counterpart doesn't (uploads without a DMCA page).
Heuristic: catches the usual traps, not every case. Not legal advice.
"""
import argparse, json, os, re, sys

SKIP = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build',
        '.next', '.overmind', 'vendor', 'coverage', '.terraform',
        'tests', 'test', '__tests__', 'spec', 'fixtures', 'e2e', 'cypress'}  # tests don't ship
EXTS = {'.html', '.htm', '.css', '.scss', '.js', '.jsx', '.ts', '.tsx', '.vue',
        '.svelte', '.py', '.rb', '.php', '.go', '.java', '.kt', '.swift', '.mjml',
        '.hbs', '.ejs', '.erb', '.jinja', '.j2', '.liquid', '.md', '.mdx', '.txt'}
IGNORE = 'legal-traps: ignore'

# (id, level, regex, why, fix)
LINE_RULES = [
    ('remote-google-fonts', 'WARN', r'fonts\.(googleapis|gstatic)\.com',
     'sends visitor IPs to Google; EU courts have awarded damages', 'self-host the fonts'),
    ('session-replay', 'WARN',
     r'hotjar|fullstory|logrocket|clarity\.ms|mouseflow|smartlook|@sentry/replay|replayIntegration|sessionRecording',
     'session replay is a common wiretap-claim target', 'load after consent, mask inputs, disclose'),
    ('ad-pixel', 'WARN',
     r'connect\.facebook\.net|fbevents\.js|fbq\(|analytics\.tiktok\.com|ttq\.|snap\.licdn\.com|googleadservices|gtag\(.*AW-',
     'ad pixels drive wiretap, VPPA and health-privacy claims', 'consent first; never on health or video pages'),
    ('chat-widget', 'WARN', r'widget\.intercom\.io|js\.driftt\.com|static\.zdassets\.com|embed\.tawk\.to|crisp\.chat',
     'third-party chat has been framed as eavesdropping', 'disclose the vendor in the widget and policy'),
    ('prechecked-age', 'FAIL',
     r'(over|older than|at least)\s*1[3-8].{0,80}(checked|defaultChecked|default=true|:\s*true)|(checked|defaultChecked).{0,80}(over|at least)\s*1[3-8]',
     'pre-ticked age box is not an age screen', 'neutral date-of-birth screen'),
    ('raw-card-field', 'FAIL', r'name=["\']?(card_?number|cardNumber|cc_?num|cvv|cvc)["\']?',
     'card data on your own servers puts you in full PCI scope', 'use processor hosted fields'),
    ('drip-fee', 'WARN', r'(service|convenience|processing|booking|handling)[ _-]?fee',
     'mandatory fees must be in the first price shown', 'include fees in the displayed price'),
    ('vague-renew-button', 'WARN',
     r'(subscribe|start trial|continue|get started)[^\n]{0,40}(button|Button|onClick)',
     'renewal terms must sit next to the button with express consent',
     'state price, cadence and auto-renewal on or beside the button'),
    ('face-biometrics', 'WARN',
     r'face-api|face_recognition|IndexFaces|SearchFacesByImage|CompareFaces|FaceDetector|mediapipe.*face',
     'face geometry needs written consent under Illinois BIPA', 'consent before processing; retention policy'),
    ('sms-send', 'WARN', r'messages\.create\(|twilio|vonage|sns\.publish\(.*PhoneNumber|textbelt',
     'marketing texts need prior express written consent (TCPA)', 'store consent, honour STOP'),
    ('health-field', 'WARN',
     r'\b(diagnosis|medication|prescription|mrn|medical_record|insurance_member_id|blood_type|icd10)\b',
     'health data: BAA with every vendor, no pixels on these pages', 'see reg-phi'),
]

# repo rules: (id, level, feature regex, required regex, why, fix)
REPO_RULES = [
    ('uploads-no-dmca', 'WARN',
     r'type=["\']file["\']|multer|putObject|createPresignedPost|getSignedUrl|uploadthing|cloudinary|UploadFile',
     r'dmca|copyright agent|designated agent',
     'user uploads without a DMCA agent lose safe harbour', 'register an agent, publish a takedown page'),
    ('email-no-unsubscribe', 'FAIL',
     r'sendgrid|@sendgrid|resend\.emails|nodemailer|ses\.send|SendEmailCommand|postmark|mailgun|react-email',
     r'unsubscribe',
     'marketing email needs a working unsubscribe link', 'unsubscribe link + List-Unsubscribe headers'),
    ('email-no-address', 'WARN',
     r'sendgrid|resend\.emails|nodemailer|ses\.send|SendEmailCommand|postmark|mailgun|react-email',
     r'postal|mailing address|\b(suite|ste\.?|p\.?o\.? box|street|st\.|ave|avenue|road|rd\.)\b',
     'CAN-SPAM requires a physical postal address in marketing email', 'add it to the email footer'),
    ('subscription-no-cancel', 'FAIL',
     r'subscriptions\.create|mode:\s*["\']subscription|recurring|interval:\s*["\'](month|year)|auto[_-]?renew',
     r'billingPortal|billing_portal|cancel_at_period_end|subscriptions\.(cancel|del)|cancelSubscription|/cancel',
     'auto-renewal without online cancellation breaks California law', 'add self-serve online cancel'),
    ('signup-no-age', 'INFO',
     r'sign[_-]?up|register|createUser|create_user',
     r'birth|dob|date_of_birth|age[_-]?(gate|screen|check)|\bage\b',
     'signup never asks age; fine for adult products, not if kids might use it',
     'neutral age screen if the audience could include under-13s'),
    ('tracking-no-gpc', 'WARN',
     r'fbq\(|gtag\(|analytics\.tiktok|hotjar|segment\.(com|io)',
     r'globalPrivacyControl|Sec-GPC|do not sell',
     'trackers present but no Global Privacy Control handling', 'honour GPC; add Do Not Sell or Share'),
    ('accounts-no-delete', 'WARN',
     r'sign[_-]?up|createUser|create_user|register',
     r'delete[_ ]?account|deleteAccount|account[_-]?deletion|deleteUser',
     'app stores require in-app account deletion', 'add a delete-account flow'),
    ('no-privacy-policy', 'WARN',
     r'<input|<form|useForm|formik|email',
     r'privacy[_ -]?policy|/privacy',
     'collecting personal data with no privacy policy (CalOPPA)', 'publish and link a privacy policy'),
]

LINE_C = [(i, l, re.compile(p, re.I), w, f) for i, l, p, w, f in LINE_RULES]
REPO_C = [(i, l, re.compile(a, re.I), re.compile(b, re.I), w, f) for i, l, a, b, w, f in REPO_RULES]


def files(root):
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in SKIP]
        for f in fs:
            if os.path.splitext(f)[1].lower() in EXTS:
                yield os.path.join(d, f)


def scan(root):
    hits, feature, required = [], {}, set()
    for p in files(root):
        if os.path.abspath(p) == os.path.abspath(__file__):
            continue
        try:
            if os.path.getsize(p) > 1_000_000:
                continue
            text = open(p, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        rel = os.path.relpath(p, root)
        is_doc = rel.lower().endswith(('.md', '.mdx', '.txt'))
        for i, l, fr, rq, w, f in REPO_C:
            if rq.search(text):
                required.add(i)
            if not is_doc and i not in feature:
                m = fr.search(text)
                if m:
                    feature[i] = '%s:%d' % (rel, text[:m.start()].count('\n') + 1)
        if is_doc:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if IGNORE in line or len(line) > 2000:
                continue
            for i, l, rx, w, f in LINE_C:
                if rx.search(line):
                    hits.append({'rule': i, 'level': l, 'where': '%s:%d' % (rel, n), 'why': w, 'fix': f})
    for i, l, fr, rq, w, f in REPO_C:
        if i in feature and i not in required:
            hits.append({'rule': i, 'level': l, 'where': feature[i], 'why': w, 'fix': f})
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(prog='legal-traps')
    ap.add_argument('root', nargs='?', default='.')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--max', type=int, default=3, help='locations shown per rule')
    a = ap.parse_args(argv)
    hits = scan(a.root)
    if a.json:
        print(json.dumps(hits, indent=2)); return 1 if any(h['level'] == 'FAIL' for h in hits) else 0
    order = {'FAIL': 0, 'WARN': 1, 'INFO': 2}
    grouped = {}
    for h in hits:
        grouped.setdefault(h['rule'], []).append(h)
    counts = {k: sum(1 for h in hits if h['level'] == k) for k in order}
    print('legal-traps: %d FAIL, %d WARN, %d INFO  (not legal advice)' %
          (counts['FAIL'], counts['WARN'], counts['INFO']))
    for rule, hs in sorted(grouped.items(), key=lambda kv: (order[kv[1][0]['level']], kv[0])):
        h = hs[0]
        locs = ', '.join(x['where'] for x in hs[:a.max]) + (' +%d' % (len(hs) - a.max) if len(hs) > a.max else '')
        print('%-4s %-22s %s' % (h['level'], rule, locs))
        print('     why: %s | fix: %s' % (h['why'], h['fix']))
    return 1 if counts['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
