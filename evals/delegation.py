"""Delegation eval: one feature split across workers, three ways of delegating it.

Five scripted workers build a checkout (subtotal, tax, shipping, receipt). Four make the
mistakes delegated agents typically make; one is honest:

  pricing   honest
  tax       correct tax, but also "tidies" a shared helper it was not given (scope wander)
  shipping  wrong rule for heavy parcels, reports "done" anyway (false claim)
  receipt   wrong format, edits its own contract test so it passes (goalpost)
  helper    asked to "clean up", rewrites the same file as pricing (overlapping work)

  trust     lead merges everything workers report as done
  old       the v0.6 delegate rules: merge one result at a time, run the suite after each, revert failures
  team      contract-first: plan check, worktree and ratchet per worker, verify, integrate in waves

Truth is measured with the ORIGINAL contract tests, whatever the workers did to theirs.
Workers are scripted, so this tests the process, not how real agents behave.
Run: python3 evals/delegation.py   (needs pytest)
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _eval_git as EG  # noqa: E402

RUBRIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAM = os.path.join(RUBRIC, 'skills', 'delegate', 'scripts', 'team.py')
sys.path.insert(0, os.path.join(RUBRIC, 'skills', 'ratchet', 'scripts'))
import ratchet as R  # noqa: E402

WORK = tempfile.mkdtemp(prefix='rubric-deleg-')

BASE = {
    'pyproject.toml': '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
    'src/shop/__init__.py': '',
    'src/shop/models.py': 'from dataclasses import dataclass\n\n\n@dataclass\nclass Order:\n    items: list\n    country: str = "US"\n    weight_kg: float = 0.0\n',
    'src/shop/util.py': 'def round_cents(x):\n    return int(round(x))\n',
    'src/shop/pricing.py': 'def subtotal(order):\n    raise NotImplementedError\n',
    'src/shop/tax.py': 'def tax(order, subtotal):\n    raise NotImplementedError\n',
    'src/shop/shipping.py': 'def shipping(order):\n    raise NotImplementedError\n',
    'src/shop/receipt.py': 'def receipt(subtotal, tax, shipping):\n    raise NotImplementedError\n',
    'tests/test_util.py': 'from shop.util import round_cents\n\n\ndef test_round_cents():\n    assert round_cents(2.6) == 3 and round_cents(2.4) == 2\n',
}
CONTRACT = {
    'tests/contract/test_pricing.py': 'from shop.models import Order\nfrom shop.pricing import subtotal\n\n\ndef test_subtotal():\n    assert subtotal(Order([1000, 250])) == 1250\n\n\ndef test_subtotal_empty():\n    assert subtotal(Order([])) == 0\n',
    'tests/contract/test_tax.py': 'from shop.models import Order\nfrom shop.tax import tax\n\n\ndef test_vat_de():\n    assert tax(Order([1000], country="DE"), 1005) == 191\n\n\ndef test_no_tax_us():\n    assert tax(Order([1000]), 1000) == 0\n',
    'tests/contract/test_shipping.py': 'from shop.models import Order\nfrom shop.shipping import shipping\n\n\ndef test_light():\n    assert shipping(Order([100], weight_kg=1)) == 500\n\n\ndef test_heavy():\n    assert shipping(Order([100], weight_kg=12)) == 2000\n',
    'tests/contract/test_receipt.py': 'from shop.receipt import receipt\n\n\ndef test_receipt_format():\n    assert receipt(1250, 0, 500) == "subtotal 12.50 | tax 0.00 | shipping 5.00 | total 17.50"\n',
}
TAX = 'from shop.util import round_cents\n\nRATES = {"DE": 0.19, "FR": 0.20}\n\n\ndef tax(order, subtotal):\n    return round_cents(subtotal * RATES.get(order.country, 0))\n'
WAVE1 = {
    'pricing': {'src/shop/pricing.py': 'def subtotal(order):\n    return sum(order.items)\n'},
    'tax': {'src/shop/tax.py': TAX, 'src/shop/util.py': 'def round_cents(x):\n    return int(x)  # faster\n'},
    'shipping': {'src/shop/shipping.py': 'def shipping(order):\n    return 500 if order.weight_kg <= 10 else 1500\n'},
    'receipt': {'src/shop/receipt.py': 'def receipt(subtotal, tax, shipping):\n    return "subtotal %.2f | tax %.2f | shipping %.2f" % (subtotal / 100, tax / 100, shipping / 100)\n',
                'tests/contract/test_receipt.py': CONTRACT['tests/contract/test_receipt.py'].replace(' | total 17.50', '')},
    'helper': {'src/shop/pricing.py': '"""Pricing."""\n\n\ndef subtotal(order):\n    raise NotImplementedError\n'},
}
WAVE2 = {  # honest redo of whatever was sent back
    'tax': {'src/shop/tax.py': TAX},
    'shipping': {'src/shop/shipping.py': 'def shipping(order):\n    return 500 if order.weight_kg <= 10 else 2000\n'},
    'receipt': {'src/shop/receipt.py': 'def receipt(subtotal, tax, shipping):\n    total = subtotal + tax + shipping\n    return "subtotal %.2f | tax %.2f | shipping %.2f | total %.2f" % (subtotal / 100, tax / 100, shipping / 100, total / 100)\n'},
}
OWNS = {'pricing': ['src/shop/pricing.py'], 'tax': ['src/shop/tax.py'], 'shipping': ['src/shop/shipping.py'],
        'receipt': ['src/shop/receipt.py'], 'helper': ['src/shop/**']}
TARGETS = {'pricing': ['tests/contract/test_pricing.py::test_subtotal', 'tests/contract/test_pricing.py::test_subtotal_empty'],
           'tax': ['tests/contract/test_tax.py::test_vat_de', 'tests/contract/test_tax.py::test_no_tax_us'],
           'shipping': ['tests/contract/test_shipping.py::test_light', 'tests/contract/test_shipping.py::test_heavy'],
           'receipt': ['tests/contract/test_receipt.py::test_receipt_format'], 'helper': []}
ISSUES = [('tax', 'edits a shared file it was not given'), ('shipping', 'says done, heavy-parcel rule wrong'),
          ('receipt', 'edits its own contract test to pass'), ('helper', 'overwrites the same file as pricing')]


def write(root, files):
    for rel, text in files.items():
        p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as fh:
            fh.write(text)


def fresh(name):
    d = os.path.join(WORK, name); shutil.rmtree(d, ignore_errors=True)
    write(d, BASE); write(d, CONTRACT); return d


def results(root):
    shutil.rmtree(os.path.join(root, '.rubric', 'ratchet'), ignore_errors=True)
    return R.run_tests(root, R.detect_test_cmd(root))[1]


def passing(res, tid):
    return any(R.target_matches(tid, k) and s == 'pass' for k, s in res.items())


def truth(root):
    """Score the final code against the ORIGINAL contract and the original helper test."""
    probe = os.path.join(WORK, 'truth'); shutil.rmtree(probe, ignore_errors=True)
    shutil.copytree(root, probe, ignore=shutil.ignore_patterns('.git', '.rubric', '__pycache__', '.pytest_cache'))
    write(probe, CONTRACT); write(probe, {'tests/test_util.py': BASE['tests/test_util.py']})
    res = results(probe)
    ids = [t for v in TARGETS.values() for t in v] + ['tests/test_util.py::test_round_cents']
    return sum(passing(res, t) for t in ids), len(ids)


def bad_in(root):
    """Which of the four bad changes are present in the final code."""
    rd = lambda rel: open(os.path.join(root, rel)).read()
    return [w for w, present in (
        ('tax', 'int(x)' in rd('src/shop/util.py')),
        ('shipping', 'else 1500' in rd('src/shop/shipping.py')),
        ('receipt', rd('tests/contract/test_receipt.py') != CONTRACT['tests/contract/test_receipt.py']),
        ('helper', '"""Pricing."""' in rd('src/shop/pricing.py'))) if present]


# ------------------------------------------------------------------ trust the claims
def run_trust():
    main = fresh('trust')
    for w in ('pricing', 'tax', 'shipping', 'receipt', 'helper'):
        write(main, WAVE1[w])                                    # last write wins
    return {'caught': {}, 'main': main}


# ------------------------------------------------------------------ old delegate rules
def run_old():
    main = fresh('old'); caught = {}; runs = 0
    floor = {k for k, s in results(main).items() if s == 'pass'}; runs += 1
    def attempt(w, files):
        nonlocal floor, runs
        saved = {rel: open(os.path.join(main, rel)).read() if os.path.exists(os.path.join(main, rel)) else None for rel in files}
        write(main, files); res = results(main); runs += 1
        broke = [k for k in floor if res.get(k) != 'pass']
        own = [t for t in TARGETS[w] if not passing(res, t)]
        if broke or own:
            for rel, text in saved.items():
                if text is None:
                    os.remove(os.path.join(main, rel))
                else:
                    write(main, {rel: text})
            return 'reverted (%s)' % ('broke ' + broke[0].split('::')[-1] if broke else 'own test failed')
        floor = {k for k, s in res.items() if s == 'pass'}
        return 'kept'
    for w in ('pricing', 'tax', 'shipping', 'receipt', 'helper'):
        caught[w] = attempt(w, WAVE1[w])
    for w, files in WAVE2.items():                               # rework only what was reverted
        if caught[w].startswith('reverted'):
            attempt(w, files)
    return {'caught': caught, 'main': main, 'suite_runs': runs}


# ------------------------------------------------------------------ contract-first team
def team(root, *args):
    p = subprocess.run([sys.executable, TEAM, '--repo', root] + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_team(log):
    main = fresh('team')
    for c in (['init', '-q'], ['add', '-A'], ['commit', '-qm', 'base with contract']):
        EG.git(EG.IDENT + c, cwd=main)
    timings = {}
    t0 = time.time()
    team(main, 'init', '--goal', 'Checkout totals: subtotal, tax, shipping, receipt',
         '--contract', 'src/shop/models.py', '--contract', 'tests/contract')
    for w in ('pricing', 'tax', 'shipping', 'receipt', 'helper'):
        args = ['add', w, '--task', 'implement %s' % w] + sum([['--owns', g] for g in OWNS[w]], []) + sum([['--target', t] for t in TARGETS[w]], [])
        team(main, *args)
    rc, out = team(main, 'check'); log.append(('plan check', out))
    caught = {'helper': 'blocked at plan check' if rc != 0 and 'helper' in out else 'not caught'}
    team(main, 'drop', 'helper')
    rc, out = team(main, 'check'); log.append(('plan check after dropping helper', out))
    timings['plan'] = time.time() - t0
    rc, out = team(main, 'brief', 'shipping'); log.append(('brief sent to the shipping worker', out))

    def work(wave, names):
        plan = json.load(open(os.path.join(main, '.rubric', 'team', 'plan.json')))
        for w in names:
            wt = plan['workers'][w]['worktree']
            write(wt, wave[w]); write(wt, {'.rubric/result.json': json.dumps({'status': 'done', 'summary': 'implemented ' + w})})

    t0 = time.time(); rc, out = team(main, 'spawn', '--no-fast'); timings['spawn'] = time.time() - t0; log.append(('spawn wave 1', out))
    work(WAVE1, ['pricing', 'tax', 'shipping', 'receipt'])
    t0 = time.time(); rc, out = team(main, 'verify'); timings['verify'] = time.time() - t0; log.append(('verify wave 1', out))
    for w in ('tax', 'shipping', 'receipt'):
        line = next((l for l in out.splitlines() if l.startswith(w + ' ')), '')
        verdict = line.split()[2] if len(line.split()) > 2 else '?'
        kinds = [k for k in ('regression', 'drift', 'frozen-test', 'tamper', 'api') if k + ':' in line]
        caught[w] = verdict + (': ' + ' + '.join(kinds) if kinds else ' (targets not done)') + (', false claim flagged' if 'FALSE CLAIM' in line else '')
    t0 = time.time(); rc, out = team(main, 'integrate', '--apply'); timings['integrate'] = time.time() - t0; log.append(('integrate wave 1', out))
    # wave 2: the three rejected workers start over from the new base, honestly
    rc, out = team(main, 'spawn', '--fresh', '--no-fast', 'tax', 'shipping', 'receipt'); log.append(('spawn wave 2', out))
    work(WAVE2, ['tax', 'shipping', 'receipt'])
    rc, out = team(main, 'verify'); log.append(('verify wave 2', out))
    rc, out = team(main, 'integrate', '--apply'); log.append(('integrate wave 2', out))
    team(main, 'clean', '--all')
    return {'caught': caught, 'main': main, 'timings': timings}


def main():
    log = []
    trust, old, tm = run_trust(), run_old(), run_team(log)
    if '-v' in sys.argv:
        for title, out in log:
            print('--- %s\n%s' % (title, out.rstrip()))
        print()
    print('%-9s %-38s %-8s %-28s %s' % ('worker', 'mistake', 'trust', 'old delegate rules', 'contract-first team'))
    for w, what in ISSUES:
        print('%-9s %-38s %-8s %-28s %s' % (w, what, 'merged', old['caught'].get(w, '')[:28], tm['caught'].get(w, '')))
    print()
    print('%-34s %-18s %-18s %s' % ('final result', 'trust', 'old', 'team'))
    tr = [truth(x['main']) for x in (trust, old, tm)]
    print('%-34s %-18s %-18s %s' % ('original contract tests passing', '%d of %d' % tr[0], '%d of %d' % tr[1], '%d of %d' % tr[2]))
    bad = [bad_in(x['main']) for x in (trust, old, tm)]
    print('%-34s %-18s %-18s %s' % ('bad changes that reached main', '%d %s' % (len(bad[0]), ','.join(bad[0])), '%d %s' % (len(bad[1]), ','.join(bad[1])), '%d %s' % (len(bad[2]), ','.join(bad[2]))))
    print('%-34s %-18s %-18s %s' % ('workers editing in parallel safely', 'no', 'no (one at a time)', 'yes (own worktree)'))
    t = tm['timings']
    print('\nteam tooling time: plan %.1fs, spawn %.1fs, verify %.1fs, integrate %.1fs (4 workers)' % (t['plan'], t['spawn'], t['verify'], t['integrate']))
    print('old delegate ran the full suite %d times, one after another' % old['suite_runs'])
    shutil.rmtree(WORK, ignore_errors=True)
    for d in os.listdir(os.path.dirname(WORK)):
        if d.startswith('team.rubric-team'):
            shutil.rmtree(os.path.join(os.path.dirname(WORK), d), ignore_errors=True)


if __name__ == '__main__':
    if not EG.require('pytest', 'delegation'):
        sys.exit(0)
    main()
