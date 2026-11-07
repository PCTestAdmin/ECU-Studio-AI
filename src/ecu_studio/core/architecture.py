"""Processor architecture of a firmware image, from at least two independent signs.

Code analysis is architecture specific: the C16x reference search reads
``E6 Fx`` byte pairs as ``MOV Rw,#imm16`` and the TriCore call analysis reads
16/32-bit TriCore opcodes. Applied to other code, chance byte patterns become
"code evidence" (1.19.0: one C16x page+offset reference on the ASCII string list
of a rusEFI ARM image). The decoders therefore run only for an architecture this
module has established.

An architecture counts as established only when two independent signs agree:

  ARM Cortex-M  valid vector table (initial stack pointer in SRAM, odd Thumb
                handler addresses near the reset vector) AND Thumb code density
                (``bx lr`` and ``push {..., lr}``).
  AVR           interrupt vector table of ``jmp``/``rjmp`` instructions at
                offset 0 AND ``ret`` density.
  C16x          trap vector table of ``jmps seg,addr`` instructions in the
                4-byte slots at offset 0 AND code density (``rets`` and
                ``mov Rw,#imm16``).
  TriCore       ``ret`` (0x9000) density AND ``movh.a`` density
                (tricore_refs.looks_like_tricore).

One sign alone (e.g. a few chance opcodes) is not enough; if no architecture
or more than one is established, the result is ``unknown`` and no
architecture-specific code evidence is produced. Thresholds are densities per
64 KiB, measured on local files (docs/ENTWICKLUNG_1.19.1.md): C16x code 151-235
``rets`` and 571-964 moves, every other image at most 4 and 13.

Bosch ME7 lookup call sequences (four chained moves to R12..R15) are moves of
the same ``mov Rw,#imm16`` family as the density sign, not an independent
second sign: they are reported in ``signs`` but decide nothing.

Calibration-only images (no code) are ``unknown``: there is no code to analyse.

Nothing here is cached: one decision costs a few milliseconds and runs once
per scan, and a module-level cache would keep whole firmware images alive.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
import numpy as np

TRICORE, C16X, ARM, AVR, UNKNOWN = 'TriCore', 'C16x', 'ARM', 'AVR', 'unknown'

# Cortex-M: SRAM / CCM / DTCM regions an initial stack pointer may point into.
ARM_STACK_REGIONS = ((0x10000000, 0x10100000), (0x1FF00000, 0x20000000), (0x20000000, 0x20400000))
ARM_MIN_HANDLERS = 8          # of the 15 system handler entries after the stack pointer
ARM_MIN_BX_LR = 40            # per 64 KiB; FOME/rusEFI 118-222, other images <= 1
ARM_MIN_PUSH_LR = 60          # per 64 KiB; FOME/rusEFI 140-169, other images <= 87 (AVR data)
AVR_MIN_VECTORS = 16          # ATmega: 26..57 vectors of 4 (jmp) or 2 (rjmp) bytes
AVR_MIN_RET = 50              # per 64 KiB; Speeduino 218, other images <= 1
C16X_MIN_VECTORS = 16         # of 128 trap vector slots; MS42/MS43/ME7.5 120-128, other images 0
C16X_MIN_RETS = 40            # per 64 KiB
C16X_MIN_MOV = 150            # per 64 KiB
MIN_SIZE = 4096

_C16X_MOV = re.compile(rb"\xE6[\xF0-\xFF]..", re.S)
_C16X_LOOKUP = re.compile(rb"\xE6\xFC..\xE6\xFD..\xE6\xFE..\xE6\xFF..", re.S)


@dataclass(frozen=True)
class Architecture:
    name: str
    evidence: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    signs: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def known(self) -> bool:
        return self.name != UNKNOWN

    def describe(self) -> str:
        if self.known:
            return f'{self.name}: ' + '; '.join(self.evidence)
        if self.conflicts:
            return 'unbekannt (widersprüchliche Belege: ' + ', '.join(self.conflicts) + ')'
        return 'unbekannt (keine ausreichenden Belege)'


def _per64k(count: int, size: int) -> float:
    return count * 0x10000 / max(size, 1)


def arm_vector_table(data: bytes) -> tuple[int, int] | None:
    """(initial stack pointer, reset vector) of a plausible Cortex-M vector table at offset 0, else None."""
    if len(data) < 64:
        return None
    w = np.frombuffer(data[:64], '<u4').astype(np.int64)
    sp, reset = int(w[0]), int(w[1])
    if sp % 4 or not any(lo < sp <= hi for lo, hi in ARM_STACK_REGIONS):
        return None
    if not reset & 1 or reset < 0x100:
        return None
    # Handlers are odd Thumb addresses near the reset handler, or 0 (reserved entries).
    near = [(v & 1) == 1 and abs(v - reset) < 0x200000 for v in w[1:16].tolist()]
    if sum(near) < ARM_MIN_HANDLERS:
        return None
    return sp, reset


def avr_vectors(data: bytes) -> int:
    """Leading interrupt vectors: 4-byte ``jmp`` (0x940C/0x940D) or 2-byte ``rjmp`` entries."""
    jmp = 0
    for i in range(0, min(len(data), 128 * 4) - 3, 4):
        if data[i + 1] == 0x94 and data[i] & 0xFE == 0x0C:
            jmp += 1
        else:
            break
    rjmp = 0
    for i in range(0, min(len(data), 128 * 2) - 1, 2):
        if data[i + 1] & 0xF0 == 0xC0:
            rjmp += 1
        else:
            break
    return max(jmp, rjmp)


def c16x_vectors(data: bytes) -> int:
    """Trap/interrupt vector slots at 0x000-0x1FF holding ``jmps seg,addr`` (0xFA) to an even address."""
    return sum(1 for i in range(0, min(len(data), 128 * 4) - 3, 4)
               if data[i] == 0xFA and not data[i + 2] & 1)


def signs(data: bytes) -> dict:
    """Measured signs (densities per 64 KiB, vector table checks) behind the decision."""
    n = len(data)
    h = np.frombuffer(data[:n // 2 * 2], '<u2')
    vt = arm_vector_table(data)
    return {
        'size': n,
        'arm_vector_table': vt is not None,
        'arm_bx_lr': round(_per64k(int((h == 0x4770).sum()), n), 1),
        'arm_push_lr': round(_per64k(int(((h & 0xFF00) == 0xB500).sum()), n), 1),
        'avr_vectors': avr_vectors(data),
        'avr_ret': round(_per64k(int((h == 0x9508).sum()), n), 1),
        'c16x_vectors': c16x_vectors(data),
        'c16x_rets': round(_per64k(int((h == 0x00DB).sum()), n), 1),
        'c16x_mov': round(_per64k(len(_C16X_MOV.findall(data)), n), 1),
        'c16x_lookups': len(_C16X_LOOKUP.findall(data)),
        'tricore_ret': round(_per64k(int((h == 0x9000).sum()), n), 1),
        'tricore_movh_a': round(_per64k(int(((h & 0xFF) == 0x91).sum()), n), 1),
    }


def detect_architecture(data: bytes) -> Architecture:
    """Established architecture of an image; ``unknown`` without two agreeing signs."""
    data = data if isinstance(data, bytes) else bytes(data)
    if len(data) < MIN_SIZE:
        return Architecture(UNKNOWN, signs={'size': len(data)})
    s = signs(data)
    found: dict[str, tuple[str, ...]] = {}
    if s['arm_vector_table'] and s['arm_bx_lr'] >= ARM_MIN_BX_LR and s['arm_push_lr'] >= ARM_MIN_PUSH_LR:
        sp, reset = arm_vector_table(data)
        found[ARM] = (f'Cortex-M-Vektortabelle (Stack 0x{sp:08X}, Reset 0x{reset:08X})',
                      f"Thumb-Code: bx lr {s['arm_bx_lr']:.0f}, push {{lr}} {s['arm_push_lr']:.0f} je 64 KiB")
    if s['avr_vectors'] >= AVR_MIN_VECTORS and s['avr_ret'] >= AVR_MIN_RET:
        found[AVR] = (f"{s['avr_vectors']} Interrupt-Sprungvektoren ab Adresse 0",
                      f"ret {s['avr_ret']:.0f} je 64 KiB")
    if s['c16x_vectors'] >= C16X_MIN_VECTORS and s['c16x_rets'] >= C16X_MIN_RETS and s['c16x_mov'] >= C16X_MIN_MOV:
        found[C16X] = (f"{s['c16x_vectors']} Trap-Vektoren (jmps) ab Adresse 0",
                       f"C16x-Code: rets {s['c16x_rets']:.0f}, mov Rw,#imm {s['c16x_mov']:.0f} je 64 KiB")
    from .tricore_refs import looks_like_tricore
    if looks_like_tricore(data):
        found[TRICORE] = (f"ret {s['tricore_ret']:.0f}, movh.a {s['tricore_movh_a']:.0f} je 64 KiB",)
    if len(found) == 1:
        name, evidence = next(iter(found.items()))
        return Architecture(name, evidence, signs=s)
    return Architecture(UNKNOWN, conflicts=tuple(sorted(found)), signs=s)


def allows(arch: Architecture, family: str) -> bool:
    """May the code decoder of ``family`` run on an image of this architecture?"""
    return arch.name == family
