#!/usr/bin/env python3
"""Guidance coverage: does a library's test-writing advice name the defect
classes that actually ship?

`code_quality.py` showed that nothing in either library's *tooling* separates a
thin implementation from a solid one - only the hidden acceptance suite does.
That makes it a guidance question, and this measures it.

The defect classes below are derived from the hidden suites in
`code_quality.py`, which are ground truth and must not be edited to change this
score. Tuning the taxonomy or the suites to make a library win is goalpost
moving; `tamper.py` exists because that is a real temptation.

What this measures: whether the guidance a library gives at the moment tests are
written *names* each class. That is necessary, not sufficient - naming a class
does not make an engineer check it. The metric is also gameable by listing
keywords, so every hit prints the line that matched. Read them before believing
the score.

Run: python3 evals/guidance_coverage.py [--lib NAME=PATH ...]
Stdlib only.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OVERMIND = os.path.dirname(HERE)
DEFAULT_SP = os.path.expanduser(
    '~/.claude/plugins/cache/claude-plugins-official/superpowers/6.4.1')

# Derived from code_quality.py's hidden suites. Frozen alongside them.
CLASSES = {
    'boundary': {
        'why': 'half-open vs closed, touching endpoints, off-by-one',
        'from': 'overlap: touching intervals must not overlap',
        # "mock boundaries" and "boundary contract" are about seams, not values.
        'rx': r'\boff.by.one\b|half.open|\binclusive\b|\bexclusive\b|'
              r'boundary (case|value|condition)s?\b|\btouching\b',
    },
    'empty': {
        'why': 'zero-length or empty input',
        'from': 'overlap: an empty interval never overlaps',
        'rx': r'\bempty (list|string|input|collection|array|set|dict|map|interval|range|slice)\b|'
              r'zero.length|\bempty case\b|'
              r'\bempty\b[^.]{0,48}\binput\b|\binput\b[^.]{0,48}\bempty\b',
    },
    'clamp': {
        'why': 'floors, ceilings, never-negative results',
        'from': 'discount: FREESHIP must not go below zero',
        'rx': r'\bclamp(s|ed|ing)?\b|\bfloors? (at|to)\b|never negative|below zero|'
              r'\bnegative (value|result|number|amount|quantity)s?\b',
    },
    'numeric_type': {
        'why': 'integer vs float, rounding direction, money as cents',
        'from': 'discount: money stays an int and rounds down',
        'rx': r'\brounding\b|\bround(s|ed)? (up|down|half|toward)|'
              r'integer (division|math|arithmetic|cents)|float(ing)?.point|'
              r'\bmoney\b.{0,40}\b(cents|integer|int)\b',
    },
    'partial_last': {
        'why': 'the last chunk is short',
        'from': 'pagination: a short final page',
        # "partial mock" is unrelated; require a chunk noun.
        'rx': r'\b(last|final|short) (page|chunk|batch|window|slice|group)\b|'
              r'partial (page|chunk|batch|slice)\b|\bremainder\b',
    },
    'out_of_range': {
        'why': 'input past the end of the data',
        'from': 'pagination: a page past the end is empty',
        'rx': r'out.of.(range|bounds)\b|past the end\b|beyond the (end|last|range)\b|'
              r'\bindex error\b|\boverflow\b',
    },
}

# Canonical classes NOT derived from code_quality.py's tasks, and NOT written
# against by either library's guidance. A robustness check: if a library only
# scores on the CORE classes, its coverage was fitted to this taxonomy rather
# than genuinely broad.
EXTENDED = {
    'null_none': {
        'why': 'None / null / nil flowing through',
        'rx': r'\bnull\b|\bNone\b|\bnil\b|\bnullable\b|\bmissing (field|key|value)s?\b',
    },
    'large_input': {
        'why': 'very large input, memory and limits',
        'rx': r'\blarge (input|file|list|payload|dataset|collection)s?\b|'
              r'\bhuge (input|file|list|payload|dataset|collection)s?\b|\bmemory limit|'
              r'\btoo (big|many) (items|rows|records|elements)\b',
    },
    'concurrency': {
        'why': 'races, double submit, atomicity',
        'rx': r'\brace (condition|s)?\b|\bconcurren(t|cy)\b|\batomic\b|\block(ing|s)?\b.{0,30}\b(test|order)|'
              r'\bdouble.(submit|click)\b|\bidempoten',
    },
    'locale': {
        'why': 'locale, collation, case folding',
        'rx': r'\blocale\b|\bcollation\b|\bcase.fold|\bi18n\b|\bcurrency symbol',
    },
}

# Where each library tells you how to write a test. Same role, both sides.
LIBS = {
    'overmind': [
        'skills/build/SKILL.md',
        'skills/build/references/prove-it.md',
    ],
    'superpowers': [
        'skills/test-driven-development/SKILL.md',
        'skills/test-driven-development/writing-good-tests.md',
    ],
}


# A line that names a class in order to exclude it is not guidance to check it.
# Writing "locale is out of scope" must not score as locale coverage.
EXCLUDES = re.compile(
    r'\bare not here\b|\bnot covered\b|\bout of scope\b|\bnot in scope\b|'
    r'\bbelongs? to\b|\bdo(es)? not (apply|belong)\b|\bexcept\b',
    re.I)


def scan(root, files, classes=None):
    """Return {class: (hit, 'file:line  matched text')}."""
    classes = classes or CLASSES
    found = {k: None for k in classes}
    for rel in files:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
        for i, line in enumerate(lines, 1):
            # Prose wraps, so an exclusion cue may sit on a neighbouring line.
            window = ' '.join(lines[max(0, i - 2):i + 1])
            for name, spec in classes.items():
                if found[name]:
                    continue
                if EXCLUDES.search(window):
                    continue
                m = re.search(spec['rx'], line, re.I)
                if m:
                    text = ' '.join(line.split())
                    if len(text) > 86:
                        text = text[:83] + '...'
                    found[name] = ('%s:%d' % (os.path.basename(rel), i), text)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(prog='guidance-coverage')
    ap.add_argument('--lib', action='append', default=[],
                    help='NAME=PATH, repeatable; defaults to overmind and superpowers')
    ap.add_argument('--quiet', action='store_true', help='scores only, no matched lines')
    a = ap.parse_args(argv)

    libs = {}
    for spec in a.lib:
        n, _, p = spec.partition('=')
        libs[n] = p
    if not libs:
        libs = {'overmind': OVERMIND, 'superpowers': DEFAULT_SP}

    results, ext_results = {}, {}
    for name, root in libs.items():
        if not os.path.isdir(root):
            print('%s: SKIPPED - not found at %s' % (name, root))
            continue
        results[name] = scan(root, LIBS.get(name, LIBS['overmind']))
        ext_results[name] = scan(root, LIBS.get(name, LIBS['overmind']), EXTENDED)

    if not results:
        print('no libraries to compare')
        return 0

    names = list(results)
    print('Defect classes derived from code_quality.py\'s hidden suites (frozen).')
    print('A hit means the guidance names the class, not that it enforces it.\n')
    width = max(len(c) for c in CLASSES) + 2
    header = 'defect class'.ljust(width) + ''.join(n.ljust(14) for n in names)
    print(header)
    print('-' * len(header))
    for c in CLASSES:
        row = c.ljust(width)
        for n in names:
            row += ('yes' if results[n][c] else 'no').ljust(14)
        print(row)
    print('-' * len(header))
    totals = {n: sum(1 for c in CLASSES if results[n][c]) for n in names}
    print('covered'.ljust(width) + ''.join(('%d/%d' % (totals[n], len(CLASSES))).ljust(14) for n in names))

    if not a.quiet:
        for n in names:
            print('\n--- %s, the line that matched each class ---' % n)
            for c in CLASSES:
                hit = results[n][c]
                if hit:
                    print('  %-14s %-28s %s' % (c, hit[0], hit[1]))
                else:
                    print('  %-14s %-28s %s' % (c, '(none)', CLASSES[c]['why']))

    print()
    print('Robustness check: classes NOT derived from those tasks, and not')
    print('written against by either library.\n')
    header2 = 'extended class'.ljust(width) + ''.join(n.ljust(14) for n in names)
    print(header2)
    print('-' * len(header2))
    for c in EXTENDED:
        row = c.ljust(width)
        for n in names:
            row += ('yes' if ext_results[n][c] else 'no').ljust(14)
        print(row)
    print('-' * len(header2))
    ext_totals = {n: sum(1 for c in EXTENDED if ext_results[n][c]) for n in names}
    print('covered'.ljust(width) + ''.join(('%d/%d' % (ext_totals[n], len(EXTENDED))).ljust(14) for n in names))

    best = max(totals, key=lambda n: totals[n])
    tie = list(totals.values()).count(totals[best]) > 1
    print()
    print('leader: %s' % ('tie at %d/%d' % (totals[best], len(CLASSES)) if tie
                          else '%s, %d/%d' % (best, totals[best], len(CLASSES))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
