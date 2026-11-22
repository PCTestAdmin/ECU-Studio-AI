"""Function hypotheses under hard conditions: anchor splits and counts (after 1.21.0-rc1).

core/function_id predicts the function of a table only from relations to anchors (tables whose
own definition names the function). Measuring it with every second table as anchor (address order)
is too favourable: almost every hidden table has an anchor right next to it. This module provides
reproducible, harder splits and the counts to report. It holds no data; the reference objects come
from a definition (e.g. A2L FUNCTION / DEF_CHARACTERISTIC) that the caller links to an image.

Splits (deterministic: a keyed hash, no random state):

  alternate   every second table with a function, by address (the earlier, favourable split)
  table       each table independently with probability ``fraction``
  block       whole address blocks (``block`` bytes) are anchors or hidden: no anchor shares a
              block with a hidden table, so direct neighbours mostly fall on the same side
  function    whole functions are anchors or hidden: a hidden table's function is never among the
              anchors (unless it belongs to several), so every assigned function is wrong. This
              measures how often the layer names a function where it should say "Unbekannt".

Counts (always with the number of evaluable tables): correct, wrong, unknown; per status and per
evidence kind; ``reachable`` = hidden tables whose function occurs among the anchors at all.
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections import Counter, defaultdict
from ..core import function_id as F
from ..core.model import MapDefinition

MODES = ('alternate', 'table', 'block', 'function')
FRACTIONS = (.5, .25, .1, .05, .01, 0.)
BLOCK = 4096


def _pick(key: str, fraction: float, salt: str) -> bool:
    if fraction <= 0:
        return False
    if fraction >= 1:
        return True
    digest = hashlib.blake2b(f'{salt}\0{key}'.encode(), digest_size=8).digest()
    return int.from_bytes(digest, 'big') / 2 ** 64 < fraction


def truth_of(m: MapDefinition) -> frozenset[str]:
    return frozenset(f for f in (m.function or '').split(' / ') if f)


def split(maps: list[MapDefinition], mode: str, fraction: float = .5, salt: str = '0',
          block: int = BLOCK) -> set[int]:
    """Indices of ``maps`` that keep their function (anchors). Only tables with a function count."""
    known = [i for i, m in enumerate(maps) if truth_of(m)]
    if mode == 'alternate':
        order = sorted(known, key=lambda i: maps[i].offset)
        return set(order[0::2])
    if mode == 'table':
        return {i for i in known if _pick(f't{maps[i].offset}:{maps[i].name}', fraction, salt)}
    if mode == 'block':
        return {i for i in known if _pick(f'b{maps[i].offset // block}', fraction, salt)}
    if mode == 'function':
        chosen = {f for i in known for f in truth_of(maps[i]) if _pick(f'f{f}', fraction, salt)}
        return {i for i in known if truth_of(maps[i]) <= chosen}
    raise ValueError(f'unknown split mode {mode!r}')


def hide(maps: list[MapDefinition], anchors: set[int]) -> list[MapDefinition]:
    """Copy of ``maps`` in which every table outside ``anchors`` has no function."""
    return [m if i in anchors else dataclasses.replace(m, function='', function_source='')
            for i, m in enumerate(maps)]


@dataclasses.dataclass
class Score:
    evaluable: int = 0      # hidden tables with a reference function
    reachable: int = 0      # ... whose function occurs among the anchors
    anchors: int = 0
    correct: int = 0
    wrong: int = 0
    unknown: int = 0
    by_status: Counter = dataclasses.field(default_factory=Counter)        # (status, 'correct'|'wrong'|'unknown')
    by_kind: Counter = dataclasses.field(default_factory=Counter)          # (kinds, 'correct'|'wrong')
    contradictions: int = 0

    def add(self, other: 'Score') -> None:
        for f in ('evaluable', 'reachable', 'anchors', 'correct', 'wrong', 'unknown', 'contradictions'):
            setattr(self, f, getattr(self, f) + getattr(other, f))
        self.by_status.update(other.by_status)
        self.by_kind.update(other.by_kind)

    def as_dict(self) -> dict:
        out = {f: getattr(self, f) for f in ('evaluable', 'reachable', 'anchors', 'correct', 'wrong', 'unknown',
                                              'contradictions')}
        out['by_status'] = {f'{s}/{r}': n for (s, r), n in sorted(self.by_status.items())}
        out['by_kind'] = {f'{k}/{r}': n for (k, r), n in sorted(self.by_kind.items())}
        return out


def score(maps: list[MapDefinition], anchors: set[int], rels: list[F.Relation] | None = None) -> Score:
    """Hide every non-anchor function, predict with function_id.identify, count against the reference.

    ``rels`` are the relations between ``maps`` (default: function_id.relations, which do not depend
    on functions). A prediction is correct when the hidden table's own reference functions contain it.
    """
    truth = [truth_of(m) for m in maps]
    test = hide(maps, anchors)
    hyp = F.identify(test, rels if rels is not None else F.relations(test))
    anchor_functions = set().union(*(truth[i] for i in anchors)) if anchors else set()
    out = Score(anchors=len(anchors))
    for i, h in enumerate(hyp):
        if i in anchors or not truth[i]:
            continue
        out.evaluable += 1
        out.reachable += bool(truth[i] & anchor_functions)
        out.contradictions += bool(h.contradictions)
        if not h.function:
            out.unknown += 1
            out.by_status[h.status, 'unknown'] += 1
            continue
        verdict = 'correct' if h.function in truth[i] else 'wrong'
        setattr(out, verdict, getattr(out, verdict) + 1)
        out.by_status[h.status, verdict] += 1
        kinds = '+'.join(sorted({e.kind for e in h.evidence})) or '-'
        out.by_kind[kinds, verdict] += 1
    return out


def group_purity(maps: list[MapDefinition], rels: list[F.Relation]) -> dict:
    """Structural groups (function_id.groups) against the reference functions, without using them.

    A group is pure when one function is shared by all its members that have a reference function.
    Counts groups and members; groups without two referenced members are not evaluable.
    """
    truth = [truth_of(m) for m in maps]
    out = Counter()
    for g in F.groups(maps, rels):
        known = [truth[i] for i in g if truth[i]]
        if len(known) < 2:
            out['groups_not_evaluable'] += 1
            continue
        out['groups'] += 1
        out['members'] += len(known)
        if set.intersection(*map(set, known)):
            out['pure'] += 1
            out['pure_members'] += len(known)
        else:
            # the members of the largest function in the group
            share = Counter(f for t in known for f in t).most_common(1)[0][1]
            out['majority_members'] += share
    return dict(out)


def relation_precision(maps: list[MapDefinition], rels: list[F.Relation]) -> dict[str, Counter]:
    """Per relation kind: pairs whose two tables share a reference function, or not, or lack one."""
    truth = [truth_of(m) for m in maps]
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rels:
        a, b = truth[r.a], truth[r.b]
        out[r.kind]['same' if a & b else 'different' if a and b else 'not_evaluable'] += 1
    return dict(out)


__all__ = ['MODES', 'FRACTIONS', 'split', 'hide', 'score', 'Score', 'group_purity', 'relation_precision', 'truth_of']
