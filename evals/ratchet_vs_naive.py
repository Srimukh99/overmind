"""Seven scripted iterations (four typical agent mistakes, three honest steps) through a naive
"failing count did not rise" gate and through ratchet. Needs pytest. Run: python3 evals/ratchet_vs_naive.py"""
import os, re, shutil, subprocess, sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _eval_git as EG  # noqa: E402

if not EG.require('pytest', 'ratchet vs naive'):
    sys.exit(0)

RUBRIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix='rubric-eval-')
R = os.path.join(RUBRIC, 'skills', 'ratchet', 'scripts', 'ratchet.py')
D = os.path.join(WORK, 'shop')
shutil.rmtree(D, ignore_errors=True)
def w(rel, text):
    p = os.path.join(D, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)
def run(*a):
    p = subprocess.run([sys.executable, R, '--repo', D] + list(a), capture_output=True, text=True); return p.returncode, p.stdout + p.stderr
def g(*a): EG.git(EG.IDENT + list(a), cwd=D)

PRICING = '''def total(items):
    return sum(items)


def apply_coupon(cents, code):
    if code == "SAVE10":
        return cents - cents * 10 // 100
    raise ValueError("bad coupon")
'''
w('pyproject.toml', '[tool.pytest.ini_options]\npythonpath = ["src"]\n')
w('src/cart/__init__.py', ''); w('src/cart/pricing.py', PRICING)
w('src/billing/__init__.py', '')
w('src/billing/invoice.py', 'def line(cents):\n    return "$%d.%02d" % divmod(cents, 100)\n')
w('tests/test_pricing.py', '''import pytest
from cart.pricing import total, apply_coupon
def test_total(): assert total([100, 250]) == 350
def test_save10(): assert apply_coupon(1000, "SAVE10") == 900
def test_bad_coupon():
    with pytest.raises(ValueError): apply_coupon(1000, "NOPE")
''')
w('tests/test_invoice.py', 'from billing.invoice import line\ndef test_line(): assert line(1234) == "$12.34"\n')
g('init', '-q'); g('add', '-A'); g('commit', '-qm', 'base')
# prove-it: the agent writes the acceptance tests first (uncommitted, failing)
w('tests/test_stacking.py', '''from cart.pricing import apply_coupon
def test_freeship(): assert apply_coupon(1000, "FREESHIP") == 500
def test_freeship_floors_at_zero(): assert apply_coupon(300, "FREESHIP") == 0
def test_stack_percent_first():
    from cart.pricing import apply_coupons
    assert apply_coupons(1000, ["FREESHIP", "SAVE10"]) == 400
''')

FREESHIP = '''    if code == "FREESHIP":
        return max(cents - 500, 0)
'''
GOOD1 = PRICING.replace('    raise ValueError', FREESHIP + '    raise ValueError')
ITERS = [
 ('regression: works, but unknown codes no longer raise', {'src/cart/pricing.py':
    PRICING.replace('    raise ValueError("bad coupon")', FREESHIP + '    return cents')}),
 ('drift: works, plus an unasked invoice "cleanup"', {'src/cart/pricing.py': GOOD1,
    'src/billing/invoice.py': 'def line(cents):\n    return f"${cents / 100:.2f}"\n'}),
 ('API break: apply_coupon now takes a list', {'src/cart/pricing.py': GOOD1.replace('def apply_coupon(cents, code):',
    'def apply_coupon(cents, codes):\n    code = codes[0] if isinstance(codes, list) else codes')}),
 ('goalpost: wrong order, so the target test is edited', {'src/cart/pricing.py': GOOD1 + '''

def apply_coupons(cents, codes):
    for c in codes:
        cents = apply_coupon(cents, c)
    return cents
''', 'tests/test_stacking.py': open(os.path.join(D, 'tests/test_stacking.py')).read().replace('== 400', '== 450')}),
 ('honest partial: FREESHIP only', {'src/cart/pricing.py': GOOD1}),
 ('no-op: comment tweak', {'src/cart/pricing.py': GOOD1.replace('def total', '# totals\ndef total')}),
 ('honest finish: stacking, percent first', {'src/cart/pricing.py': GOOD1 + '''

def apply_coupons(cents, codes):
    for c in sorted(codes, key=lambda c: c != "SAVE10"):
        cents = apply_coupon(cents, c)
    return cents
'''}),
]

rc, out = run('start', '--goal', 'Add a FREESHIP coupon (500 off, floor 0) and stacking with percent coupons applied first',
              '--scope', 'src/cart/**',
              '--target', 'tests/test_stacking.py::test_freeship',
              '--target', 'tests/test_stacking.py::test_freeship_floors_at_zero',
              '--target', 'tests/test_stacking.py::test_stack_percent_first')
print(out)

def failing_count():
    p = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--continue-on-collection-errors'], cwd=D, capture_output=True, text=True)
    m = re.search(r'(\d+) failed', p.stdout); e = re.search(r'(\d+) errors?\b', p.stdout)
    return (int(m.group(1)) if m else 0) + (int(e.group(1)) if e else 0)

naive_floor = failing_count()
rows = []
for label, files in ITERS:
    for rel, text in files.items():
        w(rel, text)
    f = failing_count()
    naive = 'ACCEPT' if f <= naive_floor else 'REJECT'
    rc, out = run('check')
    verdict = re.search(r'ratchet iter \d+: (\w+)', out).group(1)
    why = [l.strip() for l in out.splitlines() if re.match(r'\s+(regression|api|drift|tamper|frozen-test|quality|gained)\s', l)]
    print('--- %s' % label); print(out.rstrip())
    if verdict in ('REJECT', 'STALL'):
        before = EG.git(['status', '--porcelain'], cwd=D, check=False).stdout
        run('revert', '--clean')
        floor_ck = re.search(r'"checkpoint": "(\w+)"', open(os.path.join(D, '.rubric/ratchet/floor.json')).read()).group(1)
        diff = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, "%s"); import ratchet as r; print(len(r.diff_vs("%s", "%s", ["--name-only"]).split()))' % (os.path.dirname(R), D, floor_ck)], capture_output=True, text=True).stdout.strip()
        restored = diff == '0'
    else:
        restored = None
        naive_floor = min(naive_floor, f)
    if naive == 'ACCEPT':
        naive_floor = min(naive_floor, f)
    rows.append((label, f, naive, verdict, restored))

print('\n%-50s %-8s %-8s %-8s %s' % ('iteration', 'failing', 'naive', 'ratchet', 'revert exact'))
for label, f, naive, verdict, restored in rows:
    print('%-50s %-8s %-8s %-8s %s' % (label, f, naive, verdict, '' if restored is None else restored))
