#!/usr/bin/env python3
"""Built-in mutation tester for Python, limited to changed functions.

Injects one small bug at a time (flip an operator or comparison, nudge a
constant, return None, invert a condition) and reruns the tests. A surviving
mutant is a bug no test would catch. Stdlib only; restores files afterwards.
"""
import ast, copy, re, subprocess

SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
        ast.Div: ast.Mult, ast.Mod: ast.FloorDiv,
        ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
        ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.And: ast.Or, ast.Or: ast.And}
NAMES = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.FloorDiv: '//', ast.Div: '/', ast.Mod: '%',
         ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=', ast.Eq: '==', ast.NotEq: '!=',
         ast.In: 'in', ast.NotIn: 'not in', ast.Is: 'is', ast.IsNot: 'is not', ast.And: 'and', ast.Or: 'or'}


def changed_ranges(diff_text):
    """Line ranges (new file) from a unified=0 diff."""
    out = []
    for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', diff_text, re.M):
        start, n = int(m.group(1)), int(m.group(2) or 1)
        if n:
            out.append((start, start + n - 1))
    return out


def functions_touching(tree, ranges):
    if ranges is None:
        return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    hit = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(n, 'end_lineno', n.lineno)
            if any(a <= end and n.lineno <= b for a, b in ranges):
                hit.append(n)
    return hit


def sites(tree, ranges=None):
    funcs = functions_touching(tree, ranges)
    spans = [(f.lineno, getattr(f, 'end_lineno', f.lineno)) for f in funcs]
    out = []
    for n in ast.walk(tree):
        ln = getattr(n, 'lineno', None)
        if ln is None or not any(a <= ln <= b for a, b in spans):
            continue
        if isinstance(n, (ast.BinOp, ast.BoolOp)) and type(n.op) in SWAP:
            out.append(('op', 0, n))
        elif isinstance(n, ast.Compare):
            for i, o in enumerate(n.ops):
                if type(o) in SWAP:
                    out.append(('cmp', i, n))
        elif isinstance(n, ast.Constant) and type(n.value) is int and not isinstance(n.value, bool):
            out.append(('int', 0, n))
        elif isinstance(n, ast.Return) and n.value is not None and not (isinstance(n.value, ast.Constant) and n.value.value is None):
            out.append(('ret', 0, n))
        elif isinstance(n, ast.If):
            out.append(('if', 0, n))
    return out


def apply(tree, k, ranges=None):
    t = copy.deepcopy(tree)
    kind, i, n = sites(t, ranges)[k]
    if kind == 'op':
        desc = '%s -> %s' % (NAMES[type(n.op)], NAMES[SWAP[type(n.op)]]); n.op = SWAP[type(n.op)]()
    elif kind == 'cmp':
        desc = '%s -> %s' % (NAMES[type(n.ops[i])], NAMES[SWAP[type(n.ops[i])]]); n.ops[i] = SWAP[type(n.ops[i])]()
    elif kind == 'int':
        desc = '%d -> %d' % (n.value, n.value + 1); n.value += 1
    elif kind == 'ret':
        desc = 'return None'; n.value = ast.Constant(None)
    else:
        desc = 'condition inverted'; n.test = ast.UnaryOp(op=ast.Not(), operand=n.test)
    return t, n.lineno, desc


def run(path, test_cmd, cwd, ranges=None, max_mutants=60, timeout=60):
    """Returns dict(total, tested, killed, survivors=[(line, desc, source)])."""
    orig = open(path, encoding='utf-8').read()
    tree = ast.parse(orig)
    lines = orig.splitlines()
    n = len(sites(tree, ranges))
    picks = list(range(n)) if n <= max_mutants else [round(i * (n - 1) / (max_mutants - 1)) for i in range(max_mutants)]
    killed, survivors = 0, []
    try:
        for k in picks:
            t, ln, desc = apply(tree, k, ranges)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(ast.unparse(t))
            try:
                rc = subprocess.run(test_cmd, cwd=cwd, shell=True, capture_output=True, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = 124  # a hang is a detected change
            if rc != 0:
                killed += 1
            else:
                survivors.append((ln, desc, lines[ln - 1].strip() if 0 < ln <= len(lines) else ''))
    finally:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(orig)
    return {'total': n, 'tested': len(picks), 'killed': killed, 'survivors': survivors}
