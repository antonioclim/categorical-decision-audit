"""Independent finite-domain reference for the phase-2 weighted audit.

No production scorer, row builder, scenario constructor or checker is imported.
The input lists retain rank. This module certifies the coefficient table using
rational logarithm enclosures and computes every requested score directly.
"""
from fractions import Fraction
from functools import lru_cache
from itertools import product
import random

GAINS = {'binary': (0, 0, 1, 1), 'graded': (0, 1, 2, 3)}


@lru_cache(None)
def log_interval(n, terms=256):
    z = Fraction(n - 1, n + 1)
    z2 = z * z
    power, partial = z, Fraction(0)
    for j in range(terms):
        partial += power / (2 * j + 1)
        power *= z2
    lower = 2 * partial
    remainder_bound = 2 * power / ((2 * terms + 1) * (1 - z2))
    return lower, lower + remainder_bound


@lru_cache(None)
def table(scale):
    """Exact floor coefficients, established without production tables."""
    ln2_low, ln2_high = log_interval(2)
    rows = []
    for rank in range(1, 11):
        n = rank + 1
        values = [0]
        for gain in range(1, 4):
            if n & (n - 1) == 0:
                exact = Fraction(gain * scale, n.bit_length() - 1)
                values.append(exact.numerator // exact.denominator)
            else:
                low, high = log_interval(n)
                lo = gain * scale * ln2_low / high
                hi = gain * scale * ln2_high / low
                flo, fhi = lo.numerator // lo.denominator, hi.numerator // hi.denominator
                if flo != fhi:
                    raise AssertionError('Rational interval does not establish floor')
                values.append(flo)
        rows.append(tuple(values))
    return tuple(rows)


def coefficients(metric, scale):
    if metric == 'flat_gain_v1':
        assert scale == 1
        return tuple((0, 1, 2, 3) for _ in range(10))
    assert metric == 'quantised_log_discount_floor_gain_v1'
    return table(scale)


def all_worlds(case):
    unknown = tuple(sorted(case['unknown']))
    for values in product(range(4), repeat=len(unknown)):
        yield dict(zip(unknown, values))


def scores(case, completion, coeff):
    labels = dict(case['known'])
    labels.update(completion)
    result = {}
    for profile, gains in GAINS.items():
        result[profile] = {
            name: sum(coeff[position][gains[labels[passage]]]
                      for position, passage in enumerate(passages))
            for name, passages in case['runs'].items()
        }
    return result


def outcomes(score_pairs):
    result = {}
    for profile, values in score_pairs.items():
        prefix = tuple(sorted(values, key=lambda name: (-values[name], name))[:3])
        result[profile] = {'set': tuple(sorted(prefix)), 'prefix': prefix}
    return result


def margins(score_pairs, endpoint, a, b):
    """Direct comparisons for one oriented pair, independent of software rows."""
    names = sorted(score_pairs['binary'])
    if endpoint == 'set':
        specs = [('binary', other, a) for other in names if other != a]
        specs += [('graded', other, b) for other in names if other != b]
    else:
        specs = [('binary', a, b), ('graded', b, a)]
    return tuple(score_pairs[p][left] - score_pairs[p][right] - int(left > right)
                 for p, left, right in specs)


def fixtures():
    rng = random.Random(917263)
    cases = []
    for i in range(64):
        pool = [f'p{p:02}' for p in range(18)]
        runs = {name: rng.sample(pool, 10) for name in ['omega', 'alpha', 'zeta', 'beta']}
        union = sorted(set().union(*map(set, runs.values())))
        unknown = rng.sample(union, i % 5)
        known = {p: rng.randrange(4) for p in union if p not in unknown}
        cases.append({'id': f'independent-synthetic-{i:03}', 'runs': runs,
                      'known': known, 'unknown': unknown})
    base = [f'c{i}' for i in range(10)]
    cases.append({'id': 'all-common-four-unknown', 'runs': {n: base[:] for n in 'ABCD'},
                  'known': {p: 0 for p in base[4:]}, 'unknown': base[:4]})
    cases.append({'id': 'all-common-rank-shift', 'runs': {
        'A': base[:], 'B': base[1:] + base[:1], 'C': base[3:] + base[:3], 'D': list(reversed(base))},
        'known': {p: i % 4 for i, p in enumerate(base[1:])}, 'unknown': [base[0]]})
    cases.append({'id': 'fully-observed-tie', 'runs': {n: base[:] for n in 'ABCD'},
                  'known': {p: 0 for p in base}, 'unknown': []})
    return cases


def audit(case, coeff):
    cached = []
    found = {'set': False, 'prefix': False}
    names = sorted(case['runs'])
    for world in all_worlds(case):
        ss = scores(case, world, coeff)
        oo = outcomes(ss)
        for endpoint in found:
            changed = oo['binary'][endpoint] != oo['graded'][endpoint]
            scenario_any = any(all(v >= 0 for v in margins(ss, endpoint, a, b))
                               for a in names for b in names if a != b)
            assert changed == scenario_any
            found[endpoint] |= changed
        cached.append((world, ss, oo))
    return found, cached


def verify_trees_exhaustively(case, endpoint, trees, cached):
    """Check every leaf against all actual completions in its covered domain."""
    names, unknown = sorted(case['runs']), tuple(sorted(case['unknown']))
    pairs = [(a, b) for a in names for b in names if a != b]
    assert len(trees) == len(pairs)
    all_keys = {tuple(world[p] for p in unknown) for world, _, _ in cached}
    counts = {'leaf_bounds': 0, 'covered_scenario_completions': 0, 'nodes': 0}
    for tree, (a, b) in zip(trees, pairs):
        coverage = set()
        def visit(node, fixed):
            counts['nodes'] += 1
            if set(node) == {'subset'}:
                subset = node['subset']
                assert subset and subset == sorted(set(subset))
                points = [(world, ss) for world, ss, _ in cached
                          if all(world[p] == d for p, d in fixed.items())]
                assert points
                observed = []
                for world, ss in points:
                    rows = margins(ss, endpoint, a, b)
                    assert all(type(j) is int and 0 <= j < len(rows) for j in subset)
                    observed.append(sum(rows[j] for j in subset))
                    key = tuple(world[p] for p in unknown)
                    assert key not in coverage
                    coverage.add(key)
                assert max(observed) < 0
                counts['leaf_bounds'] += 1
                counts['covered_scenario_completions'] += len(points)
            else:
                assert set(node) == {'split', 'children'}
                p, children = node['split'], node['children']
                assert p in unknown and p not in fixed and len(children) == 4
                for d, child in enumerate(children):
                    visit(child, dict(fixed, **{p: d}))
        visit(tree, {})
        assert coverage == all_keys
    return counts
