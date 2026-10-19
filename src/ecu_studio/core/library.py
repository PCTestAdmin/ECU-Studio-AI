"""Locally curated exact-byte map recognition; never infer a verified ECU function.

Fingerprint labels are user-provided. An exact payload match in another file is
strong structural evidence, but it is NOT a verified calibration identification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path

from .model import BinaryImage, MapDefinition


@dataclass
class Signature:
    name: str
    kind: str
    rows: int
    cols: int
    dtype: str
    endian: str
    factor: float
    bias: float
    unit: str
    payload_hex: str
    digest: str


def default_library_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".ecu_studio_ai"))
    return root / "ECUStudioAI" / "fingerprints.json"


class MapLibrary:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_library_path()
        self.signatures: list[Signature] = []
        if self.path.exists():
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            if doc.get("format") != 1 or not isinstance(doc.get("signatures"), list):
                raise ValueError("Ungültige Fingerprint-Bibliothek")
            if len(doc["signatures"]) > 5000:
                raise ValueError("Fingerprint-Bibliothek zu groß")
            for item in doc["signatures"]:
                sig = Signature(**item)
                if len(sig.payload_hex) > 512 * 512 * 8:
                    raise ValueError("Fingerprint-Eintrag zu groß")
                if hashlib.sha256(bytes.fromhex(sig.payload_hex)).hexdigest() != sig.digest:
                    raise ValueError("Fingerprint-Daten beschädigt")
                self.signatures.append(sig)

    def add(self, image: BinaryImage, m: MapDefinition) -> None:
        if not m.verified:
            raise ValueError("Kennfeld zuerst ausdrücklich als manuell geprüft markieren")
        if m.kind in ("Unbekannt", "Boost-Verdacht", "AGR-Verdacht"):
            raise ValueError("Bitte einen geprüften Typ wählen (nicht Verdacht/Unbekannt)")
        m.validate(image.size)
        if (m.storage_order!='row-major' or m.major_stride_bits not in (0,m.width*8)
                or m.minor_stride_bits or m.equation):
            raise ValueError('Fingerprintformat 1 unterstützt nur gepackte affine Kennfelder; andere Layouts in der Definitionsdatenbank speichern')
        payload = image.read(m.offset, m.length)
        if len(payload) < 64 or len(set(payload)) < 12:
            raise ValueError("Kennfeld für eindeutigen Fingerprint zu klein oder zu gleichförmig")
        sig = Signature(
            name=m.name, kind=m.kind, rows=m.rows, cols=m.cols, dtype=m.dtype,
            endian=m.endian, factor=m.factor, bias=m.bias, unit=m.unit,
            payload_hex=payload.hex(), digest=hashlib.sha256(payload).hexdigest(),
        )
        if not any(x.digest == sig.digest and x.rows == sig.rows and x.cols == sig.cols for x in self.signatures):
            self.signatures.append(sig)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        destination = self.path
        tmp = destination.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps({"format": 1, "signatures": [asdict(x) for x in self.signatures]},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(destination)
        finally:
            tmp.unlink(missing_ok=True)

    def find(self, image: BinaryImage, max_hits: int = 200) -> list[MapDefinition]:
        """Find unique, exact byte sequences, never classify by weak statistics here."""
        data = image.materialize()
        found: list[MapDefinition] = []
        seen = set()
        for sig in self.signatures:
            payload = bytes.fromhex(sig.payload_hex)
            if not payload or len(payload) > len(data):
                continue
            pos = data.find(payload)
            if pos < 0 or data.find(payload, pos + 1) >= 0:
                continue  # ambiguous occurrence; no auto-tag
            key = (pos, sig.rows, sig.cols, sig.dtype, sig.endian)
            if key in seen:
                continue
            seen.add(key)
            kind = sig.kind
            m = MapDefinition(
                name=f"{sig.name} [Referenz-Match]", kind=kind, offset=pos,
                rows=sig.rows, cols=sig.cols, dtype=sig.dtype, endian=sig.endian,
                factor=sig.factor, bias=sig.bias, unit=sig.unit, source="exact-reference",
                confidence=0.0, verified=False,
                label_origin="Exakter Referenztreffer (ungeprüft)",
                label_evidence="Vollständiger, eindeutiger Byte-Fingerprint einer manuell gepflegten Referenz. ECU-/Softwarestand erneut prüfen.",
                type_score=0.9,
                notes="EXAKTER Byte-Fingerprint aus manuell gepflegter Bibliothek. "
                      "Funktion, Skalierung und ECU-Kompatibilität im Zielfile erneut prüfen.",
            )
            m.validate(image.size)
            found.append(m)
            if len(found) >= max_hits:
                break
        return found
