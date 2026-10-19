"""Offline, attributed software-specific layouts; never independent verification.

Full source XDFs are shipped unchanged, including linked axes. No BIN content,
vehicle identity, executable patches, network requests or training are involved.
An identity marker alone is insufficient: require a distributed axis quorum.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import math
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.profiles import identify_profile
from ecu_studio.core.xdf import read_xdf

DATA = Path(__file__).parent / 'data' / 'definitions'


def matching_source(image: BinaryImage) -> dict | None:
    p = identify_profile(image)
    for item in sources():
        if (p.family == item['family'] and p.software_version == item['software']
                and image.size == item['size']):
            return item
    return None


def sources():
    return json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))


def _axis_ok(values, count):
    if count == 1:
        return True
    if len(values) != count or not all(math.isfinite(v) for v in values):
        return False
    steps = [b-a for a,b in zip(values, values[1:])]
    return bool(steps and (all(d > 0 for d in steps) or all(d < 0 for d in steps)))


def definition_candidates(image: BinaryImage, *, cancelled=None) -> list:
    """Source-defined tables/curves, with units/layout/axes, not guessed geometry.

    Stock source matching is a compatibility proposal, NOT proof of patch variant. Keep
    unverified metadata visible; require both continuous axes to be readable.
    Constants/axis objects are available in the shipped XDF for explicit import.
    """
    item = matching_source(image)
    if item is None or (cancelled and cancelled()):
        return []
    path = DATA / item['file']
    payload = path.read_bytes()
    actual = hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()
    if actual != item['git_blob']:
        raise ValueError('Mitgelieferte Kennfelddefinition beschädigt: '+item['file'])
    parsed = read_xdf(str(path), image, include_constants=False)
    accepted = []
    anchors = set()
    regions = set()
    for m in parsed.maps:
        if cancelled and cancelled():
            return []
        if m.folder == 'Axis' or max(m.rows,m.cols) <= 1:
            continue
        if not (_axis_ok(m.axes_x,m.cols) and _axis_ok(m.axes_y,m.rows)):
            continue
        if min(m.rows,m.cols) >= 4:
            # Distinct axis pairs and distributed table positions, not repeated
            # references to one incidental monotone run or one identity string.
            anchors.add((tuple(m.axes_x), tuple(m.axes_y)))
            regions.add((m.offset-item['cal_start']) // 2048)
        accepted.append(m)
    if len(anchors) < 12 or len(regions) < 4:
        return []
    for m in accepted:
        m.source = 'bundled-definition'
        m.verified = False
        m.confidence = 0.
        m.label_origin = f"MS4X-XDF {item['version']} · Software-/Achsenabgleich · ungeprüft"
        m.label_evidence = (f"Quelle: {item['url']} · Git-Blob {item['git_blob']}. "
            f"{item['family']} {item['software']} Standard-Layout; Softwarekennung/Dateigröße und verteilte "
            'monotone Achsen passen. Patchvariante NICHT unabhängig bestätigt; '
            'keine automatische Extended-Load-Skalierung, keine Trainingsfreigabe.')
        m.notes += ' | Mitgelieferte Standard-XDF, GPL-3.0, MS4x Dev Team; ungeprüfte Zuordnung.'
    return sorted(accepted, key=lambda m:(m.offset,m.name))
