"""Blind 2-D detection benchmark against reference definitions (XDF, A2L, RomRaider XML or CSV).

The reference is only used for scoring, never as scan input. A CSV in the
definitions format (name,offset,rows,cols,dtype,...) can hold any external map
list, e.g. one exported from another tool. Reports counts only; no firmware bytes.
"""
from __future__ import annotations
import argparse
import json
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def _reference(path: str, image: BinaryImage, anchor: int | None = None) -> list[MapDefinition]:
    if Path(path).suffix.lower() == '.xdf':
        from ecu_studio.core.xdf import read_xdf
        return read_xdf(path, image, include_constants=False).maps
    if Path(path).suffix.lower() == '.xml':
        from ecu_studio.core.romraider import read_romraider
        return [m for m in read_romraider(path, image).maps if 0 <= m.offset < image.size]
    if Path(path).suffix.lower() == '.a2l':
        return a2l_reference(path, image, anchor)
    from ecu_studio.core.definitions import import_definitions
    return import_definitions(path, image.size)


def a2l_reference(path: str, image: BinaryImage, anchor: int | None = None) -> list[MapDefinition]:
    """Records of an A2L at the anchor the firmware confirms (see suggest_anchor).

    Raw values are enough for geometry, so unsupported conversions do not drop
    an object here. A given ``anchor`` (e.g. the start address of a converted
    HEX file) is checked the same way: the A2L must explain the file. Raises if
    it does not; a declared EPK that differs links nothing.
    """
    return list(_a2l_cached(str(Path(path).resolve()), image.digest, image.read(0, image.size), anchor))


@lru_cache(maxsize=4)
def _a2l_cached(path: str, digest: str, data: bytes, anchor: int | None) -> tuple:
    from ecu_studio.core.a2l import read_a2l, suggest_anchor, MIN_ANCHOR_MONOTONE
    catalog = read_a2l(path)
    if anchor is None:
        found = suggest_anchor(catalog, data)
        if found is None:
            raise ValueError('A2L passt nicht zu dieser BIN (Achsen an keiner Basis aufsteigend)')
        anchor = found['anchor']
    result = catalog.link(file_size=len(data), ecu_anchor=anchor, data=data, raw_unsupported_conversions=True)
    axes = [m.axes_x for m in result.maps if len(m.axes_x) >= 3 and len(set(m.axes_x)) > 1]
    rising = sum(all(b >= a for a, b in zip(ax, ax[1:])) and ax[-1] > ax[0] for ax in axes)
    if not result.maps or (axes and rising < MIN_ANCHOR_MONOTONE * len(axes)):
        raise ValueError(f'A2L passt nicht zu dieser BIN bei Basis 0x{anchor:X} '
                         f'({rising}/{len(axes)} Achsen steigend, {len(result.maps)} verknüpft)')
    # Axes inside records are reference objects too (as XDF axis addresses are).
    seen = {m.offset for m in result.maps}
    axes = [a for a in result.axis_objects if a.offset not in seen and not seen.add(a.offset)]
    return tuple(result.maps) + tuple(axes)


def reference_tables(path: str, image: BinaryImage, min_dim: int = 4, anchor: int | None = None) -> list[MapDefinition]:
    unique = {(m.offset, m.rows, m.cols, m.width): m for m in _reference(path, image, anchor)
              if m.rows >= min_dim and m.cols >= min_dim}
    return sorted(unique.values(), key=lambda m: m.offset)


def reference_lines(path: str, image: BinaryImage, min_len: int = 2, anchor: int | None = None) -> list[MapDefinition]:
    """1-D objects (curves and axes) with at least min_len values."""
    unique = {(m.offset, m.rows * m.cols, m.width): m for m in _reference(path, image, anchor)
              if min(m.rows, m.cols) == 1 and m.rows * m.cols >= min_len}
    return sorted(unique.values(), key=lambda m: m.offset)


def score_lines(found: list[MapDefinition], reference: list[MapDefinition]) -> dict:
    """Exact agreement of 1-D candidates: same start, value count and width."""
    keys = {(m.offset, m.rows * m.cols, m.width) for m in reference}
    exact = sum((m.offset, m.rows * m.cols, m.width) in keys for m in found)
    return {'reference_lines': len(reference), 'candidates': len(found), 'exact': exact,
            'precision': round(exact / len(found), 3) if found else 0.,
            'recall': round(exact / len(reference), 3) if reference else 0.}


def score(found: list[MapDefinition], reference: list[MapDefinition], min_iou: float = .5) -> dict:
    """IoU-matched precision/recall plus exact layout agreement (start, shape, width)."""
    hit_ref, good, exact = set(), 0, 0
    for m in found:
        s, e = m.offset, m.offset + m.length
        matched = False
        for i, r in enumerate(reference):
            inter = min(e, r.offset + r.length) - max(s, r.offset)
            if inter <= 0:
                continue
            if inter / (max(e, r.offset + r.length) - min(s, r.offset)) >= min_iou:
                matched = True
                hit_ref.add(i)
                if s == r.offset and m.width == r.width and {m.rows, m.cols} == {r.rows, r.cols}:
                    exact += 1
        good += matched
    return {'reference_tables': len(reference), 'candidates': len(found),
            'precision': round(good / len(found), 3) if found else 0.,
            'recall': round(len(hit_ref) / len(reference), 3) if reference else 0.,
            'exact_layouts': exact}


def benchmark(bin_path: str, reference_path: str, *, structure_limit: int = 400) -> dict:
    image = BinaryImage.from_file(bin_path)
    reference = reference_tables(reference_path, image)
    lines = reference_lines(reference_path, image)
    report = {'format': 1, 'sha256': image.digest, 'size': image.size}
    for label, limit in (('legacy', 0), ('current', structure_limit)):
        begin = perf_counter()
        found = scan_calibration_candidates(image, use_definitions=False, structure_limit=limit)
        elapsed = round(perf_counter() - begin, 2)
        areas = [m for m in found if min(m.rows, m.cols) > 1]
        report[label] = (score(areas, reference)
                         | {'lines_1d': score_lines([m for m in found if min(m.rows, m.cols) == 1], lines)}
                         | {'elapsed_seconds': elapsed})
    report['notice'] = ('Geometry agreement with a reference definition only; '
                        'map functions/units are not evaluated.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin')
    parser.add_argument('reference', help='XDF or definitions CSV for the same software version')
    parser.add_argument('--output')
    args = parser.parse_args()
    report = benchmark(args.bin, args.reference)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
