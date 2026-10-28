"""Guided definition editing (core) and XDF export with read-back through the project's importer."""
import struct
import pytest
from ecu_studio.core.definition_edit import AxisSpec, commit, preview_values, propose
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.xdf import read_xdf
from ecu_studio.core.xdf_export import equation, export_xdf, verify_roundtrip


def _image():
    raw = bytearray(4096)
    for i in range(16):                                   # u16 BE table 4x4 at 0x100
        struct.pack_into('>H', raw, 0x100 + 2 * i, 1000 + 10 * i)
    struct.pack_into('>4H', raw, 0x200, 800, 1600, 2400, 3200)    # X axis (rpm)
    struct.pack_into('>4H', raw, 0x210, 10, 20, 40, 80)           # Y axis (load)
    struct.pack_into('<8h', raw, 0x300, -5, 0, 5, 10, 15, 20, 25, 30)   # s16 LE curve
    raw[0x400] = 77                                       # u8 constant
    return BinaryImage(bytes(raw))


def _maps():
    return [MapDefinition('Kennfeld A', 0x100, 4, 4, 'u16', 'big', 0.1, -5.0, 'Nm', source='heuristic',
                          axes_x=[800, 1600, 2400, 3200], axes_y=[10, 20, 40, 80],
                          axis_x_unit='1/min', axis_y_unit='%', folder='Motor'),
            MapDefinition('Kennlinie B', 0x300, 1, 8, 's16', 'little', 0.5, 0.0, '°C'),
            MapDefinition('Konstante C', 0x400, 1, 1, 'u8', 'big', 1.0, 0.0, '')]


# -- guided editing -------------------------------------------------------------------------

def test_geometry_type_scaling_and_axes_are_validated_and_committed_with_undo():
    image, maps = _image(), _maps()
    original_bytes = image.materialize()
    m = maps[0]
    p = propose(image, m, {'name': ' Ladedruck Soll ', 'factor': 0.01, 'bias': 0.0, 'unit': 'bar'},
                axis_x=AxisSpec(0x200, 'u16', 'big'), axis_y=AxisSpec(0x210, 'u16', 'big', 0.5))
    assert p.proposed.name == 'Ladedruck Soll' and p.proposed.axes_y == [5, 10, 20, 40]
    assert p.proposed.axis_x_offset == 0x200 and p.proposed.dtype == 'u16' and p.proposed.endian == 'big'
    assert preview_values(image, p.proposed)[0][:2] == [10.0, 10.1]
    assert m.name == 'Kennfeld A'                        # nothing changes before the commit
    new = commit(image, maps, p, confirmed=True)
    assert maps[0] is new and new.name == 'Ladedruck Soll' and new.factor == 0.01 and not new.verified
    assert image.materialize() == original_bytes         # definitions only, never bytes
    assert image.undo() and maps[0].name == 'Kennfeld A' and maps[0].factor == 0.1
    assert image.redo() and maps[0].name == 'Ladedruck Soll'


def test_invalid_addresses_overflow_and_bad_axes_are_refused():
    image, maps = _image(), _maps()
    m = maps[0]
    with pytest.raises(ValueError, match='außerhalb'):
        propose(image, m, {'offset': 4090})                          # 32 bytes do not fit
    with pytest.raises(ValueError):
        propose(image, m, {'offset': -2})
    with pytest.raises(ValueError, match='Achse'):
        propose(image, m, {}, axis_x=AxisSpec(4094, 'u16'))           # axis runs past the end
    with pytest.raises(ValueError, match='Name'):
        propose(image, m, {'name': '   '})
    with pytest.raises(ValueError, match='Skalierung'):
        propose(image, m, {'factor': 0.0})
    with pytest.raises(ValueError, match='Nicht bearbeitbar'):
        propose(image, m, {'source': 'manual'})


def test_resize_drops_axes_that_no_longer_fit_and_warns():
    image, maps = _image(), _maps()
    p = propose(image, maps[0], {'rows': 2, 'cols': 8})
    assert p.proposed.axes_x == [] and p.proposed.axes_y == []
    assert len(p.warnings) == 2


def test_cancel_and_unconfirmed_commit_change_nothing():
    image, maps = _image(), _maps()
    before = [m.asdict() for m in maps]
    p = propose(image, maps[0], {'name': 'Neu'})
    with pytest.raises(ValueError, match='bestätigt'):
        commit(image, maps, p, confirmed=False)
    assert [m.asdict() for m in maps] == before and not image._undo


def test_verified_only_by_explicit_choice_and_stale_proposals_are_refused():
    image, maps = _image(), _maps()
    p = propose(image, maps[0], {'name': 'Neu'})
    assert not p.proposed.verified                       # detection never verifies
    q = propose(image, maps[0], {'verified': True})
    assert q.proposed.verified and any('geprüft' in w for w in q.warnings)
    commit(image, maps, p, confirmed=True)
    with pytest.raises(ValueError):
        commit(image, maps, q, confirmed=True)           # built on the old definition


# -- XDF export -----------------------------------------------------------------------------

def test_xdf_roundtrip_table_curve_constant(tmp_path):
    image, maps = _image(), _maps()
    path = tmp_path / 'export.xdf'
    report = export_xdf(path, image, maps, title='Test')
    assert (report.exported, report.tables, report.constants, report.skipped) == (3, 2, 1, [])
    assert verify_roundtrip(path, image, maps) == []
    back = read_xdf(str(path), image).maps
    a, b, c = back
    assert (a.offset, a.rows, a.cols, a.dtype, a.endian) == (0x100, 4, 4, 'u16', 'big')
    assert (a.factor, a.bias, a.unit, a.axes_x, a.axis_y_unit, a.folder) == (0.1, -5.0, 'Nm', [800, 1600, 2400, 3200], '%', 'Motor')
    assert (b.dtype, b.endian, b.rows, b.cols, b.factor) == ('s16', 'little', 1, 8, 0.5)
    assert b.axes_x == []                                # unknown axis is not invented
    assert image.physical_value(b, 0, 0) == image.physical_value(maps[1], 0, 0) == -2.5
    assert (c.rows, c.cols, c.dtype, c.offset) == (1, 1, 'u8', 0x400)
    assert all(not m.verified for m in back)             # import never verifies


def test_xdf_export_reports_what_it_cannot_write(tmp_path):
    image = _image()
    maps = [MapDefinition('Float', 0x500, 2, 2, 'f32'), MapDefinition('Zu groß', 4000, 16, 16, 'u16'),
            MapDefinition('Gut', 0x100, 4, 4, 'u16')]
    report = export_xdf(tmp_path / 'x.xdf', image, maps)
    assert report.exported == 1 and [n for n, _ in report.skipped] == ['Float', 'Zu groß']
    assert 'Gleitkomma' in report.skipped[0][1] and 'ungültig' in report.skipped[1][1]
    assert 'nicht exportiert' in report.summary()


def test_equations_keep_own_formula_and_affine_sign():
    assert equation(MapDefinition('a', 0, factor=0.1, bias=-40)) == 'X*0.1-40'
    assert equation(MapDefinition('b', 0)) == 'X'
    assert equation(MapDefinition('c', 0, equation='X*X/10')) == 'X*X/10'
