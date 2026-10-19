from ecu_studio.core.extended_demo import generate_extended_demo, DEMO_MAPS
from ecu_studio.core.a2l import read_a2l
from ecu_studio.core.model import BinaryImage


def test_synthetic_a2l_links_many_types(tmp_path):
    f,a=generate_extended_demo(str(tmp_path))
    image=BinaryImage.from_file(str(f))
    catalog=read_a2l(str(a))
    assert len(catalog.characteristics)==14==len(DEMO_MAPS)
    result=catalog.link(file_size=image.size,ecu_anchor=0x800000,file_anchor=0)
    assert len(result.maps)==14
    assert not result.unsupported and not result.out_of_range
    assert all(not m.verified for m in result.maps)
    assert len({m.kind for m in result.maps})>=10
    assert next(m for m in result.maps if m.name=='DIAGNOSTIC_THRESHOLD').length==4
    assert next(m for m in result.maps if m.name=='IDLE_SPEED_REQUEST').rows==1
    for m in result.maps:
        assert image.raw_value(m,0,0) is not None
