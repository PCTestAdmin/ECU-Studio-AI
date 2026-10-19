"""Small, local, source-locked revision snapshots with atomic single-undo restore.

Snapshots refer to exact bytes of the *same original image*, not to a similar
ECU file. Patch overlays are stored; no ECU checksum / flashing is performed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
from typing import Any

from .model import BinaryImage, MapDefinition


@dataclass(frozen=True)
class RevisionPreview:
    label: str
    changed_bytes: int
    changes: tuple[tuple[int, int, int], ...]  # offset, current, requested
    selected_map: str | None = None


def make_snapshot(image: BinaryImage, label: str, note: str = '') -> dict:
    label = label.strip()
    if not label or len(label) > 120:
        raise ValueError('Versionsname muss 1–120 Zeichen lang sein')
    if len(note) > 10_000:
        raise ValueError('Kommentar ist zu lang')
    return {
        'schema': 1,
        'label': label,
        'note': note,
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'original_sha256': image.digest,
        'size': image.size,
        'patches': image.patch_records(),
        'snapshot_sha256': hashlib.sha256(image.materialize()).hexdigest(),
    }


def validate_snapshot(image: BinaryImage, snap: dict) -> dict[int, int]:
    if not isinstance(snap, dict) or snap.get('schema') != 1:
        raise ValueError('Ungültige Snapshot-Version')
    if snap.get('original_sha256') != image.digest or snap.get('size') != image.size:
        raise ValueError('Snapshot gehört nicht zum gleichen Original-BIN-Stand (SHA-256/Größe)')
    records = snap.get('patches')
    if not isinstance(records, list) or len(records) > image.size:
        raise ValueError('Ungültige Patch-Liste')
    restored: dict[int, int] = {}
    for pair in records:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('Ungültiges Patch-Format')
        pos, value = pair
        if type(pos) is not int or type(value) is not int or not (0 <= pos < image.size and 0 <= value <= 255):
            raise ValueError('Ungültiges Patch-Byte')
        if pos in restored:
            raise ValueError('Doppelter Snapshot-Patch')
        if value == image.original[pos]:
            raise ValueError('Snapshot enthält redundantes Patch-Byte')
        restored[pos] = value
    # Compute digest of desired state, if present; protects stored snapshots
    if 'snapshot_sha256' in snap:
        out = bytearray(image.original)
        for pos, byte in restored.items():
            out[pos] = byte
        if hashlib.sha256(out).hexdigest() != snap['snapshot_sha256']:
            raise ValueError('Snapshot-Integrität stimmt nicht (SHA-256)')
    return restored


def plan_restore(image: BinaryImage, snap: dict, selected_map: MapDefinition | None = None) -> RevisionPreview:
    """Non-mutating diff against a snapshot; optionally only selected map bytes.

    Selective restore applies the saved state for the selected range while
    preserving all other bytes, including edits outside known maps.
    """
    overlay = validate_snapshot(image, snap)
    if selected_map is not None:
        selected_map.validate(image.size)
        allowed = {selected_map.cell_offset(r,c)+j for r in range(selected_map.rows)
                   for c in range(selected_map.cols) for j in range(selected_map.width)}
        lo, hi = selected_map.offset, selected_map.offset + selected_map.length
    else:
        lo, hi = 0, image.size
    changed_positions = sorted(pos for pos in set(image._patches) | set(overlay)
                               if lo <= pos < hi and (selected_map is None or pos in allowed))
    changes = tuple((pos, image.byte(pos), overlay.get(pos, image.original[pos]))
                    for pos in changed_positions if image.byte(pos) != overlay.get(pos, image.original[pos]))
    return RevisionPreview(str(snap.get('label', 'Unbenannt')), len(changes), changes,
                           selected_map.name if selected_map else None)


def apply_restore(image: BinaryImage, preview: RevisionPreview) -> bool:
    """Restore in one undo step; reject stale previews without partial writes."""
    if not preview.changes:
        return False
    last = -1
    for pos, before, after in preview.changes:
        if pos <= last or not 0 <= pos < image.size or image.byte(pos) != before or not 0 <= after <= 255:
            raise ValueError('Vorschau ist veraltet oder inkonsistent – erneut vergleichen')
        last = pos
    return image.commit(preview.changes, label='Version wiederherstellen: '+preview.label)


def validate_snapshot_set(image: BinaryImage, snapshots: Any) -> list[dict]:
    if not isinstance(snapshots, list):
        raise ValueError('Versionsstände müssen als Liste gespeichert sein')
    for snap in snapshots:
        validate_snapshot(image, snap)
        if len(str(snap.get('label', ''))) > 120 or len(str(snap.get('note', ''))) > 10_000:
            raise ValueError('Snapshot-Text zu lang')
    return snapshots
