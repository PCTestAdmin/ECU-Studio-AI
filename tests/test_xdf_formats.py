from ecu_studio.core.model import BinaryImage
from ecu_studio.core.xdf import read_xdf


LEGACY = """XDF
1.110000

%%HEADER%%
\t001005 DefTitle         ="Test 4K"
\t001035 BaseOffset       =0
\t002000 Category0        ="FuelMaps"
%%END%%

%%TABLE%%
\t000100 Cat0ID           =0x1
\t040005 Title            ="T_Fuel"
\t040100 Address          =0x100
\t040200 ZEq              =X*0.5,TH|0|0|0|0|
\t040300 Rows             =0x4
\t040305 Cols             =0x8
\t040310 PopByCol         =0x1
\t040325 YUnits           ="RPM"
%%END%%

%%CONSTANT%%
\t020005 Title            ="Rev Limit"
\t020100 Address          =0x20
\t020200 Equation         =X*40,TH|0|0|0|0|
%%END%%
"""


def test_legacy_text_xdf_is_imported(tmp_path):
    path=tmp_path/'old.xdf'
    path.write_bytes(LEGACY.replace('\n','\r\n').encode('latin-1'))
    result=read_xdf(str(path),BinaryImage(bytes(4096)))
    maps={m.name:m for m in result.maps}
    fuel=maps['T_Fuel']
    assert (fuel.offset,fuel.rows,fuel.cols,fuel.dtype)==(0x100,4,8,'u8')
    assert fuel.factor==.5 and fuel.storage_order=='column-major' and fuel.folder=='FuelMaps'
    assert maps['Rev Limit'].factor==40 and result.title=='Test 4K'


def test_xml_xdf_with_latin1_bytes_and_bare_ampersand_is_repaired(tmp_path):
    xml=('<?xml version="1.0" encoding="UTF-8"?><XDFFORMAT version="1.70"><XDFHEADER><deftitle>A & B</deftitle></XDFHEADER>'
         '<XDFTABLE><title>Temp</title><XDFAXIS id="x"><indexcount>4</indexcount><units>\xb0C</units></XDFAXIS>'
         '<XDFAXIS id="y"><indexcount>1</indexcount></XDFAXIS><XDFAXIS id="z">'
         '<EMBEDDEDDATA mmedaddress="0x10" mmedelementsizebits="8" mmedcolcount="4" />'
         '<MATH equation="X"><VAR id="X" /></MATH></XDFAXIS></XDFTABLE></XDFFORMAT>')
    path=tmp_path/'broken.xdf'
    path.write_bytes(xml.encode('latin-1'))
    result=read_xdf(str(path),BinaryImage(bytes(256)))
    assert result.title=='A & B' and [m.offset for m in result.maps]==[0x10]
