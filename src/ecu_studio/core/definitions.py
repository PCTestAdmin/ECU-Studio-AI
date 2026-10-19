"""CSV import/export of user-verified definitions; not an A2L parser."""
import csv
from pathlib import Path
from .model import MapDefinition

COLUMNS = ["name", "offset", "rows", "cols", "dtype", "endian", "factor", "bias", "unit", "kind", "notes"]


def parse_offset(s: str) -> int:
    s = str(s).strip()
    # 0x prefix = hexadecimal, otherwise decimal. Strict and unambiguous.
    return int(s, 0) if s.lower().startswith("0x") else int(s, 10)


def import_definitions(path: str, size: int) -> list[MapDefinition]:
    definitions = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        if not {"name", "offset", "rows", "cols"}.issubset(set(rows.fieldnames or [])):
            raise ValueError("CSV benötigt mindestens name,offset,rows,cols")
        for i, rec in enumerate(rows, 2):
            try:
                kind = rec.get("kind") or "Unbekannt"
                m = MapDefinition(name=rec["name"], offset=parse_offset(rec["offset"]),
                                  rows=int(rec["rows"]), cols=int(rec["cols"]),
                                  dtype=rec.get("dtype") or "u16", endian=rec.get("endian") or "big",
                                  factor=float(rec.get("factor") or 1), bias=float(rec.get("bias") or 0),
                                  unit=rec.get("unit") or "", kind=kind,
                                  notes=rec.get("notes") or "", source="csv", verified=False,
                                  label_origin="CSV-Definition (ungeprüft)" if kind != "Unbekannt" else "",
                                  label_evidence="Typ aus importierter CSV; Herkunft/Softwarestand prüfen." if kind != "Unbekannt" else "")
                m.validate(size)
                definitions.append(m)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Fehler in CSV-Zeile {i}: {exc}") from exc
    return definitions


def export_definitions(path: str, definitions: list[MapDefinition]) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for m in definitions:
            d = m.asdict()
            d["offset"] = f"0x{m.offset:X}"
            writer.writerow({k: d[k] for k in COLUMNS})
