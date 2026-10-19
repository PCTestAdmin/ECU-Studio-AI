"""Explicit, conservative ECU-memory to BIN-offset address mapping.

Multi-region images are never mapped via a guessed global base. An image can
contain holes, headers, non-contiguous flash banks and mirrored regions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AddressSegment:
    ecu_start: int
    ecu_end: int  # inclusive
    file_start: int

    @property
    def size(self) -> int:
        return self.ecu_end - self.ecu_start + 1

    def validate(self, file_size: int) -> None:
        if not (0 <= self.ecu_start <= self.ecu_end and self.file_start >= 0):
            raise ValueError('Ungültiger ECU-/BIN-Bereich')
        if self.file_start + self.size > file_size:
            raise ValueError('Segment reicht über die BIN-Datei hinaus')


def validate_segments(segments: list[AddressSegment], file_size: int) -> None:
    if not segments or len(segments) > 256:
        raise ValueError('1–256 Segmente erforderlich')
    for segment in segments:
        segment.validate(file_size)
    ordered = sorted(segments, key=lambda x: x.ecu_start)
    if any(left.ecu_end >= right.ecu_start for left, right in zip(ordered, ordered[1:])):
        raise ValueError('ECU-Adresssegmente überlappen')
    on_file = sorted(segments, key=lambda x: x.file_start)
    if any(left.file_start + left.size > right.file_start for left, right in zip(on_file, on_file[1:])):
        raise ValueError('BIN-Dateisegmente überlappen')


def locate_range(ecu_address: int, byte_count: int, segments: list[AddressSegment]) -> int | None:
    """Locate complete region in one segment; do not bridge discontinuities."""
    if byte_count < 1:
        raise ValueError('Ungültige Datengröße')
    for segment in segments:
        if segment.ecu_start <= ecu_address and ecu_address + byte_count - 1 <= segment.ecu_end:
            return segment.file_start + ecu_address - segment.ecu_start
    return None


def parse_segments(text: str, file_size: int) -> list[AddressSegment]:
    """Parse `ECU_START ECU_END FILE_START` lines; decimal or 0x hexadecimal."""
    segments: list[AddressSegment] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.partition('#')[0].strip()
        if not line:
            continue
        parts = line.replace(',', ' ').replace(';', ' ').split()
        if len(parts) != 3:
            raise ValueError(f'Zeile {lineno}: 3 Werte benötigt: ECU_START ECU_ENDE BIN_START')
        try:
            values = [int(x, 0) if x.lower().startswith('0x') else int(x, 10) for x in parts]
        except ValueError as exc:
            raise ValueError(f'Zeile {lineno}: ungültiger Zahlenwert') from exc
        segments.append(AddressSegment(*values))
    validate_segments(segments, file_size)
    return segments
