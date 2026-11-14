"""ASAP2 reading details that silently dropped objects before 1.21.0 (synthetic A2L only).

- Doubled quotes inside a string ("") are an escaped quote, not the end of the string.
- VAL_BLK sized with NUMBER (ASAP2 1.5) is a value block, not an object without size.
"""
from ecu_studio.core.a2l import TOKEN, parse_a2l, unquote

A2L = '''/begin PROJECT P "" /begin MODULE M ""
/begin MOD_COMMON "" BYTE_ORDER MSB_FIRST /end MOD_COMMON
/begin RECORD_LAYOUT W FNC_VALUES 1 UWORD ROW_DIR DIRECT /end RECORD_LAYOUT
/begin CHARACTERISTIC CWQUOTE
    "Ausgabe ""Km bei MIL on"" abschalten" VALUE 0x100 W 0 NO_COMPU_METHOD 0 1 /end CHARACTERISTIC
/begin CHARACTERISTIC CWSLASH "Ein \\"Zitat\\"" VALUE 0x102 W 0 NO_COMPU_METHOD 0 1 /end CHARACTERISTIC
/begin CHARACTERISTIC BLK15 "block" VAL_BLK 0x104 W 0 NO_COMPU_METHOD 0 65535
    NUMBER 4 /end CHARACTERISTIC
/begin CHARACTERISTIC BLK16 "block" VAL_BLK 0x10C W 0 NO_COMPU_METHOD 0 65535
    MATRIX_DIM 3 2 1 /end CHARACTERISTIC
/end MODULE /end PROJECT'''


def test_doubled_quote_stays_inside_the_string():
    tokens = [m.group(0) for m in TOKEN.finditer('A "x ""y"" z" B "" C')]
    assert tokens == ['A', '"x ""y"" z"', 'B', '""', 'C']
    assert unquote('"x ""y"" z"') == 'x "y" z'
    assert unquote('"a\\"b"') == 'a"b'
    assert unquote('""') == ''


def test_objects_with_quoted_descriptions_and_number_blocks_are_kept():
    catalog = parse_a2l(A2L)
    names = {c.name: c for c in catalog.characteristics}
    assert set(names) == {'CWQUOTE', 'CWSLASH', 'BLK15', 'BLK16'}
    assert names['CWQUOTE'].description == 'Ausgabe "Km bei MIL on" abschalten'
    assert names['CWQUOTE'].cal_type == 'VALUE' and names['CWQUOTE'].address == 0x100
    assert names['CWSLASH'].description == 'Ein "Zitat"'
    assert names['BLK15'].dims == (1, 4)
    assert names['BLK16'].dims == (2, 3)
    assert not catalog.warnings


def test_number_blocks_link_to_the_right_bytes():
    catalog = parse_a2l(A2L)
    data = bytes(range(256)) * 2
    result = catalog.link(file_size=len(data), ecu_anchor=0, data=data)
    blk = next(m for m in result.maps if m.name == 'BLK15')
    assert (blk.offset, blk.rows, blk.cols, blk.dtype, blk.endian) == (0x104, 1, 4, 'u16', 'big')
