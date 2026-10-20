from ecu_studio.ui.theme import palette, stylesheet


def test_color_themes_have_distinct_readable_palettes_and_consistent_qss():
    assert palette('light')['base']!=palette('dark')['base']
    for theme in ('light','dark'):
        colors=palette(theme)
        assert colors['text'] != colors['surface']
        css=stylesheet(theme)
        assert 'QDockWidget::title' in css
        assert 'QTabBar::tab:selected' in css
        assert colors['accent'] in css
        assert '%(' not in css


def test_portable_build_ships_every_imported_qt_module():
    # Regression: the portable EXE crashed at start because QtSvg (toolbar icons) was not bundled.
    from pathlib import Path
    from ecu_studio.tools.build_portable_runtime import qt_modules_used
    used = qt_modules_used(Path(__file__).resolve().parents[1] / 'src' / 'ecu_studio')
    assert {'QtCore', 'QtGui', 'QtWidgets', 'QtSvg'} <= used
