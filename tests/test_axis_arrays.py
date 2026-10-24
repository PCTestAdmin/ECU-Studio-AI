import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.axis_arrays import scan_count_axes, AXIS_LAYOUT
from ecu_studio.core.structure_scan import scan_structures, REFERENCE_LAYOUT
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def _u8_axis(values):
    return bytes([len(values)])+bytes(values)


def _u16_axis(values):
    return len(values).to_bytes(2,'little')+np.array(values,'<u2').tobytes()


def _mov(addr):
    """MOV R4,#page ; MOV R5,#offset (C16x)."""
    return bytes([0xE6,0xF4,addr>>14,0,0xE6,0xF5,addr&0xFF,(addr>>8)&0x3F])


def test_chained_count_prefixed_axes_are_found_in_both_widths():
    data=bytearray(np.random.default_rng(5).integers(0,256,4096,dtype=np.uint8).tobytes())
    chain=(_u8_axis([10,20,40,80,120,160])+_u8_axis([0,25,50,75])+_u16_axis([500,1000,2000,4000,6000])
           +_u16_axis([100,200,300]))
    data[0x400:0x400+len(chain)]=chain
    found=scan_count_axes(bytes(data))
    got={(a.header,a.count,a.width,a.values) for a in found}
    assert (0x400,6,1,(10,20,40,80,120,160)) in got
    assert (0x407,4,1,(0,25,50,75)) in got
    assert (0x40C,5,2,(500,1000,2000,4000,6000)) in got


def test_isolated_or_random_arrays_are_not_axes():
    noise=np.random.default_rng(121).integers(0,256,64*1024,dtype=np.uint8).tobytes()
    assert scan_count_axes(noise)==[]
    data=bytearray(4096)
    data[0x100:0x107]=_u8_axis([1,5,9,30,31,40])   # single array, no chain neighbour
    assert scan_count_axes(bytes(data))==[]


def test_axis_pointer_cannot_wrap_from_negative_file_offset():
    from ecu_studio.core.axis_arrays import axis_at
    # A negative pointer previously read the final byte as the count and then
    # treated the first four bytes as an axis: a fabricated wraparound record.
    data = bytes([10, 20, 30, 40, 7, 8, 9, 4])
    for header in (-1, -9, len(data), True, 1.5):
        assert axis_at(data, header) is None


def _image_with_lookup(gap_y_x):
    """Calibration page with a Y/X axis chain and an 8x6 table, plus code that
    loads Y, then X, then the table, like Siemens MS43 lookups."""
    data=bytearray(0x80000)
    y=[5,10,20,30,40,50,60,70]; x=[100,130,160,190,220,250]
    axes=_u8_axis(y)+_u8_axis(x)+_u8_axis([1,2,3,4])+_u8_axis([2,4,6])
    data[0x74000:0x74000+len(axes)]=axes
    t=np.array([[10+3*r+5*c for c in range(6)] for r in range(8)],np.uint8)
    data[0x75000:0x75000+t.size]=t.tobytes()
    data[0x75000+t.size:0x75100]=bytes(np.random.default_rng(1).integers(0,256,0x100-t.size,dtype=np.uint8))
    code=_mov(0x74000)+bytes(gap_y_x)+_mov(0x74009)+_mov(0x75000)
    data[0x200:0x200+len(code)]=code
    return BinaryImage(bytes(data))


def test_code_loaded_axes_fix_table_shape_and_values():
    found={m.offset:m for m in scan_structures(_image_with_lookup(8),0x70000,0x80000)}
    m=found[0x75000]
    assert (m.rows,m.cols,m.dtype)==(8,6,'u8')
    assert m.axes_y==[5,10,20,30,40,50,60,70] and m.axes_x==[100,130,160,190,220,250]
    assert m.record_layout==REFERENCE_LAYOUT and not m.verified and m.kind=='Unbekannt'
    # The breakpoint arrays themselves are not reported as 2-D tables.
    assert not any(0x74000<=o<0x74018 for o in found)


def test_scoped_scan_reports_axes_as_one_line_candidates():
    out=scan_calibration_candidates(_image_with_lookup(8),use_definitions=False)
    axes=[m for m in out if m.record_layout==AXIS_LAYOUT]
    assert {(m.offset,m.rows,m.cols) for m in axes}>={(0x74001,1,8),(0x7400A,1,6)}
    assert any(m.offset==0x75000 and (m.rows,m.cols)==(8,6) for m in out)


def test_me7_style_lookup_call_names_table_and_axes():
    # MOV R12/R13 = table, MOV R14/R15 = axis data [nX][X..][nY][Y..] (Bosch ME7 style)
    from ecu_studio.core.structure_scan import lookup_descriptors
    data=bytearray(0x20000)
    axes=_u8_axis([0,10,20,30,40,50])+_u8_axis([5,15,25,35])
    data[0x12000:0x12000+len(axes)]=axes
    t=np.array([[20+4*r+7*c for c in range(6)] for r in range(4)],np.uint8)
    data[0x18000:0x18000+t.size]=t.tobytes()
    def mov(reg,value):return bytes([0xE6,0xF0|reg,value&0xFF,value>>8])
    code=mov(12,0x18000&0x3FFF)+mov(13,0x18000>>14)+mov(14,0x12000&0x3FFF)+mov(15,0x12000>>14)
    data[0x100:0x100+len(code)]=code
    found=lookup_descriptors(bytes(data),0x10000,0x20000)
    x,y=found[0x18000]
    assert (x.count,y.count)==(6,4) and x.values==(0,10,20,30,40,50)
    m={s.offset:s for s in scan_structures(BinaryImage(bytes(data)),0x10000,0x20000)}[0x18000]
    assert (m.rows,m.cols)==(4,6) and m.axes_y==[5,15,25,35]
