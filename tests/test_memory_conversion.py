import hashlib
import json
import pytest
from ecu_studio.formats.importer import convert_to_binary, describe_memory_image
from ecu_studio.formats.records import parse_memory_text


def ihex(addr, typ, data=b''):
    x=bytes([len(data),(addr>>8)&255,addr&255,typ])+data
    return ':'+(x+bytes([(-sum(x))%256])).hex().upper()


def test_conversion_requires_explicit_gap_fill_and_sidecar(tmp_path):
    inp=tmp_path/'reference.hex'
    inp.write_text('\n'.join([
        ihex(0,4,b'\x00\x80'), ihex(0x20,0,b'\x10\x20'),
        ihex(0x24,0,b'\x30'), ihex(0,1)]), encoding='ascii')
    dest=tmp_path/'converted.bin'
    with pytest.raises(ValueError,match='Füllbyte'):
        convert_to_binary(inp,dest)
    assert not dest.exists()
    res=convert_to_binary(inp,dest,fill=255)
    assert dest.read_bytes()==b'\x10\x20\xff\xff\x30'
    info=json.loads(res.manifest.read_text(encoding='utf-8'))
    assert info['base_address']==0x800020
    assert info['segments']==[{'ecu_start':0x800020,'ecu_end_exclusive':0x800022,'binary_offset':0},
                               {'ecu_start':0x800024,'ecu_end_exclusive':0x800025,'binary_offset':4}]
    assert info['filler']==255
    assert info['binary_sha256']==hashlib.sha256(dest.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):convert_to_binary(inp,dest,fill=255)


def test_conversion_prevents_overwrites_and_source_equals_destination(tmp_path):
    p=tmp_path/'same.hex'
    p.write_text('\n'.join((ihex(0,0,b'\x01'),ihex(0,1))),encoding='ascii')
    with pytest.raises(ValueError,match='identisch'):convert_to_binary(p,p)
    out=tmp_path/'result.bin'
    sidecar=tmp_path/'result.bin.memory.json'
    sidecar.write_text('sentinel')
    with pytest.raises(FileExistsError):convert_to_binary(p,out)
    assert sidecar.read_text()=='sentinel'
    assert not out.exists()


def test_memory_info_is_explicit_about_sparse_data():
    obj=parse_memory_text('\n'.join((ihex(0,0,b'\x01'),ihex(3,0,b'\x02'),ihex(0,1))))
    desc=describe_memory_image(obj)
    assert desc['gap_bytes']==2
    assert desc['end_exclusive']==4


def test_verified_memory_segments_reused_for_a2l_link(tmp_path):
    from ecu_studio.formats.importer import read_import_segments
    inp=tmp_path/'input.hex'
    inp.write_text('\n'.join([ihex(0,4,b'\x00\x80'),ihex(0x10,0,b'\x01\x02'),
                               ihex(0x20,0,b'\x03'),ihex(0,1)]),encoding='ascii')
    out=tmp_path/'converted.bin'
    convert_to_binary(inp,out,fill=255)
    seg=read_import_segments(out)
    assert [(s.ecu_start,s.ecu_end,s.file_start) for s in seg]==[(0x800010,0x800011,0),(0x800020,0x800020,16)]
    out.write_bytes(out.read_bytes()[:-1]+b'\x04')
    with pytest.raises(ValueError,match='SHA-256'):read_import_segments(out)


def test_memory_segment_sidecar_rejects_bad_positions(tmp_path):
    from ecu_studio.formats.importer import read_import_segments
    inp=tmp_path/'input.hex'
    inp.write_text('\n'.join([ihex(0,0,b'\x01'),ihex(0,1)]),encoding='ascii')
    out=tmp_path/'converted.bin'
    convert_to_binary(inp,out)
    sidecar=out.with_name(out.name+'.memory.json')
    data=json.loads(sidecar.read_text(encoding='utf-8'))
    data['segments'][0]['binary_offset']=999
    sidecar.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='Inkonsistenter'):read_import_segments(out)
