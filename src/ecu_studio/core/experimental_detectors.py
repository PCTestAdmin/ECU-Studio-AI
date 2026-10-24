"""Opt-in structural experiments. Never imported by the production scanner.

Independent implementations of ideas reviewed in BimmerStein (paired axis
pointers and exact record packing) and xdfkit (per-field word alignment).
Provenance, pinned sources and restrictions: docs/OPEN_SOURCE_DETECTION_BENCHMARK.md.
No function names, units, calibrated confidence or verification are inferred.
"""
from __future__ import annotations
from .axis_arrays import axis_at
from .model import BinaryImage, MapDefinition
from .structure_scan import _counted_values, c16x_reference_anchors

MAX_IMAGE = 4 * 1024**2
MAX_ANCHORS = 20_000


def _candidate(at, rows, cols, width, x, y, header, layout):
    return MapDefinition(
        f'Experimental structure @ 0x{at:X}', at, rows, cols,
        dtype='u8' if width == 1 else 'u16', endian='little', source='heuristic',
        confidence=0.0, verified=False, axes_x=list(x.values), axes_y=list(y.values),
        axis_x_offset=x.offset, axis_y_offset=y.offset, candidate_region_start=header,
        record_layout=layout, label_origin='Experimental structural hypothesis',
        label_evidence='Counts and stored axes with exact successor boundary; target review required.',
        type_alternatives=['s16'] if width == 2 else ['s8'],
        notes='Raw unsigned storage hypothesis; signedness, units and function are not established.')


def scan_pointer_chains(image: BinaryImage, *, cancelled=None, max_results=1000, diagnostics=None):
    """Direct u16LE X/Y pointers before a table, in a run of >=3 headers.

    Direct file offsets only, <=64 KiB. Both count-prefixed axes must precede
    the header and not overlap. The NEXT header fixes cell width exactly.
    An ambiguous successor rejects the reading. The final table is not emitted:
    its end/type lacks independent evidence. This is not MS41 bank decoding.
    """
    if diagnostics is not None: diagnostics.update(scope='direct-u16le', incomplete=False, applicable=image.size <= 65536)
    if not 0 < max_results <= 5000: raise ValueError('Invalid result budget')
    if image.size > 65536 or image.size < 32: return []
    data = image.read(0, image.size)
    axes, headers = {}, {}
    def axis(ptr):
        if ptr not in axes: axes[ptr] = axis_at(data, ptr)
        return axes[ptr]
    for h in range(len(data) - 4):
        if h % 256 == 0 and cancelled and cancelled(): return []
        xp = int.from_bytes(data[h:h+2], 'little')
        yp = int.from_bytes(data[h+2:h+4], 'little')
        if not 0 < xp < h or not 0 < yp < h or xp == yp: continue
        x, y = axis(xp), axis(yp)
        if not x or not y or min(x.count, y.count) < 4: continue
        if x.end > h or y.end > h or (x.header < y.end and y.header < x.end): continue
        headers[h] = x, y
    links = {}
    ambiguous = 0
    for h, (x, y) in headers.items():
        choices = [(h+4+x.count*y.count*w, w) for w in (1, 2)
                   if h+4+x.count*y.count*w in headers]
        if len(choices) == 1: links[h] = choices[0]
        elif choices: ambiguous += 1
    # Components are increasing chains; at least two consecutive edges needed.
    valid = set()
    for h, (nxt, _) in links.items():
        if nxt in links: valid.update((h, nxt))
    out = []
    for h in sorted(valid):
        nxt, width = links[h]
        x, y = headers[h]
        # Axes inside any emitted value range would contradict the interpretation.
        if any(a.header < links[p][0] and p+4 < a.end for a in (x, y) for p in valid): continue
        out.append(_candidate(h+4, y.count, x.count, width, x, y, h, 'experiment:axis-pointer-chain'))
    if diagnostics is not None: diagnostics.update(headers=len(headers), ambiguous=ambiguous)
    if len(out) > max_results:
        if diagnostics is not None: diagnostics['incomplete'] = True
        return []
    return out


def scan_aligned_records(image: BinaryImage, *, cancelled=None, max_results=1000, diagnostics=None):
    """C16x-addressed byte counts with independently aligned 8/16-bit axes.

    A second code-addressed record must follow the value block exactly, fixing
    cell width. Only padded or mixed-axis layouts missing from the packed
    decoder are considered. No geometry-only grid is used as a boundary.
    """
    if diagnostics is not None: diagnostics.update(scope='c16x-aligned-counts', incomplete=False, applicable=image.size <= MAX_IMAGE)
    if not 0 < max_results <= 5000: raise ValueError('Invalid result budget')
    if image.size > MAX_IMAGE or image.size < 32: return []
    data = image.read(0, image.size)
    anchors = c16x_reference_anchors(data, 0, len(data))
    if len(anchors) > MAX_ANCHORS:
        if diagnostics is not None: diagnostics['incomplete'] = True
        return []
    readings = {}
    for i, h in enumerate(anchors):
        if i % 64 == 0 and cancelled and cancelled(): return []
        if h+2 > len(data): continue
        nx, ny = data[h:h+2]
        if not 4 <= nx <= 32 or not 4 <= ny <= 32: continue
        options = []
        for wx, wy in ((1, 1), (1, 2), (2, 1), (2, 2)):
            p = h+2; padded = False
            decoded = []
            for n, w in ((nx, wx), (ny, wy)):
                if w == 2 and p % 2:
                    if p >= len(data) or data[p] not in (0, 255): break
                    p += 1; padded = True
                ax = _counted_values(data, h, p, n, w)
                if ax is None: break
                decoded.append(ax); p = ax.end
            if len(decoded) == 2: options.append((p, decoded, padded, wx != wy))
        readings[h] = options
    out, ambiguous = [], 0
    for h, options in readings.items():
        choices = {}
        for p, (x, y), padded, mixed in options:
            for width in (1, 2):
                at = p
                extra_pad = width == 2 and at % 2
                if extra_pad:
                    if at >= len(data) or data[at] not in (0, 255): continue
                    at += 1
                end = at + x.count*y.count*width
                if end not in readings or not readings[end] or not (padded or extra_pad or mixed): continue
                key = (at, x.offset, x.width, y.offset, y.width, width)
                choices[key] = _candidate(at, y.count, x.count, width, x, y, h, 'experiment:aligned-record')
        if len(choices) == 1: out.extend(choices.values())
        elif choices: ambiguous += 1
    if diagnostics is not None: diagnostics.update(anchors=len(anchors), ambiguous=ambiguous)
    if len(out) > max_results:
        if diagnostics is not None: diagnostics['incomplete'] = True
        return []
    return sorted(out, key=lambda m: (m.offset, m.rows, m.cols, m.dtype))


def combine_conservatively(baseline, proposals, *, diagnostics=None):
    """Keep baseline verbatim; add only proposals with no competing byte span.

    All overlapping experimental proposals are excluded, not ranked by votes.
    Equality includes actual storage type/order and stored axis addresses.
    This method never increases confidence or promotes verification.
    """
    def key(m):
        return m.offset, m.rows, m.cols, m.dtype, m.endian, m.axis_x_offset, m.axis_y_offset
    existing = {key(m) for m in baseline}
    unique = {key(m): m for m in proposals}
    extras, duplicate, conflicts = [], 0, 0
    def overlaps(a, b): return a.offset < b.offset+b.length and b.offset < a.offset+a.length
    for k, m in sorted(unique.items(), key=lambda kv: (kv[0][0], repr(kv[0]))):
        if k in existing: duplicate += 1; continue
        if any(overlaps(m, b) for b in baseline) or any(k != q and overlaps(m, b) for q, b in unique.items()):
            conflicts += 1; continue
        extras.append(m)
    if diagnostics is not None: diagnostics.update(duplicate=duplicate, conflict=conflicts, added=len(extras))
    return sorted([*baseline, *extras], key=lambda m: (m.offset, m.rows, m.cols, m.dtype))
