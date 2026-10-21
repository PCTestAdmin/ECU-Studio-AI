"""Compact, restrained Qt Widgets presentation for calibration workstations.

Independent visual language: inspired by professional engineering software,
not a reproduction of any vendor's protected trade dress or icon assets.
"""
from __future__ import annotations

PALETTES = {
 'light': {
    'base':'#EEF1F5','surface':'#FFFFFF','surface2':'#F7F9FB','well':'#F3F6FA',
    'line':'#D3D9E2','line2':'#E6EAF0','text':'#1B2430','secondary':'#5F6E82',
    'accent':'#1F6FEB','accent_hover':'#185BC4','selection':'#DCE9FD',
    'selection_text':'#123E7C','header':'#E9EDF3','tab':'#E9EDF3','changed':'#FFE9C2',
    'changed_text':'#7A4B00','warn':'#A65A00',
 },
 'dark': {
    'base':'#14181F','surface':'#1B2029','surface2':'#181D25','well':'#161B22',
    'line':'#2E3643','line2':'#252C37','text':'#E4E9F1','secondary':'#93A0B4',
    'accent':'#4C9AFF','accent_hover':'#71B0FF','selection':'#1F3A5F',
    'selection_text':'#FFFFFF','header':'#212834','tab':'#1B2029','changed':'#5A4420',
    'changed_text':'#FFD28A','warn':'#F2B35E',
 },
}

# Cold-to-hot scale used by heatmap, table and 3-D view (low = blue, high = red),
# the convention calibration engineers read at a glance.
HEAT_STOPS = ((0.00, (38, 84, 196)), (0.22, (32, 156, 214)), (0.42, (46, 184, 122)),
              (0.62, (226, 206, 62)), (0.80, (240, 138, 44)), (1.00, (214, 52, 52)))


def heat_rgb(t: float) -> tuple[int, int, int]:
    """Colour for a value normalised to 0..1 (clamped)."""
    t = 0. if t != t else min(1., max(0., t))
    for (t0, c0), (t1, c1) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return HEAT_STOPS[-1][1]


def heat_tint(t: float, theme: str) -> tuple[int, int, int]:
    """Heat colour blended into the cell background so text stays readable."""
    base = palette(theme)['surface'].lstrip('#')
    bg = tuple(int(base[i:i + 2], 16) for i in (0, 2, 4))
    strength = .55 if theme == 'dark' else .42
    return tuple(round(b + (h - b) * strength) for h, b in zip(heat_rgb(t), bg))


def palette(theme: str) -> dict[str,str]:
    return PALETTES.get(theme, PALETTES['light'])


def stylesheet(theme: str) -> str:
    c=palette(theme)
    return '''
    QMainWindow, QDialog, QWidget { background: %(base)s; color: %(text)s;
      font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Arial'; font-size: 12px; }
    QMenuBar { background: %(surface)s; border-bottom: 1px solid %(line)s; padding: 2px 4px; }
    QMenuBar::item { padding: 5px 11px; background: transparent; }
    QMenuBar::item:selected { background: %(selection)s; color: %(selection_text)s; }
    QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(line)s; border-radius: 8px; padding: 6px; }
    QMenu::item { padding: 6px 22px; border-radius: 5px; }
    QMenu::item:selected { background: %(selection)s; color: %(selection_text)s; }
    QToolBar { background: %(surface)s; border-bottom: 1px solid %(line)s; spacing: 4px; padding: 6px 10px; }
    QToolBar::separator { width: 1px; background: %(line)s; margin: 5px 8px; }
    QToolButton { padding: 6px 10px; border: 1px solid transparent; border-radius: 6px; background: transparent; }
    QToolButton:hover { background: %(selection)s; border-color: %(line)s; }
    QDockWidget { color: %(text)s; font-weight: 600; titlebar-close-icon: none; }
    QDockWidget::title { background: %(surface)s; padding: 9px 12px; border-bottom: 1px solid %(line)s; text-align: left; }
    QDockWidget::close-button, QDockWidget::float-button { border: none; }
    QSplitter::handle { background: %(line)s; }
    QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTableView, QComboBox,
    QSpinBox, QDoubleSpinBox, QTreeWidget, QScrollArea { background: %(surface)s; color: %(text)s;
      border: 1px solid %(line)s; border-radius: 6px; selection-background-color: %(selection)s;
      selection-color: %(selection_text)s; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 22px; padding: 3px 8px; }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid %(accent)s; }
    QListWidget::item { padding: 6px 8px; border-bottom: 1px solid %(line2)s; }
    QListWidget::item:selected { background: %(selection)s; color: %(selection_text)s; }
    QTableView { gridline-color: %(line2)s; alternate-background-color: %(surface2)s; border: 0; }
    QHeaderView::section { background: %(header)s; color: %(secondary)s;
      padding: 5px 7px; border: 0; border-right: 1px solid %(line)s;
      border-bottom: 1px solid %(line)s; font-weight: 600; }
    QPushButton { background: %(surface)s; color: %(text)s; border: 1px solid %(line)s;
      border-radius: 6px; padding: 6px 12px; min-height: 22px; }
    QPushButton:hover { background: %(selection)s; border-color: %(accent)s; }
    QPushButton:pressed { background: %(header)s; }
    QPushButton#primary { background: %(accent)s; color: %(surface)s; border: 1px solid %(accent)s; font-weight: 600; }
    QPushButton#primary:hover { background: %(accent_hover)s; }
    QPushButton#secondary { background: %(header)s; }
    QTabWidget::pane { border: 1px solid %(line)s; border-radius: 0 8px 8px 8px; background: %(surface)s; }
    QTabBar::tab { background: transparent; border: 0; border-bottom: 2px solid transparent;
      padding: 8px 14px; margin-right: 2px; color: %(secondary)s; }
    QTabBar::tab:hover { color: %(text)s; border-bottom: 2px solid %(line)s; }
    QTabBar::tab:selected { background: %(surface)s; color: %(accent)s; border-bottom: 2px solid %(accent)s; font-weight: 600; }
    QLabel#workspaceTitle { color: %(text)s; font-size: 16px; font-weight: 650; }
    QLabel#fileBadge { color: %(secondary)s; font-family: 'Cascadia Mono', 'Consolas'; font-size: 11px;
      background: %(well)s; border: 1px solid %(line)s; border-radius: 10px; padding: 3px 10px; }
    QFrame#identityBanner { background: %(selection)s; border: 1px solid %(accent)s; border-radius: 8px; }
    QFrame#identityBanner QLabel { color: %(text)s; }
    QLabel#sectionTitle { color: %(secondary)s; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding-top: 4px; }
    QLabel#hint { color: %(secondary)s; }
    QLabel#identificationTitle { color: %(accent)s; font-size: 13px; font-weight: 700;
      padding: 9px 10px; background: %(well)s; border-left: 3px solid %(accent)s; border-radius: 4px; }
    QLabel#warningNote { color: %(warn)s; font-size: 11px; }
    QLabel#statusChip { color: %(secondary)s; padding: 2px 10px; border-left: 1px solid %(line)s; }
    QStatusBar { background: %(surface)s; color: %(secondary)s; border-top: 1px solid %(line)s; }
    QStatusBar::item { border: 0; }
    QScrollBar:vertical { background: transparent; width: 11px; }
    QScrollBar::handle:vertical { background: %(line)s; border-radius: 4px; min-height: 24px; margin: 2px; }
    QScrollBar:horizontal { background: transparent; height: 11px; }
    QScrollBar::handle:horizontal { background: %(line)s; border-radius: 4px; min-width: 24px; margin: 2px; }
    QCheckBox { spacing: 7px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(line)s; border-radius: 6px; padding: 5px 8px; }
    QProgressBar { background: %(well)s; border: 1px solid %(line)s; border-radius: 5px; text-align: center; height: 14px; }
    QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    ''' % c
