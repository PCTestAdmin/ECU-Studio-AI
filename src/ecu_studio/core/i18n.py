"""Interface language: German source texts, English translation catalog.

The program is written with German texts. With English active, ``t(text)``
returns the translation from recognition/data/i18n/en.json:

1. exact entry,
2. template entry for composed texts ("{0} Kennfelder exportiert" matches
   "12 Kennfelder exportiert"; placeholders keep their values),
3. line by line for multi-line messages, part by part for ' · '/' | ' status lines,
4. known sentence fragments inside longer texts (longest first).

Untranslated text stays German rather than being guessed. Data (map names
from definitions, units, file names) passes through unchanged unless it is a
catalog entry. ``tools/i18n_extract.py --check`` keeps the catalog complete.
"""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'i18n' / 'en.json'
LANGUAGES = {'de': 'Deutsch', 'en': 'English'}
_language = 'de'
_MIN_FRAGMENT = 14
_SEPARATOR = re.compile(r'(\s+[·|]\s+)')
_WORD = re.compile(r'[A-Za-zÄÖÜäöüß]{3}')   # no word, nothing to translate (hex cells, numbers)


def language() -> str:
    return _language


def set_language(code: str) -> None:
    global _language
    _language = code if code in LANGUAGES else 'de'


def system_language() -> str:
    """'de' for German systems, else 'en'."""
    try:
        from PySide6.QtCore import QLocale
        return 'de' if QLocale.system().name().lower().startswith('de') else 'en'
    except ImportError:
        import locale
        return 'de' if (locale.getlocale()[0] or '').lower().startswith('de') else 'en'


@lru_cache(maxsize=1)
def _catalog():
    try:
        entries = json.loads(CATALOG.read_text(encoding='utf-8'))['entries']
    except (OSError, ValueError, KeyError):
        entries = {}
    entries = dict(entries)
    # Lines of multi-line texts also stand alone (labels often append further lines).
    for k, v in list(entries.items()):
        if v and '\n' in k and k.count('\n') == v.count('\n'):
            for ks, vs in zip(k.split('\n'), v.split('\n')):
                if ks.strip() and vs.strip() and ks not in entries:
                    ids = re.findall(r'\{(\d+)\}', ks)
                    if sorted(ids) != sorted(re.findall(r'\{(\d+)\}', vs)):
                        continue
                    remap = {old: str(new) for new, old in enumerate(dict.fromkeys(ids))}
                    entries[re.sub(r'\{(\d+)\}', lambda m: '{%s}' % remap[m.group(1)], ks)] = \
                        re.sub(r'\{(\d+)\}', lambda m: '{%s}' % remap[m.group(1)], vs)
    exact = {k: v for k, v in entries.items() if v and not re.search(r'\{\d+\}', k)}
    templates = []
    for k, v in entries.items():
        if v and re.search(r'\{\d+\}', k):
            literal = re.split(r'(\{\d+\})', k)
            if len(''.join(p for p in literal if not re.fullmatch(r'\{\d+\}', p)).strip()) < 3:
                continue
            # Directly adjacent placeholders ({1}{2}) make lazy groups backtrack
            # exponentially on long non-matching texts; such composites are not used.
            if re.search(r'\}\{\d', k.replace('{{', '').replace('}}', '')):
                continue
            pattern = ''.join('(.*?)' if re.fullmatch(r'\{\d+\}', p) else re.escape(p.replace('{{', '{').replace('}}', '}'))
                              for p in literal)
            order = [int(p[1:-1]) for p in literal if re.fullmatch(r'\{\d+\}', p)]
            chunks = [p.replace('{{', '{').replace('}}', '}') for p in literal
                      if p and not re.fullmatch(r'\{\d+\}', p)]
            templates.append((re.compile('^' + pattern + '$', re.S), order, v, chunks))
    templates.sort(key=lambda t: -len(t[0].pattern))
    fragments = sorted(((k, v) for k, v in exact.items() if len(k) >= _MIN_FRAGMENT), key=lambda kv: -len(kv[0]))
    return exact, templates, fragments


def _one(text: str) -> str | None:
    exact, templates, _ = _catalog()
    if text in exact:
        return exact[text]
    stripped = text.strip()
    if stripped != text and stripped in exact:
        return text.replace(stripped, exact[stripped])
    for regex, order, target, chunks in templates:
        if not all(c in text for c in chunks):     # cheap pre-filter before any regex work
            continue
        m = regex.match(text)
        if m:
            values = [t(g) for g in m.groups()]
            try:
                return target.format(*[values[order.index(i)] if i in order else '' for i in range(len(order))])
            except (IndexError, KeyError, ValueError):
                return None
    return None


@lru_cache(maxsize=8192)
def _translate(text: str) -> str:
    exact = _catalog()[0]
    if text in exact:
        return exact[text]
    parts = _SEPARATOR.split(text)
    if len(parts) > 1 and '\n' not in text:
        # Composite status lines ("16 × 16 · u16 · Unbekannt · Typ-Vorschlag"):
        # each part on its own, before short templates like "{0} geprüft"
        # could swallow the whole line.
        joined = ''.join(p if i % 2 or not p.strip() else t(p) for i, p in enumerate(parts))
        if joined != text:
            return joined
    direct = _one(text)
    if direct is not None:
        return direct
    if '\n' in text:
        lines = text.split('\n')
        out = [_translate(line) if line.strip() else line for line in lines]
        if out != lines:
            return '\n'.join(out)
    if len(text) >= _MIN_FRAGMENT and any(c.isalpha() for c in text):
        result = text
        for k, v in _catalog()[2]:
            if k in result:
                result = result.replace(k, v)
        return result
    return text


def t(text):
    """Translated interface text (German unchanged when German is active)."""
    if _language == 'de' or not isinstance(text, str) or len(text) < 3 or not _WORD.search(text):
        return text
    return _translate(text)


def translated_roles(method):
    """Decorator for Qt model data()/headerData(): translate display and tooltip strings."""
    def wrapper(self, *args, **kwargs):
        value = method(self, *args, **kwargs)
        return t(value) if isinstance(value, str) else value
    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper
