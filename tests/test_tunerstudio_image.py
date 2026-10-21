"""TunerStudio .ini + .msq -> calibration image and complete reference (licence-clean benchmark pairs)."""
import struct
import pytest
from ecu_studio.tools.tunerstudio_image import build_image, parse_ini, _Expr, main

INI = """[MegaTune]
   signature      = "demo 202501"
[PcVariables]
    #define loadNames = "MAP", "TPS"
[Constants]
   endianness = little
   nPages     = 2
   pageSize   = 16, 32
page = 1
   algorithm = bits, U08, 0, [0:1], $loadNames
   reqFuel   = scalar, U08, 1, "ms", 0.1, 0.0, 0, 25.5, 1
#if CELSIUS
   cltBins   = array, U08, 2, [4], "C", 1.0, -40, -40, 215, 0
#else
   cltBins   = array, U08, 2, [4], "F", 1.8, -22.23, -40, 419, 0
#endif
page = 2
   veTable   = array, U08, 0, [4x4], "%", 1.0, 0.0, 0, 255, 0
   rpmBins   = array, U16, 16, [4], "RPM", 10.0, 0.0, 0, 25500, 0
   loadBins  = array, U08, 24, [4], "kPa", loadRes, 0.0, 0, 511, 0
[ConstantsExtensions]
   loadRes = { (algorithm == 0) ? 2.0 : 0.5 }
"""

MSQ = """<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
<versionInfo fileFormat="5.0" nPages="2" signature="demo 202501"/>
<page number="0" size="16">
<constant name="algorithm">"MAP"</constant>
<constant digits="1" name="reqFuel" units="ms">9.5</constant>
<constant cols="1" digits="0" name="cltBins" rows="4" units="C">-10.0 20.0 60.0 90.0</constant>
</page>
<page number="1" size="32">
<constant cols="4" digits="0" name="veTable" rows="4" units="%">30 35 40 45 32 37 42 47 34 39 44 49 36 41 46 51</constant>
<constant cols="1" digits="0" name="rpmBins" rows="4" units="RPM">500 1500 3000 6000</constant>
<constant cols="1" digits="0" name="loadBins" rows="4" units="kPa">20 60 100 200</constant>
</page>
</msq>
"""


def _files(tmp_path, msq=MSQ):
    ini = tmp_path / 'demo.ini'; ini.write_text(INI, encoding='latin-1')
    tune = tmp_path / 'demo.msq'; tune.write_text(msq, encoding='latin-1')
    return str(ini), str(tune)


def test_pages_values_and_complete_reference(tmp_path):
    image, refs, stats = build_image(*_files(tmp_path))
    assert len(image) == 48 and stats['unresolved'] == 0 and stats['clipped_values'] == 0
    assert image[1] == 95                                    # 9.5 ms / 0.1
    assert list(image[2:6]) == [30, 60, 100, 130]            # Celsius branch chosen by the tune's units (+40)
    assert list(image[16:32]) == [30, 35, 40, 45, 32, 37, 42, 47, 34, 39, 44, 49, 36, 41, 46, 51]
    assert struct.unpack('<4H', image[32:40]) == (50, 150, 300, 600)
    assert list(image[40:44]) == [10, 30, 50, 100]            # loadRes = 2.0 because algorithm == "MAP" (index 0)
    names = {r['name']: r for r in refs}
    assert set(names) == {'cltBins', 'veTable', 'rpmBins', 'loadBins'}
    assert (names['veTable']['offset'], names['veTable']['rows'], names['veTable']['cols']) == (16, 4, 4)


def test_wrong_definition_version_is_refused(tmp_path):
    ini, tune = _files(tmp_path, MSQ.replace('signature="demo 202501"', 'signature="demo 202305"'))
    with pytest.raises(ValueError, match='passt nicht'):
        build_image(ini, tune)


def test_expressions_are_evaluated_without_eval():
    look = {'a': 1.0, 'b': 0.0}.__getitem__
    assert _Expr('{ (a == 1 && !b) ? 2.5 : 0.5 }', look).value() == 2.5
    assert _Expr('3 + 4 * 2 - 1', look).value() == 10
    with pytest.raises(ValueError):
        _Expr('__import__("os")', look).value()


def test_cli_writes_bin_and_csv(tmp_path, capsys):
    ini, tune = _files(tmp_path)
    assert main([ini, tune, str(tmp_path / 'out')]) == 0
    assert (tmp_path / 'out.bin').stat().st_size == 48
    assert 'veTable' in (tmp_path / 'out.csv').read_text(encoding='utf-8')
