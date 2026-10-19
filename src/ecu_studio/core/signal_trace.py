"""Signal tracing: RAM variables the code reads right before a table lookup.

C16x lookups read their axis inputs from RAM shortly before the table address
is loaded (MOV Rw,mem / MOVB / MOVBZ / MOVBS with a 16-bit DPP-relative
address). Maps sharing an input variable share a physical quantity, e.g. engine
speed. The 16-bit addresses are what RAM loggers (ME7Logger-style) record once
the data page pointer is known. Static analysis only: register reuse across
branches is not followed, so the list is a strong hint, not proof.
"""
from __future__ import annotations
import collections
from dataclasses import dataclass
from .model import BinaryImage, MapDefinition
from .structure_scan import c16x_reference_positions

READS = {0xF2: 'MOV', 0xF3: 'MOVB', 0xC2: 'MOVBZ', 0xD2: 'MOVBS'}
LOOKBACK = 40


@dataclass(frozen=True)
class InputRead:
    address: int        # 16-bit operand: bits 15..14 select the data page pointer
    op: str
    distance: int       # code bytes before the table reference


def inputs_before(data: bytes, position: int) -> list[InputRead]:
    """Memory reads in the LOOKBACK bytes before a code position (aligned scan)."""
    found = []
    start = max(0, position - LOOKBACK)
    # Never look past a return instruction into the previous routine.
    window = data[start:position]
    last_return = max(window.rfind(r) for r in (b'\xCB\x00', b'\xDB\x00', b'\xFB\x88'))
    if last_return >= 0:
        start += last_return + 2
    for p in range(start, position - 3):
        op, reg = data[p], data[p + 1]
        if op in READS and reg >= 0xF0:
            addr = data[p + 2] | data[p + 3] << 8
            if addr >> 14 == 3 or addr >= 0x8000:      # RAM/SFR pages, not flash constants
                found.append(InputRead(addr, READS[op], position - p))
    return found


def trace_inputs(image: BinaryImage, maps: list[MapDefinition], lo: int = 0,
                 hi: int | None = None) -> dict[int, list[InputRead]]:
    """{map index: input reads} for maps referenced in C16x code."""
    data = image.read(0, image.size)
    refs = c16x_reference_positions(data, lo, image.size if hi is None else hi)
    traces = {}
    for i, m in enumerate(maps):
        reads = {}
        for pos in refs.get(m.offset, ()):
            for r in inputs_before(data, pos):
                if r.address not in reads or r.distance < reads[r.address].distance:
                    reads[r.address] = r
        if reads:
            traces[i] = sorted(reads.values(), key=lambda r: r.distance)
    return traces


def variable_table(traces: dict[int, list[InputRead]]) -> dict[int, list[int]]:
    """{RAM address: map indices reading it}, most shared first."""
    table = collections.defaultdict(list)
    for i, reads in traces.items():
        for r in reads:
            table[r.address].append(i)
    return dict(sorted(table.items(), key=lambda kv: -len(kv[1])))


def trace_report(traces: dict[int, list[InputRead]], maps: list[MapDefinition], top: int = 40) -> str:
    table = variable_table(traces)
    lines = ['SIGNAL-TRACING · RAM-Eingänge vor Kennfeldzugriffen (statische Analyse, ungeprüft)', '',
             f'{len(traces)} Kennfelder mit erkannten Eingängen, {len(table)} RAM-Variablen.', '',
             'Meistgenutzte Variablen (gleiche Variable = gleiche physikalische Größe):']
    for addr, members in list(table.items())[:top]:
        names = ', '.join(maps[i].name for i in members[:5]) + (' …' if len(members) > 5 else '')
        lines.append(f'  0x{addr:04X} (DPP{addr >> 14})  {len(members):3d} Kennfelder  · {names}')
    lines += ['', 'Logger-Liste: diese Adressen mit einem RAM-Logger aufzeichnen; die Korrelation mit '
                  'bekannten Signalen (z. B. OBD-Drehzahl) benennt die Achse.']
    return '\n'.join(lines)
