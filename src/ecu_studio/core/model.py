"""Pure, testable ECU binary primitives. Never alter the original input bytes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import json
import math
import struct
from typing import Optional

FORMATS = {
    "u8": ("B", 1, 0, 255),
    "s8": ("b", 1, -128, 127),
    "u16": ("H", 2, 0, 65535),
    "s16": ("h", 2, -32768, 32767),
    "u32": ("I", 4, 0, 4294967295),
    "s32": ("i", 4, -2147483648, 2147483647),
    "f32": ("f", 4, -3.4028234663852886e38, 3.4028234663852886e38),
}
TYPES = ("Unbekannt", "Ladedruck / Boost", "AGR / EGR", "Drehmoment", "Einspritzung", "Zündung", "Luftmasse / Lambda", "Turbo / VTG", "Drehzahl / Leerlauf", "Temperatur / Schutz", "Kraftstoff / Druck", "Diagnose", "Abgasnachbehandlung", "Boost", "AGR", "Boost-Verdacht", "AGR-Verdacht", "Andere")


@dataclass
class MapDefinition:
    name: str
    offset: int
    rows: int = 16
    cols: int = 16
    dtype: str = "u16"
    endian: str = "big"
    factor: float = 1.0
    bias: float = 0.0
    unit: str = ""
    kind: str = "Unbekannt"
    source: str = "manual"
    confidence: float = 0.0  # heuristic score, NOT calibrated probability
    notes: str = ""
    verified: bool = False
    axes_x: list[float] = field(default_factory=list)
    axes_y: list[float] = field(default_factory=list)
    ecu_address: int | None = None
    record_layout: str = ""
    axes_info: str = ""
    # Optional semantic evidence; does not change old project compatibility.
    label_origin: str = ""
    label_evidence: str = ""
    type_score: float = 0.0  # rule strength / shape similarity, NOT probability
    type_alternatives: list[str] = field(default_factory=list)
    storage_order: str = "row-major"
    # XDF memory strides are in BITS, and describe distance within a line
    # (major) plus distance from final element to next line (minor).
    # Zero means the packed/default TunerPro arrangement.
    major_stride_bits: int = 0
    minor_stride_bits: int = 0
    # Non-affine XDF formula: decoded read-only, editing requires a verified inverse.
    equation: str = ""
    axis_x_channel: str = ""
    axis_y_channel: str = ""
    axis_x_unit: str = ""
    axis_y_unit: str = ""
    folder: str = ""
    favorite: bool = False
    candidate_region_start: int | None = None
    # Measured hit rate of this candidate's evidence class on reference
    # firmware (see core/confidence.py); None = not calibrated. Not a guarantee.
    evidence_tier: str = ""
    calibrated_rate: float | None = None
    # File offsets of the stored X/Y breakpoints (None = not known). Maps whose
    # axis is read from the same offset share that axis (see core/axis_groups.py).
    # *_ref names a separately stored axis object of a definition (A2L AXIS_PTS).
    axis_x_offset: int | None = None
    axis_y_offset: int | None = None
    axis_x_ref: str = ""
    axis_y_ref: str = ""

    def raw_from_physical(self, value: float) -> int | float:
        if self.equation:
            raise ValueError('Formel ohne geprüfte Umkehrfunktion: schreibgeschützt')
        raw = (float(value) - self.bias) / self.factor
        if not math.isfinite(raw):
            raise ValueError('Nur endliche Rohwerte erlaubt')
        raw = raw if self.dtype == 'f32' else round(raw)
        _, _, low, high = FORMATS[self.dtype]
        if not low <= raw <= high:
            raise ValueError('Rohwertüberlauf: außerhalb des Datentyps')
        return raw

    def scale_raw(self, raw: float) -> float:
        if self.equation:
            from .equations import evaluate_equation
            return evaluate_equation(self.equation, raw)
        return raw * self.factor + self.bias

    def _geometry(self) -> tuple[int, int, int]:
        """(line_length, line_count, line_start_step_bits)."""
        bits = self.width * 8
        major = self.major_stride_bits or bits
        minor = self.minor_stride_bits
        length = self.cols if self.storage_order == 'row-major' else self.rows
        lines = self.rows if self.storage_order == 'row-major' else self.cols
        gap = abs(minor - bits)
        if abs(minor) < gap:
            gap = abs(minor)
        line_step = (length - 1) * abs(major) + bits + gap
        return length, lines, line_step

    @property
    def width(self) -> int:
        return FORMATS[self.dtype][1]

    @property
    def length(self) -> int:
        length, lines, line_step = self._geometry()
        major = abs(self.major_stride_bits or self.width * 8)
        bits = (lines - 1) * line_step + (length - 1) * major + self.width * 8
        return (bits + 7) // 8

    def cell_offset(self,row:int,col:int)->int:
        if not (0<=row<self.rows and 0<=col<self.cols):
            raise IndexError((row,col))
        length, lines, line_step = self._geometry()
        major = self.major_stride_bits or (self.width*8)
        pos, line = ((row,col) if self.storage_order == 'column-major' else (col,row))
        if major < 0:
            pos = length - 1 - pos
        if self.minor_stride_bits < 0:
            line = lines - 1 - line
        address_bits = line * line_step + pos * abs(major)
        return self.offset + address_bits // 8

    def validate(self, size: int) -> None:
        if self.candidate_region_start is not None and (type(self.candidate_region_start) is not int or
                not 0<=self.candidate_region_start<=self.offset):
            raise ValueError('Ungültiger Beginn des vermuteten Records')
        for axis_offset in (self.axis_x_offset, self.axis_y_offset):
            if axis_offset is not None and (type(axis_offset) is not int or not 0 <= axis_offset < size):
                raise ValueError('Achsenadresse außerhalb der BIN-Datei')
        if self.dtype not in FORMATS:
            raise ValueError("Nicht unterstützter Datentyp")
        if self.storage_order not in ("row-major", "column-major"):
            raise ValueError("Nicht unterstützte Speicherordnung")
        if self.endian not in ("big", "little"):
            raise ValueError("Byte-Reihenfolge muss big oder little sein")
        if self.rows < 1 or self.cols < 1 or self.rows > 512 or self.cols > 512:
            raise ValueError("Ungültige Kennfelddimension (1–512)")
        bits = self.width * 8
        major = self.major_stride_bits or bits
        minor = self.minor_stride_bits
        if type(major) is not int or type(minor) is not int:
            raise ValueError('Stride muss eine Ganzzahl sein')
        if abs(major) < bits or major % 8 or minor % 8:
            raise ValueError('Überlappende/bitverschobene Speicherstrides sind nicht darstellbar')
        if self.offset < 0 or self.offset + self.length > size:
            raise ValueError("Kennfeld liegt außerhalb der BIN-Datei")
        if self.equation:
            from .equations import parse_equation
            parse_equation(self.equation)
        if not math.isfinite(self.factor) or self.factor == 0 or not math.isfinite(self.bias):
            raise ValueError("Ungültige Skalierung")

    def asdict(self) -> dict:
        return asdict(self)


class BinaryImage:
    """Copy-on-write byte overlay, with groupable undo/redo and exact export."""
    def __init__(self, original: bytes, path: Optional[str] = None):
        self.original = bytes(original)
        self.path = path
        self.digest = hashlib.sha256(self.original).hexdigest()
        self._patches: dict[int, int] = {}
        self._undo: list[list[tuple[int, int, int]]] = []
        self._redo: list[list[tuple[int, int, int]]] = []
        self.revision = 0  # Invalidates plot caches even if patch count is unchanged.
        self.journal: list[dict] = []

    @classmethod
    def from_file(cls, path: str) -> BinaryImage:
        p = Path(path)
        if p.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Dateien über 128 MiB werden in diesem Prototyp nicht unterstützt")
        return cls(p.read_bytes(), str(p.resolve()))

    @property
    def size(self) -> int:
        return len(self.original)

    @property
    def dirty_bytes(self) -> int:
        return len(self._patches)

    def byte(self, offset: int) -> int:
        if not 0 <= offset < self.size:
            raise IndexError(offset)
        return self._patches.get(offset, self.original[offset])

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.size:
            raise ValueError("Lesezugriff außerhalb der Datei")
        # No overlay: return the original slice without a bytearray copy or
        # a per-byte dictionary lookup. This is the normal scroll path.
        if not self._patches:
            return self.original[offset:offset + length]
        result = bytearray(self.original[offset:offset + length])
        # For long reads and sparse changes, iterate only the patch overlay.
        if length > 512 and len(self._patches) < length // 2:
            for pos, patch in self._patches.items():
                if offset <= pos < offset + length:
                    result[pos - offset] = patch
        else:
            for i in range(length):
                patch = self._patches.get(offset + i)
                if patch is not None:
                    result[i] = patch
        return bytes(result)

    def _apply(self, changes: list[tuple[int, int, int]], forward: bool) -> None:
        if changes:
            self.revision += 1
        for idx, before, after in changes:
            v = after if forward else before
            if v == self.original[idx]:
                self._patches.pop(idx, None)
            else:
                self._patches[idx] = v

    def commit(self, changes, *, label='Bearbeitung', expected_revision=None) -> bool:
        """Validate every byte before applying a transaction in one undo step."""
        if expected_revision is not None and self.revision != expected_revision:
            raise ValueError('Vorschau ist veraltet – erneut berechnen')
        edits = sorted(changes)
        seen = set()
        for pos, before, after in edits:
            if (type(pos) is not int or type(before) is not int or type(after) is not int
                    or not 0 <= pos < self.size or not 0 <= after <= 255
                    or pos in seen or self.byte(pos) != before):
                raise ValueError('Vorschau ist veraltet oder enthält ungültige/überlappende Bytes')
            seen.add(pos)
        edits = [e for e in edits if e[1] != e[2]]
        if not edits:
            return False
        self._apply(edits, True)
        self._undo.append(edits)
        self._redo.clear()
        self._record(label, edits)
        return True

    def _record(self, label, changes):
        from datetime import datetime, timezone
        self.journal.append({'utc': datetime.now(timezone.utc).isoformat(), 'label': label,
                             'revision': self.revision, 'changes': [list(e) for e in changes]})

    def write(self, offset: int, data: bytes) -> None:
        if offset < 0 or offset + len(data) > self.size:
            raise ValueError("Schreibzugriff außerhalb der Datei")
        changes = [(offset+i, self.byte(offset+i), b) for i, b in enumerate(data) if self.byte(offset+i) != b]
        if not changes:
            return
        self.commit(changes, label=f'Bytes ab 0x{offset:X}')

    def undo(self) -> bool:
        if not self._undo:
            return False
        changes = self._undo.pop()
        self._apply(changes, False)
        self._redo.append(changes)
        self._record('Undo', [(p,a,b) for p,b,a in changes])
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        changes = self._redo.pop()
        self._apply(changes, True)
        self._undo.append(changes)
        self._record('Redo', changes)
        return True

    def raw_value(self, m: MapDefinition, row: int, col: int) -> int | float:
        m.validate(self.size)
        if not (0 <= row < m.rows and 0 <= col < m.cols):
            raise IndexError((row, col))
        code, width, _, _ = FORMATS[m.dtype]
        pos = m.cell_offset(row,col)
        return struct.unpack((">" if m.endian == "big" else "<") + code, self.read(pos, width))[0]

    def physical_value(self, m: MapDefinition, row: int, col: int) -> float:
        return m.scale_raw(self.raw_value(m, row, col))

    def matrix(self, m: MapDefinition, *, physical=False):
        """Vectorized logical matrix, including padding and reversed XDF strides."""
        import numpy as np
        m.validate(self.size)
        length, lines, step = m._geometry()
        major = (m.major_stride_bits or m.width*8)//8
        line = step//8 * (-1 if m.minor_stride_bits<0 else 1)
        strides = (line,major) if m.storage_order=='row-major' else (major,line)
        dtype = np.dtype(('>' if m.endian=='big' else '<')+('f' if m.dtype=='f32' else 'u' if m.dtype[0]=='u' else 'i')+str(m.width))
        raw = np.ndarray((m.rows,m.cols),dtype=dtype,buffer=self.read(m.offset,m.length),
                         offset=m.cell_offset(0,0)-m.offset,strides=strides)
        if physical:
            if m.equation:
                return np.array([[m.scale_raw(float(v)) for v in row] for row in raw])
            return raw.astype(float)*m.factor+m.bias
        return raw

    def write_physical(self, m: MapDefinition, row: int, col: int, value: float) -> None:
        m.validate(self.size)
        if m.equation:
            raise ValueError("Nichtlineare XDF-Formel: Kennfeld schreibgeschützt (keine geprüfte Umkehrfunktion)")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Nur endliche Zahlen erlaubt")
        code, width, low, high = FORMATS[m.dtype]
        raw = m.raw_from_physical(value)
        if not low <= raw <= high:
            raise ValueError(f"Rohwert {raw} liegt außerhalb {low} … {high}")
        pos = m.cell_offset(row,col)
        self.write(pos, struct.pack((">" if m.endian == "big" else "<") + code, raw))

    def materialize(self) -> bytes:
        out = bytearray(self.original)
        for p, b in self._patches.items():
            out[p] = b
        return bytes(out)

    def changed_ranges(self) -> list[tuple[int, bytes, bytes]]:
        """Merged contiguous regions; original and current bytes."""
        if not self._patches:
            return []
        positions = sorted(self._patches)
        groups = []
        start = end = positions[0]
        for p in positions[1:]:
            if p == end + 1:
                end = p
            else:
                groups.append((start, self.original[start:end+1], self.read(start, end-start+1)))
                start = end = p
        groups.append((start, self.original[start:end+1], self.read(start, end-start+1)))
        return groups

    def patch_records(self) -> list[list[int]]:
        return [[idx, val] for idx, val in sorted(self._patches.items())]

    def restore_patches(self, records: list[list[int]]) -> None:
        if len(records) > self.size:
            raise ValueError("Ungültige Projektdatei")
        values = {}
        for entry in records:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("Ungültiger Patch-Eintrag")
            p, b = entry
            if type(p) is not int or type(b) is not int or not (0 <= p < self.size and 0 <= b <= 255):
                raise ValueError("Ungültiger Patch-Offset oder Bytewert")
            if p in values:
                raise ValueError("Doppelter Patch-Offset")
            values[p] = b
        self._patches = {p: v for p, v in values.items() if self.original[p] != v}
        self.revision += 1
        self._undo.clear()
        self._redo.clear()


def map_from_record(record: dict, ignored: set[str] | None = None) -> MapDefinition:
    """A map from a project record, also one written by a newer version.

    Fields this version does not know are left out and collected in ``ignored``;
    without that set they are refused, so no caller drops data unknowingly.
    """
    if not isinstance(record, dict):
        raise ValueError('Ungültige Kennfelddefinition im Projekt')
    known = MapDefinition.__dataclass_fields__
    unknown = set(record) - set(known)
    if unknown:
        if ignored is None:
            raise ValueError('Projekt stammt aus einer neueren Version (unbekannte Felder: '
                             + ', '.join(sorted(unknown)) + ')')
        ignored |= unknown
    try:
        return MapDefinition(**{k: v for k, v in record.items() if k in known})
    except TypeError as exc:
        raise ValueError(f'Ungültige Kennfelddefinition im Projekt: {exc}') from None


def save_project(path: str, image: BinaryImage, maps: list[MapDefinition], bookmarks: list[dict], notes: str, snapshots: list[dict] | None = None, *, overwrite=True) -> None:
    from .storage import atomic_write, canonical_digest
    for m in maps:
        m.validate(image.size)
    target = Path(path).resolve()
    if image.path and target == Path(image.path).resolve():
        raise ValueError('Originaldatei darf nicht überschrieben werden')
    original = target.parent / '.ecustudio-originals' / (image.digest+'.bin')
    if original.exists():
        if hashlib.sha256(original.read_bytes()).hexdigest() != image.digest:
            raise ValueError('SHA-256 des Originalbackups stimmt nicht')
    else:
        atomic_write(original, image.original, overwrite=False)
    payload = {"format": 1, "source_file": image.path, "source_sha256": image.digest,
               "patches": image.patch_records(), "maps": [m.asdict() for m in maps],
               "bookmarks": bookmarks, "notes": notes,
               "original_backup": str(original.relative_to(target.parent)), "journal": image.journal}
    if snapshots is not None:
        from .versioning import validate_snapshot_set
        payload["snapshots"] = validate_snapshot_set(image, snapshots)
    payload['integrity_sha256'] = canonical_digest(payload)
    encoded=json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded)>256*1024**2:
        raise ValueError('Projekt überschreitet die unterstützte Größe von 256 MiB')
    atomic_write(target, encoded,
                 backup=overwrite, protected=(image.path, original), overwrite=overwrite)


def load_project(path: str, *, ignored_fields: set[str] | None = None
                 ) -> tuple[BinaryImage, list[MapDefinition], list[dict], str]:
    """``ignored_fields``: collect map fields of newer versions instead of refusing the project."""
    from .storage import canonical_digest
    if Path(path).stat().st_size > 256*1024**2:
        raise ValueError('Projektdatei größer als 256 MiB')
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload,dict):
        raise ValueError('Ungültige Projektstruktur')
    if 'integrity_sha256' in payload and canonical_digest(payload) != payload['integrity_sha256']:
        raise ValueError('Projektintegrität (SHA-256) stimmt nicht')
    if payload.get("format") != 1:
        raise ValueError("Unbekanntes Projektformat")
    source = payload.get("source_file")
    if not source or not Path(source).is_file():
        backup = (Path(path).resolve().parent / payload.get('original_backup', '')).resolve()
        root = Path(path).resolve().parent / '.ecustudio-originals'
        if backup.parent != root or not backup.is_file():
            raise FileNotFoundError("Original-BIN nicht gefunden: " + str(source))
        source = str(backup)
    image = BinaryImage.from_file(source)
    if image.digest != payload.get("source_sha256"):
        raise ValueError("Sicherheitsstopp: SHA-256 der Originaldatei stimmt nicht überein")
    image.restore_patches(payload.get("patches", []))
    journal=payload.get('journal', [])
    if not isinstance(journal,list) or any(not isinstance(entry,dict) for entry in journal):
        raise ValueError('Ungültiges Änderungsprotokoll im Projekt')
    image.journal = journal
    maps = [map_from_record(x, ignored_fields) for x in payload.get("maps", [])]
    for m in maps:
        m.validate(image.size)
    return image, maps, payload.get("bookmarks", []), str(payload.get("notes", ""))


def read_project_snapshots(path: str, image: BinaryImage) -> list[dict]:
    """Backwards-compatible opt-in loading for projects made by older versions."""
    from .versioning import validate_snapshot_set
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("source_sha256") != image.digest:
        raise ValueError("Projekt gehört zu einem anderen Original-BIN-Stand")
    return validate_snapshot_set(image, obj.get("snapshots", []))
