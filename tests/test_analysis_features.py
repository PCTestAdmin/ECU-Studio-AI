import numpy as np
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.cpu_refs import detect_cpu
from ecu_studio.core.function_graph import build_function_graph, related_maps
from ecu_studio.core.signal_trace import trace_inputs, variable_table
from ecu_studio.core.axis_semantics import guess_axis


def _mov(reg,value):
    return bytes([0xE6,0xF0|reg,value&0xFF,value>>8])


def _ref(addr):
    return _mov(4,addr>>14)+_mov(5,addr&0x3FFF)


def test_hc11_top_mapped_image_is_detected_from_address_loads():
    rng=np.random.default_rng(2)
    data=bytearray(rng.integers(0,256,0x4000,dtype=np.uint8).tobytes())
    data[0x0000:0x0600]=np.repeat(np.arange(0,240,10,dtype=np.uint8),64)[:0x600].tobytes()   # smooth data
    code=bytearray()
    for k in range(40):
        code+=bytes([0xCE])+(0xC000+0x20*k).to_bytes(2,'big')+bytes([0x01])
    data[0x2000:0x2000+len(code)]=code
    data[-2:]=(0xE000).to_bytes(2,'big')                 # reset vector inside 0xC000..0xFFFF
    guess,targets=detect_cpu(bytes(data))
    assert guess and (guess.family,guess.base)==('HC11',0xC000)
    assert targets and all(t<0x600 for t in targets)


def test_pure_data_image_has_no_cpu():
    smooth=bytes(np.repeat(np.arange(0,250,5,dtype=np.uint8),82)[:4096])
    assert detect_cpu(smooth)==(None,set())


def _c16x_image():
    data=bytearray(0x80000)
    maps=[MapDefinition('A',0x74000,4,4,dtype='u8'),MapDefinition('B',0x74100,4,4,dtype='u8'),
          MapDefinition('C',0x74200,4,4,dtype='u8')]
    # routine 1 reads RAM 0xF100 then uses A and B; RET; routine 2 reads 0xF200 and uses C
    r1=bytes([0xF2,0xF4,0x00,0xF1])+_ref(0x74000)+bytes([0xF2,0xF4,0x00,0xF1])+_ref(0x74100)+b'\xCB\x00'
    r2=bytes([0xF2,0xF6,0x00,0xF2])+_ref(0x74200)+b'\xCB\x00'
    data[0x1000:0x1000+len(r1)+len(r2)]=r1+r2
    return BinaryImage(bytes(data)),maps


def test_function_graph_groups_tables_of_one_routine():
    image,maps=_c16x_image()
    graph=build_function_graph(image,maps,0x70000,0x80000)
    assert [sorted(g.members) for g in graph['groups']]==[[0,1]]
    assert related_maps(graph,0)['routine']==[1] and related_maps(graph,2)['routine']==[]


def test_signal_trace_finds_ram_inputs_before_lookup():
    image,maps=_c16x_image()
    traces=trace_inputs(image,maps,0x70000,0x80000)
    assert {r.address for r in traces[0]}=={0xF100}
    table=variable_table(traces)
    assert sorted(table[0xF100])==[0,1] and table[0xF200]==[2]


def test_axis_semantics_prefers_round_breakpoints():
    temp=[(t+48)/.75 for t in (-30,0,30,60,90)]          # MS4x temperature scaling
    assert guess_axis([round(v) for v in temp],1)[0].unit=='°C'
    rpm=[600,1000,1500,2000,3000,4000,5000,6000]
    assert guess_axis(rpm,2)[0].unit=='rpm'
