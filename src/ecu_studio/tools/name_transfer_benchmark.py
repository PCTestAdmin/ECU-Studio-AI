"""Measure name transfer between sister versions against the target's own definition.

Usage: python -m ecu_studio.tools.name_transfer_benchmark SRC.bin SRC.xdf|a2l DST.bin DST.xdf|a2l

A transfer is correct when the target definition has a map of the same name at
the proposed offset with the same shape. Reported per evidence class, plus the
share of the shared names that were transferred at all. Only counts are printed.
"""
from __future__ import annotations
import argparse
import collections
import json
import time
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.name_transfer import transfer_names, EVIDENCE
from ecu_studio.tools.structure_benchmark import _reference


def measure(src_bin, src_ref, dst_bin, dst_ref, src_anchor=None, dst_anchor=None) -> dict:
    source, target = BinaryImage.from_file(src_bin), BinaryImage.from_file(dst_bin)
    smaps = [m for m in _reference(src_ref, source, src_anchor) if m.rows * m.cols >= 2]
    tmaps = {m.name: m for m in _reference(dst_ref, target, dst_anchor)}
    shared = [m for m in smaps if m.name in tmaps]
    t = time.perf_counter()
    result = transfer_names(source, target, shared)
    seconds = time.perf_counter() - t
    by = collections.Counter(); good = collections.Counter()
    for tr in result:
        ref = tmaps[tr.source.name]
        ok = ref.offset == tr.target.offset and {ref.rows, ref.cols} == {tr.target.rows, tr.target.cols}
        by[tr.evidence] += 1; good[tr.evidence] += ok
    same_place = sum(tmaps[m.name].offset == m.offset for m in shared)
    return {'shared_names': len(shared), 'same_address_already': same_place, 'transferred': len(result),
            'correct': sum(good.values()), 'seconds': round(seconds, 1),
            'by_evidence': {e: {'n': by[e], 'correct': good[e]} for e in EVIDENCE if by[e]}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('src_bin'); p.add_argument('src_ref'); p.add_argument('dst_bin'); p.add_argument('dst_ref')
    a = p.parse_args(argv)
    print(json.dumps(measure(a.src_bin, a.src_ref, a.dst_bin, a.dst_ref), indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
