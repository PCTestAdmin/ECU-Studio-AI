"""Collect German user-facing texts from the source into the translation catalog.

  python -m ecu_studio.tools.i18n_extract [--check]

Walks ui/ and the core modules whose messages reach the interface. Plain
strings become exact entries, f-strings become templates with numbered
placeholders ("{0} Kennfelder exportiert"). New texts are added to
recognition/data/i18n/en.json with an empty translation; existing translations
are kept. --check exits 1 if any collected text has no translation (used by the
test suite, so new German texts cannot slip into the English interface).
"""
from __future__ import annotations
import argparse
import ast
import json
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
CATALOG = PKG / 'recognition' / 'data' / 'i18n' / 'en.json'
SOURCES = ['ui/*.py', 'core/*.py', 'formats/*.py', 'recognition/*.py', 'main.py']
SKIP_FILES = {'i18n.py'}
GERMAN = re.compile(r'[äöüÄÖÜß]|\b(der|die|das|den|dem|des|und|nicht|mit|für|wird|werden|ist|sind|Datei|Dateien|'
                    r'Kennfeld\w*|bitte|Bitte|kein\w*|Kein\w*|aus|auf|oder|eine?|zum|zur|nach|alle|Alle|wählen|'
                    r'laden|speichern|Speichern|Fehler|ungeprüft|geprüft|Achse\w*|Werte?|Zeilen?|Spalten?|'
                    r'Suche|suchen|Prüf\w*|prüf\w*|Vorschau|Bereich\w*|Änderung\w*|Original|Steuergerät\w*|'
                    r'Übernehmen|übernehmen|Abbrechen|Schließen|Neu|Bearbeiten|Ansicht|Werkzeuge|Hilfe|'
                    r'Einstellungen|Versionen|Datei|Gehe|Lesezeichen|Typ|Einheit|Skalierung|Kandidat\w*|'
                    r'Erkennung\w*|Treffer|gemessen|Messung|Kennung|Familie|Software|\w*[kK]andidat\w*|Datenbereich|'
                    r'Unbekannt\w*|Vermutung|gesichert|wahrscheinlich|Vorschlag)\b')
# Every text passed to these calls is shown to the user, whatever words it contains.
UI_CALLS = {'act', 'QAction', 'QLabel', 'QPushButton', 'QCheckBox', 'QRadioButton', 'QGroupBox', 'QDockWidget',
            'setText', 'setWindowTitle', 'setToolTip', 'setStatusTip', 'setPlaceholderText', 'setTitle', 'showMessage',
            'addTab', 'insertTab', 'setTabText', 'addMenu', 'addItem', 'addItems', 'setHorizontalHeaderLabels',
            'setVerticalHeaderLabels', 'information', 'warning', 'question', 'critical', 'getText', 'getItem',
            'getInt', 'getDouble', 'getOpenFileName', 'getSaveFileName', 'getExistingDirectory', 'save_destination',
            'setPlainText', 'setInformativeText', 'setLabelText', 'addRow', '_label', 'QToolButton', 'setFormat',
            'addAction', 'setIconText', 'QListWidgetItem', 'QTableWidgetItem', 'setWhatsThis'}
IGNORE = re.compile(r'^[\w./\\:%-]*$|^\s*$|^[A-Z0-9_]+$|^(utf-8|latin-1|ascii)$')


def _is_text(s: str) -> bool:
    return bool(s) and not IGNORE.match(s) and bool(GERMAN.search(s)) and len(s) < 2000


def _ui_text(s: str) -> bool:
    """Shown text in a UI call: contains a capitalised word (keys, numbers, shortcuts, patterns excluded)."""
    if not s or len(s) >= 2000 or re.fullmatch(r'(Ctrl|Alt|Shift)\+.*', s) or s.startswith(('http', '*.')):
        return False
    return bool(re.search(r'[A-ZÄÖÜ][a-zäöüß]{2}', s)) or (not IGNORE.match(s) and bool(re.search(r'[A-Za-zÄÖÜäöüß]{3}', s)))


# Category names shown in combo boxes and the map list (data values, displayed translated).
CATEGORY_TABLES = {'TYPES': 'all', 'KINDS': 'keys', 'CATEGORIES': 'keys', 'LEXICON': 'first', 'TIERS': 'first', 'TIER_FILTERS': 'all'}


def _categories(tree) -> list[str]:
    out = []
    for node in ast.walk(tree):
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target if isinstance(node, ast.AnnAssign) else None
        name = getattr(target, 'id', None)
        if name not in CATEGORY_TABLES or node.value is None:
            continue
        mode, value = CATEGORY_TABLES[name], node.value
        if mode == 'all' and isinstance(value, (ast.Tuple, ast.List)):
            out += [e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        elif mode == 'keys' and isinstance(value, ast.Dict):
            out += [k.value for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        elif mode == 'first' and isinstance(value, (ast.Tuple, ast.List)):
            out += [e.elts[0].value for e in value.elts if isinstance(e, ast.Tuple) and e.elts
                    and isinstance(e.elts[0], ast.Constant) and isinstance(e.elts[0].value, str)]
    return out


def _template(node: ast.JoinedStr) -> str | None:
    parts, n = [], 0
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value.replace('{', '{{').replace('}', '}}'))
        else:
            parts.append('{%d}' % n); n += 1
    text = ''.join(parts)
    literal = re.sub(r'\{\d+\}', '', text)
    return text if n and _is_text(literal) else None


def _docstrings(tree) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def collect() -> dict[str, str]:
    found: dict[str, str] = {}
    for pattern in SOURCES:
        for path in sorted(PKG.glob(pattern)):
            if path.name in SKIP_FILES:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            docs = _docstrings(tree)
            inside_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
            for text in _categories(tree):
                found.setdefault(text, str(path.relative_to(PKG)))
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, 'id', '')
                if name not in UI_CALLS:
                    continue
                for arg in list(call.args) + [k.value for k in call.keywords]:
                    items = arg.elts if isinstance(arg, (ast.List, ast.Tuple)) else [arg]
                    for item in items:
                        if isinstance(item, ast.Constant) and isinstance(item.value, str) and _ui_text(item.value):
                            found.setdefault(item.value, str(path.relative_to(PKG)))
                        elif isinstance(item, ast.JoinedStr):
                            parts, n = [], 0
                            for v in item.values:
                                if isinstance(v, ast.Constant):
                                    parts.append(v.value.replace('{', '{{').replace('}', '}}'))
                                else:
                                    parts.append('{%d}' % n); n += 1
                            text = ''.join(parts)
                            if n and _ui_text(re.sub(r'\{\d+\}', '', text)):
                                found.setdefault(text, str(path.relative_to(PKG)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                        and id(node) not in inside_fstring and _is_text(node.value):
                    found.setdefault(node.value, str(path.relative_to(PKG)))
                elif isinstance(node, ast.JoinedStr):
                    t = _template(node)
                    if t:
                        found.setdefault(t, str(path.relative_to(PKG)))
    return found


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--check', action='store_true')
    a = p.parse_args(argv)
    found = collect()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else {}
    entries = catalog.get('entries', {})
    missing = [t for t in found if not entries.get(t)]
    if a.check:
        for t in missing[:20]:
            print('fehlt:', t[:100], file=sys.stderr)
        print(f'{len(found)} Texte, {len(missing)} ohne Übersetzung')
        return 1 if missing else 0
    for t in found:
        entries.setdefault(t, '')
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps({'language': 'en', 'entries': dict(sorted(entries.items()))}, ensure_ascii=False,
                                  indent=0) + '\n', encoding='utf-8')
    print(f'{len(found)} Texte gesammelt, {len(missing)} neu/ohne Übersetzung')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
