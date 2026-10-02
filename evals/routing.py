#!/usr/bin/env python3
"""Routing accuracy: does a situation reach the right skill, and the right part of it?

A transparent lexical stand-in for an agent reading skill names and descriptions:
TF-IDF cosine over name + description (stdlib only). It is NOT a language model. It
measures how distinctive and well-covered the descriptions are; a real agent can
only do better at reading them, not at finding words that are absent.

  python3 evals/routing.py                 # dev set, old (v0.5) vs new layout
  python3 evals/routing.py --held-out      # the frozen set: run once, never tune on it
  python3 evals/routing.py --misses        # show wrong answers
"""
import argparse, json, math, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
STOP = set("a an the to of and or for in on at by with from is are was be it this that these those as into when use "
           "you your we our i my me can do does should how what which who why not no so if then than there their".split())

# v0.5 skill -> (v0.6 skill, reference file or None)
MOVED = {'shape': ('design', 'shape'), 'blueprint': ('design', 'blueprint'),
         'sandbox': ('build', 'sandbox'), 'prove-it': ('build', 'prove-it'), 'build': ('build', 'build'),
         'log-trace': ('debug', 'log-trace'), 'log-fetch': ('debug', 'log-fetch'), 'hunt': ('debug', 'hunt'),
         'trace-back': ('debug', 'trace-back'), 'threat-check': ('review', 'threat-check'),
         'second-look': ('review', 'second-look'), 'weigh-in': ('review', 'weigh-in'),
         'vibe-check': ('ship', 'vibe-check'), 'receipts': ('ship', 'receipts'), 'land': ('ship', 'land'),
         'preflight': ('ship', 'preflight'), 'ship': ('ship', 'deploy'),
         'observe': ('observe', 'observe'), 'slo': ('observe', 'slo')}


def stem(w):
    for suf in ('ings', 'ing', 'ied', 'ies', 'ed', 'es', 's'):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def toks(text):
    return [stem(w) for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP and len(w) > 1]


class Index:
    def __init__(self, docs):
        self.ids = list(docs)
        self.tf = {i: self._tf(toks(t)) for i, t in docs.items()}
        df = {}
        for tf in self.tf.values():
            for w in tf:
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.vec = {i: self._vec(tf) for i, tf in self.tf.items()}

    @staticmethod
    def _tf(ts):
        tf = {}
        for w in ts:
            tf[w] = tf.get(w, 0) + 1
        return tf

    def _vec(self, tf):
        v = {w: (1 + math.log(c)) * self.idf.get(w, 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def rank(self, query):
        q = self._vec(self._tf(toks(query)))
        scored = [(sum(q.get(w, 0) * x for w, x in self.vec[i].items()), i) for i in self.ids]
        return [i for s, i in sorted(scored, key=lambda t: (-t[0], t[1]))]


def meta(path):
    t = pathlib.Path(path).read_text(encoding='utf-8')
    return re.search(r'^name:\s*(.+)$', t, re.M).group(1).strip(), re.search(r'^description:\s*(.+)$', t, re.M).group(1).strip()


def load_new(root=ROOT):
    docs, parts = {}, {}
    for md in sorted(list(root.glob('skills/*/SKILL.md')) + list(root.glob('packs/*/skills/*/SKILL.md'))):
        n, d = meta(md)
        docs[n] = n.replace('-', ' ') + ' ' + d
        rows = re.findall(r'^\|\s*(.+?)\s*\|\s*`references/([\w.-]+)\.md`\s*\|$', md.read_text(encoding='utf-8'), re.M)
        if rows:
            parts[n] = Index({p: w for w, p in rows})
    return docs, parts


def load_old():
    d = json.loads((HERE / 'v05_descriptions.json').read_text())
    return {n: n.replace('-', ' ') + ' ' + t for n, t in d.items()}


def evaluate(cases, layout):
    if layout == 'old':
        idx, parts = Index(load_old()), {}
    else:
        docs, parts = load_new(); idx = Index(docs)
    top1 = top3 = e2e = pt = pk = 0; misses = []
    for text, o in cases:
        skill, part = MOVED.get(o, (o, None)) if layout == 'new' else (o, None)
        order = idx.rank(text)
        ok1 = order[0] == skill
        top1 += ok1; top3 += skill in order[:3]
        okp = True
        if layout == 'new' and skill in parts and part:
            okp = parts[skill].rank(text)[0] == part
            if ok1:
                pt += 1; pk += okp
        e2e += ok1 and okp
        if not (ok1 and okp):
            got = order[0] + ('' if ok1 else '')
            misses.append((o, text, order[0] if not ok1 else '%s -> wrong part %s' % (skill, parts[skill].rank(text)[0])))
    n = len(cases)
    return {'n': n, 'candidates': len(idx.ids), 'top1': 100 * top1 / n, 'top3': 100 * top3 / n, 'e2e': 100 * e2e / n,
            'chance': 100 / len(idx.ids), 'misses': misses,
            'part_given_skill': (100 * pk / pt) if pt else None, 'part_n': pt}


def legacy_recall():
    """Each v0.5 description's own situation, fed back as a query. Catches triggers lost in the merge."""
    old = json.loads((HERE / 'v05_descriptions.json').read_text())
    cases = []
    for n, d in old.items():
        t = re.sub(r'^Use when ', '', d); t = re.split(r'\. | - ', t)[0]
        cases.append((t, n))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--held-out', action='store_true'); ap.add_argument('--misses', action='store_true')
    a = ap.parse_args()
    data = json.loads((HERE / 'routing_cases.json').read_text())
    sets = [('held-out' if a.held_out else 'dev', data['held_out' if a.held_out else 'dev']), ('legacy triggers', legacy_recall())]
    print('%-16s %-18s %5s  %6s %6s %12s %10s %8s' % ('set', 'layout', 'skills', 'top-1', 'top-3', 'skill+part', 'part|skill', 'chance'))
    for name, cases in sets:
        for layout, label in (('old', 'v0.5 (41 skills)'), ('new', 'v0.6 (14+14)')):
            r = evaluate(cases, layout)
            pg = '%9.0f%%' % r['part_given_skill'] if r['part_given_skill'] is not None else '%10s' % '-'
            print('%-16s %-18s %5d  %5.0f%% %5.0f%% %11.0f%% %s %7.1f%%' % (name, label, r['candidates'], r['top1'], r['top3'], r['e2e'], pg, r['chance']))
            if a.misses and layout == 'new':
                for o, text, got in r['misses']:
                    print('      miss  %-12s -> %-22s %s' % (o, got, text[:70]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
