import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.structure_scan import (c16x_reference_anchors, scan_structures, anchored_fit,
                                            REFERENCE_LAYOUT, PITCH_LAYOUT)
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def _table(rows, cols, base, step_r, step_c):
    return np.array([[base+step_r*r+step_c*c+(r*c)%3 for c in range(cols)] for r in range(rows)])


def _noise(n, seed=7):
    return bytearray(np.random.default_rng(seed).integers(0,256,n,dtype=np.uint8).tobytes())


def test_row_pitch_finds_unlisted_shape_at_exact_offset():
    data=_noise(8192)
    t=_table(7,9,20,11,5).astype(np.uint8)   # 7x9 is not one of the fixed legacy grids
    data[0x400:0x400+t.size]=t.tobytes()
    found=scan_structures(BinaryImage(bytes(data)))
    hit=[m for m in found if m.offset==0x400]
    assert hit and (hit[0].rows,hit[0].cols,hit[0].dtype)==(7,9,'u8')
    assert hit[0].record_layout==PITCH_LAYOUT and not hit[0].verified and hit[0].kind=='Unbekannt'


def test_little_endian_u16_table_is_not_misread_as_bytes():
    # Between unrelated byte data and erased flash, as in calibration windows.
    data=_noise(8192,seed=3)
    data[0x700:0x900]=b'\xff'*0x200
    t=_table(8,6,300,15,30).astype('<u2')   # each row restarts low: row-wrap jump
    data[0x800:0x800+t.nbytes]=t.tobytes()
    hit=[m for m in scan_structures(BinaryImage(bytes(data))) if m.offset<0x800+t.nbytes and 0x800<m.offset+m.length]
    # Pitch may come out as a multiple (two rows merged) without code references;
    # storage width and byte order must still be right.
    assert hit and all((m.dtype,m.endian)==('u16','little') for m in hit)
    assert all(m.cols%6==0 for m in hit)


def test_monotone_plane_without_row_wrap_is_found_but_pitch_is_ambiguous():
    # Rows continuing each other (e.g. MAF-like grids) fit many pitches; only the
    # region is asserted. Without axes or code references the width is unknowable.
    data=_noise(8192,seed=3)
    t=_table(8,6,300,40,9).astype('<u2')
    data[0x800:0x800+t.nbytes]=t.tobytes()
    found=scan_structures(BinaryImage(bytes(data)))
    assert any(m.offset<0x800+t.nbytes and 0x800<m.offset+m.length and m.dtype=='u16' for m in found)


def test_c16x_page_offset_pair_yields_absolute_anchor():
    # MOV R4,#0x001D ; MOV R5,#0x59DC  -> page 0x1D, offset 0x19DC -> 0x759DC
    code=bytes.fromhex('E6F41D00')+bytes.fromhex('E6F5DC59')
    data=code+bytes(0x80000-len(code))
    assert c16x_reference_anchors(data,0x70000,0x80000)==[0x759DC]
    assert c16x_reference_anchors(data,0x40000,0x50000)==[]


def test_anchors_split_packed_tables_of_equal_width():
    # Two 6x4 tables back to back: rows of the second continue the first smoothly,
    # so only the code references reveal the boundary.
    a=_table(6,4,10,4,2).astype(np.uint8); b=_table(6,4,34,4,2).astype(np.uint8)
    data=bytearray(0x80000)
    data[0x75000:0x75018]=a.tobytes(); data[0x75018:0x75030]=b.tobytes()
    data[0x75030:0x75100]=_noise(0xD0)
    code=b''
    for addr in (0x75000,0x75018,0x75030):
        code+=bytes([0xE6,0xF4,addr>>14,0])+bytes([0xE6,0xF5,addr&0xFF,(addr>>8)&0x3F])
    data[0x100:0x100+len(code)]=code
    found={m.offset:m for m in scan_structures(BinaryImage(bytes(data)),0x70000,0x80000)}
    assert 0x75000 in found and 0x75018 in found
    assert (found[0x75000].rows,found[0x75000].cols)==(6,4)
    assert found[0x75000].record_layout==REFERENCE_LAYOUT
    assert anchored_fit(bytes(data),0x75018,0x75030)[1:3]==(6,4)


def test_random_and_constant_data_produce_no_structures():
    assert scan_structures(BinaryImage(bytes(_noise(32*1024,seed=121))))==[]
    assert scan_structures(BinaryImage(b'\xff'*4096))==[]
    assert scan_structures(BinaryImage(bytes(4096)))==[]


def test_structure_limit_zero_restores_legacy_pipeline():
    data=_noise(8192)
    t=_table(7,9,20,11,5).astype(np.uint8)
    data[0x400:0x400+t.size]=t.tobytes()
    legacy=scan_calibration_candidates(BinaryImage(bytes(data)),use_definitions=False,structure_limit=0)
    assert all(m.record_layout not in (REFERENCE_LAYOUT,PITCH_LAYOUT) for m in legacy)
    full=scan_calibration_candidates(BinaryImage(bytes(data)),use_definitions=False)
    assert any(m.offset==0x400 and (m.rows,m.cols)==(7,9) for m in full)


def test_data_mask_separates_smooth_calibration_blocks_from_code():
    from ecu_studio.core.data_regions import data_mask
    data=_noise(4096,seed=9)                      # code-like: erratic neighbours
    t=_table(16,16,30,6,4).astype(np.uint8)       # smooth calibration block
    data[0x800:0x900]=t.tobytes()
    mask=data_mask(bytes(data),block=256)
    assert mask[0x800:0x900].all()
    assert not mask[:0x800].any() and not mask[0x900:].any()
