"""Transparency-first heuristic candidate search; no pretense of reliable type prediction.

The labels BOOST/AGR on anonymous raw bytes are weak hypotheses, never identified
calibration functions. Verified metadata is imported separately in definitions.py.
"""
from __future__ import annotations
import numpy as np
from .model import BinaryImage, MapDefinition


def _guess_kind(block: np.ndarray) -> tuple[str, str]:
    """Return a weak *visual search cue*, NOT an ECU map identification."""
    p05, med, p95 = np.percentile(block, [5, 50, 95])
    if 800 <= med <= 3000 and 950 <= p95 <= 4500 and p05 >= 150:
        return "Boost-Verdacht", "Rohwerte im typischen Druck-Zahlenbereich; ohne Skalierung/Achsen kein Nachweis."
    if 5 <= med <= 90 and 20 <= p95 <= 100 and p05 >= 0:
        return "AGR-Verdacht", "Rohwerte im möglichen Prozentbereich; viele andere Tabellen sind ebenso möglich."
    return "Unbekannt", "Keine belastbare Funktionszuordnung aus den Rohwerten."


def discover_maps(image: BinaryImage, max_results: int = 60, scan_limit_mb: int = 8, *, cancelled=None) -> list[MapDefinition]:
    """Find smooth nontrivial rectangular 16-bit arrays. Scan fixed alignment/grid.

    Bound complexity to protect GUI. Runs in a background worker in the GUI.
    Most true maps will be missed and false positives are expected.
    """
    limit = min(image.size, max(1, scan_limit_mb) * 1024 * 1024)
    if limit < 128:
        return []
    buf = image.read(0, limit)
    candidates = []
    # 16-byte search alignment; matrices are contiguous, assumed not interleaved.
    for endian, dtype in (("big", ">u2"), ("little", "<u2")):
        array = np.frombuffer(buf[:len(buf) // 2 * 2], dtype=dtype).astype(np.float32)
        for rows, cols in ((8, 8), (12, 12), (16, 16), (16, 12), (12, 16), (20, 16), (16, 20)):
            length = rows * cols
            if len(array) < length:
                continue
            starts = np.arange(0, len(array) - length + 1, 8, dtype=np.int64)
            # Process bounded chunks to avoid megabyte-scale allocations.
            for k in range(0, len(starts), 1024):
                if cancelled and cancelled():
                    return []
                starts_block = starts[k:k + 1024]
                window = array[starts_block[:, None] + np.arange(length)[None, :]]
                mat = window.reshape(-1, rows, cols)
                # Fast screening first (critical for multi-megabyte firmware).
                # Random/noisy regions fail early without expensive percentiles.
                span = np.maximum(window.max(axis=1)-window.min(axis=1), 1)
                h_diff = np.abs(np.diff(mat, axis=2))
                h_mean = np.mean(h_diff, axis=(1, 2)) / span
                # Apply the same necessary predicate before allocating vertical
                # differences/row statistics. No new rejection rule is added.
                horizontal = (span >= 8) & (span <= 65535) & (h_mean < .19)
                if not np.any(horizontal):
                    continue
                starts_block=starts_block[horizontal]
                window=window[horizontal]
                mat=mat[horizontal]
                span=span[horizontal]
                h_diff=h_diff[horizontal]
                h_mean=h_mean[horizontal]
                v_diff = np.abs(np.diff(mat, axis=1))
                v_mean = np.mean(v_diff, axis=(1, 2)) / span
                var_rows = np.std(np.mean(mat, axis=2), axis=1)
                var_cols = np.std(np.mean(mat, axis=1), axis=1)
                precheck = ((span >= 8) & (span <= 65535) &
                            (h_mean < .19) & (v_mean < .24) &
                            (var_rows > .006 * span) & (var_cols > .006 * span))
                preliminary = np.flatnonzero(precheck)
                if len(preliminary)==0:
                    continue
                # Robust high-percentile boundary check, only on plausible data.
                narrow = window[preliminary]
                low = np.percentile(narrow, 5, axis=1)
                high = np.percentile(narrow, 95, axis=1)
                spread = np.maximum(high-low, 1)
                h = np.median(h_diff[preliminary], axis=(1, 2)) / spread
                v = np.median(v_diff[preliminary], axis=(1, 2)) / spread
                h95 = np.percentile(h_diff[preliminary], 95, axis=(1, 2)) / spread
                v95 = np.percentile(v_diff[preliminary], 95, axis=(1, 2)) / spread
                okay = ((spread >= 8) & (spread <= 30000) &
                        (h < .19) & (v < .25) &
                        (h95 < .22) & (v95 < .30) &
                        ((narrow == 0).mean(axis=1) < .40) &
                        ((narrow == 65535).mean(axis=1) < .40))
                indices = preliminary[np.flatnonzero(okay)]
                metrics = {int(ix): (float(h[j]),float(v[j]),float(h95[j]),float(v95[j])) for j,ix in enumerate(preliminary)}
                for idx in indices:
                    hh, vv, hh95, vv95 = metrics[int(idx)]
                    r = (hh + vv) / 2 + (hh95 + vv95) / 4
                    # Score prioritizes smoothness but penalizes huge 16-bit spreads.
                    score = max(0., min(.44, .44 - r * .55))
                    # Weak numeric-range tie breaker for endian ambiguity.
                    # Does NOT turn a type hypothesis into a verified label.
                    hint, _ = _guess_kind(window[idx])
                    if hint != "Unbekannt":
                        score += .012
                    if score < .27:
                        continue
                    offset = int(starts_block[idx] * 2)
                    # retain only a limited candidate pool even for large files
                    candidates.append((score + .005 * min(rows, cols) / 16, offset, rows, cols, endian))
            # Bound intermediate result count; sort by score but need diversity.
            if len(candidates) > max_results * 200:
                candidates.sort(reverse=True)
                candidates = candidates[:max_results * 100]
    candidates.sort(reverse=True)
    chosen: list[MapDefinition] = []
    spans = []
    for score, offset, rows, cols, endian in candidates:
        extent = rows * cols * 2
        if any(offset < stop and start < offset + extent for start, stop in spans):
            continue
        values = np.frombuffer(buf[offset:offset+extent], dtype=">u2" if endian == "big" else "<u2").reshape(rows, cols)
        kind, reason = _guess_kind(values)
        chosen.append(MapDefinition(name=f"Kandidat @ 0x{offset:08X}", offset=offset, rows=rows, cols=cols,
                                    dtype="u16", endian=endian, kind=kind, source="heuristic",
                                    confidence=round(float(score), 2), notes=reason,
                                    label_origin="Ungeprüfte Rohwert-Heuristik" if kind != "Unbekannt" else "Nur Strukturkandidat",
                                    label_evidence=reason, type_score=0.0))
        spans.append((offset, offset + extent))
        if len(chosen) >= max_results:
            break
    return sorted(chosen, key=lambda x: x.offset)
