"""Review aids of quality phase 3: filters for shared axes, open axis references and function status; the
detail view says why a function stays unknown; the function graph lists held-back functions (synthetic)."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ecu_studio.core.model import BinaryImage, MapDefinition


def _maps():
    def t(name, offset, **kw):
        return MapDefinition(name=name, offset=offset, rows=1, cols=4, dtype='u8', **kw)   # curves: X axis only
    far = t('FAR_A', 0x3000, source='a2l', function='FN_A', function_source='A2L FUNCTION (DEF_CHARACTERISTIC)',
            axis_x_offset=0x3800)
    b1 = t('B1', 0x100, source='a2l', function='FN_B', function_source='A2L FUNCTION (DEF_CHARACTERISTIC)',
           axes_x=[0, 1, 2, 3])                                             # fixed axis (no storage)
    b2 = t('B2', 0x200, source='a2l', function='FN_B', function_source='A2L FUNCTION (DEF_CHARACTERISTIC)',
           axes_x=[0, 1, 2, 3])
    held = t('held', 0x300, source='heuristic', axis_x_offset=0x3800)       # shares FAR_A's axis, far away
    open_ = t('open', 0x400, source='heuristic', axes_x=[0, 1, 2, 3])        # axis without storage address
    c1 = t('C1', 0x500, source='a2l', function='FN_C', function_source='A2L FUNCTION (DEF_CHARACTERISTIC)',
           axes_x=[0, 1, 2, 3])
    c2 = t('C2', 0x600, source='a2l', function='FN_C', function_source='A2L FUNCTION (DEF_CHARACTERISTIC)',
           axes_x=[0, 1, 2, 3])
    return [far, b1, b2, held, open_, c1, c2]


def test_review_filters_detail_text_and_graph(tmp_path, monkeypatch):
    from tests.test_ui_filters_banner import _window
    from ecu_studio.core.function_graph import build_function_graph
    from ecu_studio.ui.function_graph_dialog import FunctionGraphDialog
    from ecu_studio.ui.main_window import AXIS_FILTERS, FUNCTION_FILTERS, TIER_FILTERS
    app, w = _window(tmp_path, monkeypatch)
    maps = _maps()
    image = BinaryImage(bytes(0x4000))
    w.load_state(image, maps, [], '', None)
    assert TIER_FILTERS[-5:] == AXIS_FILTERS + FUNCTION_FILTERS

    def shown(choice):
        w.tier_filter.setCurrentText(choice)
        return sorted(w.catalog_model.data(w.catalog_model.index(r, 0), 0x0100) for r in range(w.catalog_model.rowCount()))
    assert shown(AXIS_FILTERS[0]) == [0, 3]                    # one axis object, two users
    assert shown(AXIS_FILTERS[1]) == [4]
    unknown = shown(FUNCTION_FILTERS[0])
    assert 3 in unknown and 4 in unknown and 1 not in unknown
    assert shown(FUNCTION_FILTERS[1]) == []                    # the far axis does not name a function
    w.tier_filter.setCurrentIndex(0)
    w.select_map(maps[3])
    detail = w.identification_detail.text()
    assert 'Funktion unbekannt' in detail and 'Speicherlage' in detail and 'FN_A' in detail
    assert 'X-Achse @ 0x3800' in w.map_hint.text() and 'Teilt die Achse mit: FAR_A' in w.map_hint.text()
    w.select_map(maps[4])
    assert 'Achsenreferenz ungeklärt' in w.map_hint.text()
    dialog = FunctionGraphDialog(w, maps, build_function_graph(image, maps), lambda m: None)
    texts = []

    def walk(item):
        texts.append(item.text(0))
        for k in range(item.childCount()):
            walk(item.child(k))
    for k in range(dialog.tree.topLevelItemCount()):
        walk(dialog.tree.topLevelItem(k))
    assert any(t.startswith('Achsenreferenzen: ') and '1 ungeklärt' in t for t in texts)
    assert any(t.startswith('Zurückgehalten (Funktion unbekannt') for t in texts)
    assert any(t == 'held → Funktion unbekannt' for t in texts)
    assert any('(Stark gestützt, nicht bestätigt)' in t for t in texts)
    dialog.close()
    w.saved_fingerprint = w.project_state()
    w.close()
