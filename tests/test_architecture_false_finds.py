"""1.19.1: architecture gate for code decoders, text and pointer-table false finds.

All images are synthetic (no firmware bytes): real opcode encodings at the
densities measured on local files (see core/architecture), vector tables built
like Cortex-M and ATmega images, strings and pointer tables like those found in
open ARM firmware.
"""
import struct
import numpy as np
from ecu_studio.core.architecture import (detect_architecture, ARM, AVR, C16X, TRICORE, UNKNOWN,
                                          arm_vector_table)
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.region_classes import text_spans, pointer_spans, classify, is_text_string, EMPTY
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.structure_scan import (scan_structures, REFERENCE_LAYOUT, POINTER_LAYOUT,
                                           c16x_reference_anchors)

SIZE = 0x20000


def _rng(seed):
    return np.random.default_rng(seed)


def _halfwords(n, seed):
    # Random 16-bit words without accidental opcode hits of any family under test.
    h = _rng(seed).integers(0x0100, 0x4000, n, dtype=np.uint16)
    return h


def _sprinkle(h, value, per_64k, seed, mask=None):
    n = len(h)
    k = int(per_64k * n * 2 / 0x10000)
    idx = _rng(seed).choice(np.arange(64, n), k, replace=False)
    if mask is None:
        h[idx] = value
    else:
        h[idx] = (h[idx] & ~np.uint16(mask)) | np.uint16(value)
    return h


def arm_image(size=SIZE, seed=1, vectors=True, thumb=True):
    h = _halfwords(size // 2, seed)
    if thumb:
        _sprinkle(h, 0x4770, 120, seed + 1)                    # bx lr
        _sprinkle(h, 0xB500, 140, seed + 2, mask=0xFF00)       # push {..., lr}
    data = bytearray(h.tobytes())
    if vectors:
        words = [0x20001000, 0x08000101] + [0x08000201 + 0x10 * k for k in range(14)]
        data[:64] = struct.pack('<16I', *words)
    return data


def avr_image(size=SIZE, seed=3):
    h = _halfwords(size // 2, seed)
    _sprinkle(h, 0x9508, 200, seed + 1)                        # ret
    data = bytearray(h.tobytes())
    for k in range(57):                                         # jmp vectors (ATmega2560)
        data[4 * k:4 * k + 4] = bytes([0x0C, 0x94, 0x72, 0x00])
    return data


def c16x_image(size=SIZE, seed=5, vectors=True, code=True):
    h = _halfwords(size // 2, seed)
    if code:
        _sprinkle(h, 0x00DB, 200, seed + 1)                    # rets (bytes DB 00)
    data = bytearray(h.tobytes())
    # mov Rw,#0xFFFF (E6 Fx FF FF): page 0xFFFF lies outside the image, so the
    # moves give C16x density without chance page/offset references.
    pos = _rng(seed + 2).choice(np.arange(16, size // 4 - 1), 400 * size // 0x10000, replace=False)
    for p in pos.tolist() if code else ():
        data[4 * p:4 * p + 4] = bytes([0xE6, 0xF0 | (p & 0xF), 0xFF, 0xFF])
    if vectors:
        _c16x_vectors(data)
    return data


def _c16x_vectors(data, slots=range(128)):
    # Trap/interrupt vector table: jmps seg,addr (FA seg addr16) per 4-byte slot (MS43: 128 of 128).
    for k in slots:
        data[4 * k:4 * k + 4] = bytes([0xFA, 0x00, (0x40 + 8 * k) & 0xFE, 0x20])


def tricore_image(size=SIZE, seed=7):
    h = _halfwords(size // 2, seed)
    _sprinkle(h, 0x9000, 120, seed + 1)                        # ret (16-bit)
    _sprinkle(h, 0x0091, 650, seed + 2, mask=0x00FF)           # movh.a opcode byte
    return bytearray(h.tobytes())


def _table(rows, cols, base, step_r, step_c):
    return np.array([[base + step_r * r + step_c * c + (r * c) % 3 for c in range(cols)] for r in range(rows)])


# --- architecture -------------------------------------------------------------------------------------------


def test_each_architecture_needs_and_gets_two_agreeing_signs():
    assert detect_architecture(bytes(arm_image())).name == ARM
    assert detect_architecture(bytes(avr_image())).name == AVR
    assert detect_architecture(bytes(c16x_image())).name == C16X
    assert detect_architecture(bytes(tricore_image())).name == TRICORE


def test_one_sign_alone_is_not_enough():
    # Valid vector table but no Thumb code, Thumb density without vector table.
    assert detect_architecture(bytes(arm_image(thumb=False))).name == UNKNOWN
    assert detect_architecture(bytes(arm_image(vectors=False))).name == UNKNOWN
    # C16x moves without rets: a single opcode pattern.
    h = _halfwords(SIZE // 2, 11)
    data = bytearray(h.tobytes())
    for p in range(16, SIZE // 4, 64):
        data[4 * p:4 * p + 4] = bytes([0xE6, 0xF4, 0xFF, 0xFF])
    assert detect_architecture(bytes(data)).name == UNKNOWN


# --- C16x: trap vector table AND code density (1.19.1, final review) -----------------------------------------


def _lookup_sequences(data, count, start=0x2000, step=0x40):
    # Bosch ME7 lookup call: mov R12..R15,#imm16 (E6 FC.. E6 FD.. E6 FE.. E6 FF..).
    for k in range(count):
        at = start + k * step
        data[at:at + 16] = bytes([0xE6, 0xFC, 0x00, 0x50, 0xE6, 0xFD, 0x02, 0x00,
                                  0xE6, 0xFE, 0x00, 0x48, 0xE6, 0xFF, 0x02, 0x00])
    return data


def test_c16x_needs_vector_table_and_code_density():
    arch = detect_architecture(bytes(c16x_image()))
    assert arch.name == C16X
    assert arch.evidence[0].startswith('128 Trap-Vektoren (jmps)')
    assert arch.evidence[1].startswith('C16x-Code: rets')
    # Each sign alone is one sign: vector table without code, code without vector table.
    assert detect_architecture(bytes(c16x_image(code=False))).name == UNKNOWN
    assert detect_architecture(bytes(c16x_image(vectors=False))).name == UNKNOWN


def test_lookup_like_sequences_alone_are_not_c16x():
    # 59f355d: >= 20 such sequences alone made an image C16x. They are moves of the
    # same mov Rw,#imm16 family as the density sign: no second independent sign.
    for base in (bytearray(_rng(8).integers(0, 256, SIZE, dtype=np.uint8).tobytes()), bytearray(SIZE)):
        data = _lookup_sequences(base, 120)
        arch = detect_architecture(bytes(data))
        assert arch.signs['c16x_lookups'] == 120
        assert arch.name == UNKNOWN
        found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
        assert not [m for m in found if m.evidence_tier == 'Code-Beleg']
    # On a C16x image the sequences change nothing about the decision or its evidence.
    plain, more = detect_architecture(bytes(c16x_image())), detect_architecture(bytes(_lookup_sequences(c16x_image(), 120)))
    assert plain.name == more.name == C16X
    assert not any('Aufrufsequenzen' in e for e in more.evidence)


def test_random_c16x_sequences_in_other_code_are_not_c16x():
    def with_c16x_noise(data, seed):
        # Chance rets/mov opcodes and lookup sequences at C16x density, but no trap vectors.
        h = np.frombuffer(bytes(data), np.uint16).copy()
        _sprinkle(h, 0x00DB, 200, seed)
        noisy = bytearray(h.tobytes())
        for p in _rng(seed + 1).choice(np.arange(256, SIZE // 4 - 1), 800, replace=False).tolist():
            noisy[4 * p:4 * p + 4] = bytes([0xE6, 0xF0 | (p & 0xF), 0xFF, 0xFF])
        return _lookup_sequences(noisy, 30, start=0x1C000, step=0x20)
    for build, name in ((arm_image, ARM), (avr_image, AVR), (tricore_image, TRICORE)):
        arch = detect_architecture(bytes(with_c16x_noise(build(), 31)))
        assert arch.name == name, (name, arch.describe())
        assert C16X not in arch.conflicts


def test_calibration_and_damaged_c16x_images_are_unknown():
    smooth = bytearray(np.tile(_table(16, 16, 20, 3, 2).astype(np.uint8).ravel(), SIZE // 256).tobytes())
    assert detect_architecture(bytes(smooth)).name == UNKNOWN
    assert detect_architecture(bytes(_lookup_sequences(smooth, 40))).name == UNKNOWN
    full = bytes(c16x_image())
    assert detect_architecture(full[0x200:]).name == UNKNOWN    # vector table cut off
    erased = bytearray(full)
    erased[:0x200] = b'\xff' * 0x200                            # erased boot sector
    assert detect_architecture(bytes(erased)).name == UNKNOWN
    assert detect_architecture(full[:0x800]).name == UNKNOWN    # too short to judge


def test_random_calibration_and_tiny_images_are_unknown():
    assert detect_architecture(_rng(1).integers(0, 256, SIZE, dtype=np.uint8).tobytes()).name == UNKNOWN
    smooth = np.tile(_table(16, 16, 20, 3, 2).astype(np.uint8).ravel(), SIZE // 256).tobytes()
    assert detect_architecture(smooth).name == UNKNOWN
    assert detect_architecture(b'').name == UNKNOWN
    assert detect_architecture(bytes(arm_image())[:100]).name == UNKNOWN


def test_conflicting_signs_give_unknown_with_reason():
    # Full ARM and full C16x signs in one image: no decoder may run.
    h = np.frombuffer(bytes(arm_image()), np.uint16).copy()
    _sprinkle(h, 0x00DB, 200, 21)
    data = bytearray(h.tobytes())
    for p in range(64, SIZE // 4, 8):
        data[4 * p:4 * p + 4] = bytes([0xE6, 0xF0 | (p & 0xF), 0xFF, 0xFF])
    _c16x_vectors(data, range(16, 128))                         # after the 16 Cortex-M words
    arch = detect_architecture(bytes(data))
    assert arch.name == UNKNOWN
    assert set(arch.conflicts) == {ARM, C16X}
    assert 'widersprüchliche Belege' in arch.describe()


def test_truncated_or_damaged_firmware_does_not_raise_and_falls_back_to_unknown():
    full = bytes(arm_image())
    assert detect_architecture(full[256:]).name == UNKNOWN      # vector table cut off
    damaged = bytearray(full)
    damaged[0:4] = b'\xff\xff\xff\xff'                          # erased stack pointer
    assert arm_vector_table(bytes(damaged)) is None
    assert detect_architecture(bytes(damaged)).name == UNKNOWN
    odd = full[:SIZE - 3]                                       # odd length
    assert detect_architecture(odd).name == ARM
    scan_calibration_candidates(BinaryImage(odd), use_definitions=False)


# --- code evidence only on the established architecture ------------------------------------------------------


def _with_c16x_references(data, tables_at=0x15000):
    a = _table(6, 4, 10, 4, 2).astype(np.uint8)
    b = _table(6, 4, 34, 4, 2).astype(np.uint8)
    data[tables_at:tables_at + 24] = a.tobytes()
    data[tables_at + 24:tables_at + 48] = b.tobytes()
    code = b''
    for addr in (tables_at, tables_at + 24, tables_at + 48):
        code += bytes([0xE6, 0xF4, addr >> 14, 0]) + bytes([0xE6, 0xF5, addr & 0xFF, (addr >> 8) & 0x3F])
    data[0x100:0x100 + len(code)] = code
    return data


def test_c16x_moves_in_arm_code_give_no_code_evidence():
    data = _with_c16x_references(arm_image())
    assert detect_architecture(bytes(data)).name == ARM
    # The decoder itself still reads the bytes as C16x page/offset loads ...
    assert 0x15000 in c16x_reference_anchors(bytes(data), 0x10000, 0x20000)
    legacy = scan_structures(BinaryImage(bytes(data)), 0x10000, 0x20000)
    assert any(m.record_layout == REFERENCE_LAYOUT for m in legacy)
    # ... but the application scan does not apply it to ARM code.
    gated = scan_structures(BinaryImage(bytes(data)), 0x10000, 0x20000,
                            architecture=detect_architecture(bytes(data)))
    assert not any(m.record_layout == REFERENCE_LAYOUT for m in gated)
    found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
    assert not [m for m in found if m.evidence_tier == 'Code-Beleg']


def test_c16x_code_evidence_is_kept_on_c16x_images():
    data = _with_c16x_references(c16x_image())
    assert detect_architecture(bytes(data)).name == C16X
    gated = {m.offset: m for m in scan_structures(BinaryImage(bytes(data)), 0x10000, 0x20000,
                                                  architecture=detect_architecture(bytes(data)))}
    assert gated[0x15000].record_layout == REFERENCE_LAYOUT
    assert (gated[0x15000].rows, gated[0x15000].cols) == (6, 4)
    found = {m.offset: m for m in scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)}
    assert found[0x15000].evidence_tier == 'Code-Beleg'


def test_c16x_moves_in_avr_and_unknown_images_give_no_code_evidence():
    for base in (avr_image(), bytearray(_rng(4).integers(0, 256, SIZE, dtype=np.uint8).tobytes())):
        data = _with_c16x_references(base)
        found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
        assert not [m for m in found if m.record_layout == REFERENCE_LAYOUT]


def _with_denso_descriptors(data, at=0x10000, n_tables=6):
    # SH-2 (Denso) descriptors nx, ny, &X, &Y, &Z, type (big endian), as in test_structure_families.
    for k in range(n_tables):
        x_ptr = at + 0x1000 + 0x200 * k
        y_ptr, z_ptr = x_ptr + 16, x_ptr + 36
        data[x_ptr:y_ptr] = struct.pack('>4f', 0, 1000, 2000, 3000)
        data[y_ptr:z_ptr] = struct.pack('>5f', 10, 20, 40, 80, 160)
        z = np.add.outer(np.arange(5) * 300, np.arange(4) * 70).astype('>u2') + 100 * k
        data[z_ptr:z_ptr + z.nbytes] = z.tobytes()
        d = at + 0x200 + 0x20 * k
        data[d:d + 24] = struct.pack('>HHIIIBxxxf', 4, 5, x_ptr, y_ptr, z_ptr, 0x08, 1.)
    return data


def test_generic_and_sh2_decoders_run_only_without_established_architecture():
    # 1.19.1 review: HC11/8051/68k address loads and SH-2 descriptors are decoded only on
    # unknown images; on an established architecture their chance hits are no evidence.
    table = 0x10000 + 0x1000 + 36
    unknown = bytes(_with_denso_descriptors(bytearray(_rng(12).integers(0, 256, SIZE, dtype=np.uint8).tobytes())))
    assert detect_architecture(unknown).name == UNKNOWN
    found = {m.offset: m for m in scan_structures(BinaryImage(unknown), 0x11000, 0x12000, architecture=detect_architecture(unknown))}
    assert found[table].record_layout == POINTER_LAYOUT
    for build in (arm_image, avr_image, c16x_image, tricore_image):
        data = bytes(_with_denso_descriptors(build()))
        arch = detect_architecture(data)
        assert arch.known, build.__name__
        legacy = {m.offset: m for m in scan_structures(BinaryImage(data), 0x11000, 0x12000)}
        assert legacy[table].record_layout == POINTER_LAYOUT          # the decoder itself still reads them
        gated = scan_structures(BinaryImage(data), 0x11000, 0x12000, architecture=arch)
        assert not [m for m in gated if m.record_layout in (POINTER_LAYOUT, 'candidate:code-reference-generic')]


def test_scan_reports_the_architecture_decision():
    diag = {}
    scan_calibration_candidates(BinaryImage(bytes(arm_image())), use_definitions=False, diagnostics=diag)
    assert diag['architecture'].startswith('ARM: Cortex-M-Vektortabelle')


# --- text ---------------------------------------------------------------------------------------------------


def _string_slots(names, slot=16):
    return b''.join(n.encode() + bytes(slot - len(n)) for n in names)


def test_fixed_width_string_list_is_text():
    raw = _string_slots([f'TLE8888.INJ{k}' for k in range(1, 13)])
    data = bytes(64) + raw + bytes(64)
    spans = text_spans(data)
    assert classify(64, 64 + len(raw), spans, EMPTY) == 'text'
    # Packed NUL-terminated strings (rusEFI "Injector Second Stage n").
    packed = b''.join(f'Injector Second Stage {k}'.encode() + b'\0' for k in range(1, 13))
    data = bytes(32) + packed + bytes(32)
    assert classify(32, 32 + len(packed), text_spans(data), EMPTY) == 'text'


def test_calibration_bytes_that_happen_to_be_printable_are_not_text():
    # u8 table 0x30..0x7A, smooth, no NUL terminators: printable but not text.
    t = _table(16, 16, 0x30, 3, 1).clip(0x20, 0x7E).astype(np.uint8).tobytes()
    data = bytes(16) + t + bytes(16)
    assert classify(16, 16 + len(t), text_spans(data), EMPTY) == ''
    # Rows of ascending letters separated by 0 (first column 0): ramps, not words.
    rows = b''.join(bytes([0]) + bytes(range(0x41 + r, 0x41 + r + 15)) for r in range(12))
    data = bytes(16) + rows + bytes(16)
    assert classify(16, 16 + len(rows), text_spans(data), EMPTY) == ''
    assert not is_text_string(b'ABCDEFGHIJKLMNO')
    assert is_text_string(b'Injector Second Stage 4')


def test_isolated_string_inside_table_does_not_make_the_table_text():
    t = bytearray(_table(16, 16, 20, 3, 2).astype(np.uint8).tobytes())
    t[100:108] = b'abcXYZq\0'
    data = bytes(t)
    assert classify(0, len(data), text_spans(data), EMPTY) == ''


def test_text_finds_are_not_offered_as_maps():
    data = arm_image()
    names = _string_slots([f'TLE8888.INJ{k}' for k in range(1, 29)])
    data[0x18000:0x18000 + len(names)] = names
    found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
    hit = [m for m in found if m.offset < 0x18000 + len(names) and 0x18000 < m.offset + m.length]
    spans = text_spans(bytes(data))
    assert not [m for m in hit if classify(m.offset, m.offset + m.length, spans, EMPTY) == 'text']


# --- pointer tables -------------------------------------------------------------------------------------------


def _pointer_table(n, start=0x08010001, step=0x34):
    return struct.pack(f'<{n}I', *[start + step * k for k in range(n)])


def test_arm_pointer_table_is_recognised():
    data = arm_image()
    p = _pointer_table(32)
    data[0x10000:0x10000 + len(p)] = p
    arch = detect_architecture(bytes(data))
    spans = pointer_spans(bytes(data), arch)
    assert classify(0x10000, 0x10000 + len(p), EMPTY, spans) == 'pointer'
    # An unaligned candidate over the same table is covered as well (FOME: 106x4 s8 at an odd offset).
    assert classify(0x10001, 0x10000 + len(p) - 3, EMPTY, spans) == 'pointer'


def test_pointer_tables_need_a_known_pointer_format():
    data = bytearray(_rng(9).integers(0, 256, SIZE, dtype=np.uint8).tobytes())
    p = _pointer_table(32)
    data[0x10000:0x10000 + len(p)] = p
    assert len(pointer_spans(bytes(data), detect_architecture(bytes(data)))) == 0
    data = c16x_image()
    data[0x10000:0x10000 + len(p)] = p
    assert len(pointer_spans(bytes(data), detect_architecture(bytes(data)))) == 0


def test_tables_with_pointer_like_values_are_not_pointer_tables():
    data = arm_image()
    arch = detect_architecture(bytes(data))
    # u16 Q11 factor table near 1.0 (0x0800): words 0x07F8_0803 ... inside the flash window.
    q11 = (2048 + _table(8, 8, -8, 2, 1)).astype('<u2').tobytes()
    data[0x10000:0x10000 + len(q11)] = q11
    # u8 table of small integers whose last column is 8: words 0x08_05_07_06.
    u8 = np.array([[5 + (r + c) % 4 for c in range(3)] + [8] for r in range(16)], np.uint8).tobytes()
    data[0x11000:0x11000 + len(u8)] = u8
    # u32 table of plain values.
    u32 = struct.pack('<16I', *[1000 * k for k in range(16)])
    data[0x12000:0x12000 + len(u32)] = u32
    spans = pointer_spans(bytes(data), arch)
    for lo, n in ((0x10000, len(q11)), (0x11000, len(u8)), (0x12000, len(u32))):
        assert classify(lo, lo + n, EMPTY, spans) == ''


def test_pointer_finds_are_not_offered_as_maps_on_arm():
    data = arm_image()
    p = _pointer_table(96, start=0x08070985, step=0x0C)        # sorted, smooth when read as bytes
    data[0x18000:0x18000 + len(p)] = p
    found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
    spans = pointer_spans(bytes(data), detect_architecture(bytes(data)))
    assert not [m for m in found if classify(m.offset, m.offset + m.length, EMPTY, spans) == 'pointer']


def test_real_table_next_to_text_and_pointers_survives():
    data = arm_image()
    names = _string_slots([f'TLE8888.INJ{k}' for k in range(1, 13)])
    p = _pointer_table(24)
    t = _table(12, 16, 40, 6, 3).astype('<u2').tobytes()
    data[0x14000:0x14000 + len(names)] = names
    data[0x14000 + len(names):0x14000 + len(names) + len(t)] = t
    at = 0x14000 + len(names) + len(t)
    data[at:at + len(p)] = p
    found = scan_calibration_candidates(BinaryImage(bytes(data)), use_definitions=False)
    start = 0x14000 + len(names)
    assert any(m.offset <= start + 32 and m.offset + m.length >= start + len(t) - 32 and m.dtype == 'u16'
               for m in found)


def test_vector_table_with_reserved_words_is_a_pointer_region():
    data = arm_image()
    words = [0x20001000] + [0x08000201 + 0x10 * k for k in range(97)]
    words[7], words[8] = 0x9D265A2D, 0x4E98                     # image checksum and size (FOME/ChibiOS)
    data[:4 * len(words)] = struct.pack(f'<{len(words)}I', *words)
    arch = detect_architecture(bytes(data))
    spans = pointer_spans(bytes(data), arch)
    assert classify(0x1A, 0x1D, EMPTY, spans) == 'pointer'      # FOME: count-axis find inside the table
    assert classify(0, 4 * len(words), EMPTY, spans) == 'pointer'


def _record(axis_x, axis_y, rows=4, cols=4):
    from ecu_studio.core.model import MapDefinition
    m = MapDefinition(name='r', offset=axis_y[0] + 4, rows=rows, cols=cols, dtype='u8', source='heuristic',
                      record_layout='candidate:nx,ny,x,y,z')
    m.axis_x_offset, m.axes_x = axis_x
    m.axis_y_offset, m.axes_y = axis_y
    return m


def test_header_record_whose_axes_are_pointers_is_rejected_but_real_axes_stay():
    from ecu_studio.core.region_classes import address_word_spans
    from ecu_studio.core.scoped_scan import _axes_are_pointers
    data = arm_image()
    # rusEFI-like table object: CCM pointer, nx=4/ny=4, then three flash pointers.
    obj = struct.pack('<IHHIII', 0x10002764, 4, 4, 0x08011011, 0x08011027, 0x080189AA)
    data[0x15000:0x15000 + len(obj)] = obj
    addresses = address_word_spans(bytes(data), detect_architecture(bytes(data)))
    fake = _record((0x15008, [0x11, 0x10, 0x01, 0x08]), (0x1500C, [0x27, 0x10, 0x01, 0x08]))
    assert _axes_are_pointers(fake, addresses)
    # Real record: ascending u8 axes 8,10,16,17 and 20,40,60,80 never read as addresses.
    real = struct.pack('<HH8B', 4, 4, 8, 10, 16, 17, 20, 40, 60, 80) + _table(4, 4, 30, 5, 2).astype(np.uint8).tobytes()
    data[0x16000:0x16000 + len(real)] = real
    addresses = address_word_spans(bytes(data), detect_architecture(bytes(data)))
    ok = _record((0x16004, [8, 10, 16, 17]), (0x16008, [20, 40, 60, 80]))
    assert not _axes_are_pointers(ok, addresses)
    # Only one axis on an address word: not enough.
    half = _record((0x15008, [0x11, 0x10, 0x01, 0x08]), (0x16008, [20, 40, 60, 80]))
    assert not _axes_are_pointers(half, addresses)
