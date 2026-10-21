"""Apply the interface language to Qt: text setters, message boxes, dialogs, combo boxes, shown windows.

Installed once at start-up (``install``) before any window exists. With German
active nothing is patched. With English active:

- text setters (labels, buttons, titles, tooltips, status bar, tabs, headers,
  message boxes, input/file dialogs) translate their argument,
- every window is translated again when it is shown (covers texts given to
  constructors),
- combo boxes SHOW the translation but keep returning the original value from
  currentText()/itemText(), and accept original values in setCurrentText()/
  findText(): program logic and saved projects stay language-independent.
"""
from __future__ import annotations
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDockWidget, QFileDialog, QGroupBox,
                               QInputDialog, QLabel, QLineEdit, QMenu, QMenuBar, QMessageBox, QPlainTextEdit,
                               QStatusBar, QTableWidget, QTabWidget, QTextEdit, QToolBar, QToolButton, QWidget)
from ..core import i18n
from ..core.i18n import t

ORIGINAL = Qt.ItemDataRole.UserRole + 731     # combo item: original (German) text
_installed = False


def _wrap(cls, name, positions=(0,), keywords=()):
    original = getattr(cls, name)

    def patched(self, *args, **kwargs):
        args = list(args)
        for i in positions:
            if i < len(args) and isinstance(args[i], str):
                args[i] = t(args[i])
        for k in keywords:
            if isinstance(kwargs.get(k), str):
                kwargs[k] = t(kwargs[k])
        return original(self, *args, **kwargs)
    patched.__name__ = name
    setattr(cls, name, patched)


def _wrap_static(cls, name, positions):
    original = getattr(cls, name)

    def patched(*args, **kwargs):
        args = list(args)
        for i in positions:
            if i < len(args) and isinstance(args[i], str):
                args[i] = t(args[i])
        for k in ('title', 'text', 'caption', 'label', 'filter', 'informativeText'):
            if isinstance(kwargs.get(k), str):
                kwargs[k] = t(kwargs[k])
        return original(*args, **kwargs)
    setattr(cls, name, staticmethod(patched))


def _patch_combo():
    add_item, add_items, insert_item = QComboBox.addItem, QComboBox.addItems, QComboBox.insertItem
    set_item_text, item_text, current_text = QComboBox.setItemText, QComboBox.itemText, QComboBox.currentText
    find_text, set_current_text = QComboBox.findText, QComboBox.setCurrentText

    def _remember(combo, index, text):
        combo.setItemData(index, text, ORIGINAL)

    def addItem(self, *args, **kwargs):
        text_pos = 1 if args and not isinstance(args[0], str) else 0
        if len(args) > text_pos and isinstance(args[text_pos], str):
            original = args[text_pos]
            args = list(args); args[text_pos] = t(original)
            add_item(self, *args, **kwargs)
            _remember(self, self.count() - 1, original)
            return
        add_item(self, *args, **kwargs)

    def addItems(self, texts):
        for text in texts:
            addItem(self, text)

    def insertItem(self, index, *args, **kwargs):
        text_pos = 1 if args and not isinstance(args[0], str) else 0
        if len(args) > text_pos and isinstance(args[text_pos], str):
            original = args[text_pos]
            args = list(args); args[text_pos] = t(original)
            insert_item(self, index, *args, **kwargs)
            _remember(self, index, original)
            return
        insert_item(self, index, *args, **kwargs)

    def setItemText(self, index, text):
        set_item_text(self, index, t(text)); _remember(self, index, text)

    def itemText(self, index):
        original = self.itemData(index, ORIGINAL)
        return original if isinstance(original, str) else item_text(self, index)

    def currentText(self):
        if self.isEditable():
            return current_text(self)
        index = self.currentIndex()
        return itemText(self, index) if index >= 0 else current_text(self)

    def findText(self, text, *args):
        for i in range(self.count()):
            if itemText(self, i) == text:
                return i
        return find_text(self, t(text), *args)

    def setCurrentText(self, text):
        index = findText(self, text)
        if index >= 0 and not self.isEditable():
            self.setCurrentIndex(index)
        else:
            set_current_text(self, t(text) if not self.isEditable() else text)

    for name, fn in (('addItem', addItem), ('addItems', addItems), ('insertItem', insertItem),
                     ('setItemText', setItemText), ('itemText', itemText), ('currentText', currentText),
                     ('findText', findText), ('setCurrentText', setCurrentText)):
        setattr(QComboBox, name, fn)


def translate_tree(root: QWidget) -> None:
    """Translate texts of a shown window that were set through constructors."""
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        if w.isWindow() and w.windowTitle():
            w.setWindowTitle(w.windowTitle())
        if w.toolTip():
            w.setToolTip(w.toolTip())
        if isinstance(w, QLabel) and w.text():
            w.setText(w.text())
        elif isinstance(w, QAbstractButton) and w.text() and not isinstance(w, QToolButton):
            w.setText(w.text())
        elif isinstance(w, QGroupBox) and w.title():
            w.setTitle(w.title())
        elif isinstance(w, QLineEdit) and w.placeholderText():
            w.setPlaceholderText(w.placeholderText())
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                w.setTabText(i, w.tabText(i))
        elif isinstance(w, QDockWidget) and w.windowTitle():
            w.setWindowTitle(w.windowTitle())
        elif isinstance(w, QComboBox):
            model = w.model()
            for i in range(w.count()):
                if isinstance(w.itemData(i, ORIGINAL), str):
                    continue
                index = model.index(i, 0)
                shown = index.data(Qt.ItemDataRole.DisplayRole)
                if isinstance(shown, str) and t(shown) != shown:
                    w.setItemData(i, shown, ORIGINAL)
                    model.setData(index, t(shown), Qt.ItemDataRole.DisplayRole)
        elif isinstance(w, QTableWidget):
            for i in range(w.columnCount()):
                item = w.horizontalHeaderItem(i)
                if item and item.text():
                    item.setText(t(item.text()))
        elif isinstance(w, (QPlainTextEdit, QTextEdit)) and w.isReadOnly():
            text = w.toPlainText()
            if text and t(text) != text:
                w.setPlainText(text)
        if isinstance(w, (QMenu, QMenuBar, QToolBar)) or w.isWindow():
            _translate_actions(w)


def _translate_actions(w: QWidget) -> None:
    for action in QWidget.actions(w):   # some windows shadow actions() with an attribute
        if action.text():
            action.setText(action.text())
        if action.toolTip() and action.toolTip() != action.text():
            action.setToolTip(action.toolTip())
        menu = action.menu()
        if menu is not None:
            menu.setTitle(menu.title())
            _translate_actions(menu)


class _ShowFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and (obj.isWindow() or isinstance(obj, QMenu)):
            try:
                translate_tree(obj)
            except RuntimeError:
                pass
        return False


def install(app: QApplication, code: str) -> None:
    """Activate the language for this run (call once, before windows are created)."""
    global _installed
    i18n.set_language(code)
    if code == 'de' or _installed:
        return
    _installed = True
    _wrap(QLabel, 'setText'); _wrap(QAbstractButton, 'setText')
    _wrap(QWidget, 'setWindowTitle'); _wrap(QWidget, 'setToolTip'); _wrap(QWidget, 'setStatusTip')
    _wrap(QStatusBar, 'showMessage'); _wrap(QLineEdit, 'setPlaceholderText'); _wrap(QGroupBox, 'setTitle')
    _wrap(QPlainTextEdit, 'setPlainText'); _wrap(QPlainTextEdit, 'appendPlainText')
    _wrap(QTextEdit, 'setPlainText'); _wrap(QTextEdit, 'setHtml'); _wrap(QTextEdit, 'append')
    _wrap(QTabWidget, 'setTabText', (1,)); _wrap(QTabWidget, 'setTabToolTip', (1,))
    _wrap(QTabWidget, 'addTab', (1, 2)); _wrap(QTabWidget, 'insertTab', (2, 3))
    _wrap(QTableWidget, 'setHorizontalHeaderLabels'); _wrap(QTableWidget, 'setVerticalHeaderLabels')
    _wrap(QAction, 'setText'); _wrap(QAction, 'setToolTip'); _wrap(QAction, 'setStatusTip'); _wrap(QAction, 'setIconText')
    _wrap(QMenu, 'addAction', (0, 1))   # addAction(text, ...) and addAction(icon, text, ...)
    _wrap(QMenu, 'setTitle'); _wrap(QMenu, 'addMenu'); _wrap(QMenuBar, 'addMenu')
    _wrap(QMessageBox, 'setText'); _wrap(QMessageBox, 'setInformativeText'); _wrap(QMessageBox, 'setDetailedText')
    for name in ('information', 'warning', 'question', 'critical'):
        _wrap_static(QMessageBox, name, (1, 2))
    for name in ('getText', 'getItem', 'getInt', 'getDouble', 'getMultiLineText'):
        _wrap_static(QInputDialog, name, (1, 2))
    for name in ('getOpenFileName', 'getSaveFileName', 'getOpenFileNames', 'getExistingDirectory'):
        _wrap_static(QFileDialog, name, (1, 3))
    _patch_combo()
    app.installEventFilter(_ShowFilter(app))
    app._i18n_filter = app.findChildren(_ShowFilter)
