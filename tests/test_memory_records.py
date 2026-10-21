import pytest
from ecu_studio.formats.records import parse_memory_text


def ihex(address,kind,data=b''):
    raw=bytes((len(data),(address>>8)&255,address&255,kind))+data
    return ':'+(raw+bytes(((-sum(raw))%256,))).hex().upper()


def srec(kind,address,payload=b''):
    width={'1':2,'2':3,'3':4,'5':2,'7':4,'8':3,'9':2}[kind]
    body=address.to_bytes(width,'big')+payload
    raw=bytes((len(body)+1,))+body
    return 'S'+kind+(raw+bytes(((~sum(raw))&255,))).hex().upper()


def test_intel_hex_segment_gaps_and_coverage():
    lines=[ihex(0,4,b'\x00\x12'), ihex(0x0100,0,b'\x01\x02'),
           ihex(0x0104,0,b'\x03'),ihex(0,5,b'\x00\x12\x01\x00'),ihex(0,1)]
    obj=parse_memory_text('\n'.join(lines))
    assert obj.start==0x120100 and obj.end==0x120105
    assert obj.gap_bytes==2 and obj.payload_bytes==3
    assert obj.entry_address==0x120100
    assert obj.segments==[(0x120100,0x120102),(0x120104,0x120105)]
    with pytest.raises(ValueError,match='Adresslücken'):obj.to_binary()
    assert obj.to_binary(fill=255)==b'\x01\x02\xFF\xFF\x03'


def test_intel_segment_mode_and_checksums():
    raw='\n'.join((ihex(0,2,b'\x12\x34'),ihex(0x10,0,b'\xFA'),ihex(0,1)))
    parsed=parse_memory_text(raw)
    assert parsed.start==0x12350 and parsed.to_binary()==b'\xFA'
    with pytest.raises(ValueError,match='Prüfsumme'):
        parse_memory_text(raw.replace('FA','FB'))
    with pytest.raises(ValueError,match='EOF'):
        parse_memory_text(ihex(0,0,b'\x10'))
    with pytest.raises(ValueError,match='Überlapp'):
        parse_memory_text('\n'.join([ihex(0,0,b'12'),ihex(1,0,b'2'),ihex(0,1)]))


def test_motorola_srec_multi_address_and_counts():
    raw='\n'.join((srec('2',0x801000,b'\x10\x20'),
                   srec('2',0x801002,b'\x30'),srec('5',2),srec('8',0x801000)))
    parsed=parse_memory_text(raw)
    assert parsed.format=='Motorola S-Record'
    assert parsed.to_binary()==b'\x10\x20\x30'
    assert parsed.entry_address==0x801000
    with pytest.raises(ValueError,match='Anzahl'):
        parse_memory_text(raw.replace(srec('5',2),srec('5',3)))
    with pytest.raises(ValueError,match='Prüfsumme'):
        parse_memory_text(raw.replace(srec('5',2), 'S503000200'))


def test_dos_eof_marker_after_end_record_is_accepted_but_real_trailing_data_is_not():
    # Regression: real EDC16 HEX files from Windows tools end with 0x1A and were refused.
    import pytest
    from ecu_studio.formats.records import parse_memory_text
    body = ':0400000001020304F2\r\n:00000001FF\r\n'
    assert parse_memory_text(body + '\x1a').payload_bytes == 4
    with pytest.raises(ValueError, match='nach Intel-HEX-EOF'):
        parse_memory_text(body + ':0400000001020304F2\r\n')
    srec = 'S107000001020304EE\r\nS9030000FC\r\n'
    assert parse_memory_text(srec + '\x1a').payload_bytes == 4
