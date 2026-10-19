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
