"""No accidental source encoding declaration in the first two lines of any Python file.

PEP 263 tools match the pattern below anywhere in line 1 or 2, also outside a comment. A docstring with
"decoding: counts" made CodeQL read tests/test_a2l_records.py as encoding "counts" and skip it with a
syntax error (code scanning on eb30c81).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = re.compile(rb'coding[:=][ \t]*([-\w.]+)')
VALID = re.compile(rb'^[ \t\f]*#.*?coding[:=][ \t]*(utf-8|utf8|ascii|latin-1)\b', re.I)


def test_no_python_file_declares_an_encoding_by_accident():
    bad = []
    for path in sorted(list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'tests').rglob('*.py'))
                       + list((ROOT / 'packaging').rglob('*.py'))):
        for line in path.read_bytes().splitlines()[:2]:
            if DECLARATION.search(line) and not VALID.match(line):
                bad.append(f'{path.relative_to(ROOT)}: {line[:80]!r}')
    assert not bad, bad
