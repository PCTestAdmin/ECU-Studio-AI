"""Calibrated confidence: measured hit rates per evidence class, not guesses.

Each automatic candidate belongs to an evidence class (code reference with
axes, code reference only, count-prefixed axis, smoothness only, ...). For
every class the share of candidates that start exactly at a real calibration
object was measured on firmware with complete reference definitions
(tools/calibrate_confidence.py). That rate is shown as a percentage together
with its sample size. A rate describes the class on the measured families; for
other ECU families it is a guide, not a guarantee.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from .model import MapDefinition

DATA = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'confidence_calibration.json'
MIN_SAMPLES = 20

TIERS = (('gesichert', .90), ('wahrscheinlich', .60), ('Vermutung', 0.))


def evidence_class(m: MapDefinition) -> str:
    """Stable key describing what evidence produced a candidate."""
    layout = m.record_layout or 'raster'
    one_d = min(m.rows, m.cols) == 1
    if layout == 'candidate:code-reference':
        axes = 'axes2' if m.axes_x and m.axes_y else 'axis1' if m.axes_x else 'noaxes'
        return f"code:{'1d' if one_d else '2d'}:{axes}"
    if layout == 'candidate:code-reference-generic':
        return 'code:generic'
    if layout == 'candidate:count-axis':
        return 'axis:count'
    if layout == 'candidate:nx,ny,x,y,z':
        return 'header:nxny'
    if layout == 'candidate:row-pitch':
        return 'pitch'
    return 'raster'


@lru_cache(maxsize=1)
def calibration() -> dict:
    try:
        return json.loads(DATA.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'classes': {}}


def tier_for(rate: float) -> str:
    return next(name for name, low in TIERS if rate >= low)


def apply_confidence(maps: list[MapDefinition], table: dict | None = None) -> list[MapDefinition]:
    """Annotate heuristic candidates with measured rate and tier (in place)."""
    classes = (table or calibration()).get('classes', {})
    for m in maps:
        if m.source != 'heuristic':
            continue
        row = classes.get(evidence_class(m))
        if not row or row.get('n', 0) < MIN_SAMPLES:
            m.evidence_tier, m.calibrated_rate = 'nicht kalibriert', None
            continue
        m.calibrated_rate = round(float(row['rate']), 3)
        m.evidence_tier = tier_for(m.calibrated_rate)
        note = (f"Evidenzklasse {evidence_class(m)}: {m.calibrated_rate:.0%} Treffer "
                f"(n={row['n']}, {', '.join(row.get('families', []))}) – {m.evidence_tier}.")
        if note not in m.notes:
            m.notes = (m.notes + ' ' + note).strip()
    return maps
