"""Calibration image + complete reference from a TunerStudio definition (.ini) and a tune (.msq).

Open-source ECUs (Speeduino, rusEFI, MegaSquirt) describe every calibration
object in a TunerStudio .ini: page, offset, storage type, shape and scaling. A
tune (.msq) holds the physical values. Together they give the page memory as
the ECU serves it over its tuning protocol - a calibration image with a
COMPLETE, licence-clean reference (every table is known), usable as a
benchmark pair for the detector.

  python -m ecu_studio.tools.tunerstudio_image DEFINITION.ini TUNE.msq OUT_PREFIX

writes OUT_PREFIX.bin (pages back to back) and OUT_PREFIX.csv (reference in the
ECU Studio CSV format). Values whose scale cannot be resolved are not written
and not listed as reference (counted in the report). The tune's firmware
signature must equal the definition's - a wrong .ini would misplace tables.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

TYPES = {'U08': ('B', 'u8'), 'S08': ('b', 's8'), 'U16': ('H', 'u16'), 'S16': ('h', 's16'),
         'U32': ('I', 'u32'), 'S32': ('i', 's32'), 'F32': ('f', 'f32')}
_ENTRY = re.compile(r'^\s*([A-Za-z_][\w]*)\s*=\s*(scalar|array|bits)\s*,\s*([USF]\d\d)\s*,\s*(\d+)\s*,?\s*(.*)$')


@dataclass
class Definition:
    name: str
    kind: str          # scalar / array / bits
    type: str
    page: int
    offset: int
    rows: int = 1
    cols: int = 1
    units: str = ''
    scale: str = '1'
    translate: str = '0'
    options: tuple = ()


def _split(rest: str) -> list[str]:
    """Comma-separated ini fields; braces {...} and quotes stay together."""
    out, cur, depth, quote = [], '', 0, False
    for ch in rest.split(';', 1)[0] if not rest.lstrip().startswith('"') else rest:
        if ch == '"' and depth == 0:
            quote = not quote
        if ch in '{[' and not quote:
            depth += 1
        elif ch in '}]' and not quote:
            depth -= 1
        if ch == ',' and depth == 0 and not quote:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_ini(path: str):
    """(definitions by name -> list of variants, page sizes, endianness, expressions, signature)."""
    defs: dict[str, list[Definition]] = {}
    expressions: dict[str, str] = {}
    page, section, sizes, endian, signature = 0, '', [], 'little', None
    lists: dict[str, tuple] = {}
    for raw in Path(path).read_text(encoding='latin-1').splitlines():
        line = raw.strip()
        m = re.match(r'#define\s+([A-Za-z_]\w*)\s*=\s*(.*)$', line)
        if m:   # option lists such as $loadSourceNames
            lists[m.group(1)] = tuple(f.strip().strip('"') for f in _split(m.group(2)))
            continue
        if not line or line.startswith(';') or line.startswith('#'):
            continue
        if line.startswith('['):
            section = line.strip('[]'); continue
        if section == 'MegaTune' and line.startswith('signature') and signature is None:
            signature = line.split('=', 1)[1].split(';')[0].strip().strip('"')
        if section != 'Constants' and '=' in line and '{' in line and not _ENTRY.match(line):
            name, expr = line.split('=', 1)
            if re.fullmatch(r'[A-Za-z_]\w*', name.strip()):
                expressions.setdefault(name.strip(), expr.split(';')[0].strip())
            continue
        if section != 'Constants':
            continue
        if re.match(r'pageSize\s*=', line):
            sizes = [int(x) for x in line.split('=')[1].split(';')[0].split(',')]; continue
        if re.match(r'page\s*=', line):
            page = int(line.split('=')[1].split(';')[0]); continue
        if line.startswith('endianness'):
            endian = 'little' if 'little' in line else 'big'; continue
        m = _ENTRY.match(line)
        if not m or m.group(3) not in TYPES:
            continue
        name, kind, typ, offset, rest = m.groups()
        fields = _split(rest)
        d = Definition(name, kind, typ, page, int(offset))
        if kind == 'array':
            shape = re.findall(r'\d+', fields[0]) if fields else []
            if len(shape) == 2:
                d.rows, d.cols = int(shape[0]), int(shape[1])
            elif len(shape) == 1:
                d.rows, d.cols = int(shape[0]), 1
            fields = fields[1:]
        elif kind == 'bits':
            opts = [f.strip().strip('"') for f in fields[1:]]
            if len(opts) == 1 and opts[0].startswith('$'):
                opts = list(lists.get(opts[0][1:], ()))
            d.options = tuple(opts)
            fields = []
        if fields:
            d.units = fields[0].strip('"')
            d.scale = fields[1] if len(fields) > 1 else '1'
            d.translate = fields[2] if len(fields) > 2 else '0'
        defs.setdefault(name, []).append(d)
    return defs, sizes, endian, expressions, signature


class _Expr:
    """Safe evaluator for TunerStudio expressions: numbers, names, + - * /, comparisons, && || !, ?:."""
    TOKEN = re.compile(r'\s*(\d+\.\d*|\d*\.\d+|\d+|[A-Za-z_]\w*|==|!=|<=|>=|&&|\|\||[-+*/()<>?:!])')

    def __init__(self, text: str, lookup):
        self.tokens, pos = [], 0
        text = text.strip().strip('{}')
        while pos < len(text):
            m = self.TOKEN.match(text, pos)
            if not m:
                raise ValueError(text)
            self.tokens.append(m.group(1)); pos = m.end()
            if not text[pos:].strip():
                break
        self.i, self.lookup = 0, lookup

    def _peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _take(self):
        self.i += 1; return self.tokens[self.i - 1]

    def value(self):
        v = self._ternary()
        if self._peek() is not None:
            raise ValueError('trailing')
        return v

    def _ternary(self):
        cond = self._or()
        if self._peek() == '?':
            self._take(); a = self._ternary()
            if self._take() != ':':
                raise ValueError(':')
            b = self._ternary()
            return a if cond else b
        return cond

    def _or(self):
        v = self._and()
        while self._peek() == '||':
            self._take(); r = self._and(); v = bool(v) or bool(r)
        return v

    def _and(self):
        v = self._cmp()
        while self._peek() == '&&':
            self._take(); r = self._cmp(); v = bool(v) and bool(r)
        return v

    def _cmp(self):
        v = self._add()
        if self._peek() in ('==', '!=', '<', '>', '<=', '>='):
            op = self._take(); r = self._add()
            return {'==': v == r, '!=': v != r, '<': v < r, '>': v > r, '<=': v <= r, '>=': v >= r}[op]
        return v

    def _add(self):
        v = self._mul()
        while self._peek() in ('+', '-'):
            op = self._take(); r = self._mul(); v = v + r if op == '+' else v - r
        return v

    def _mul(self):
        v = self._unary()
        while self._peek() in ('*', '/'):
            op = self._take(); r = self._unary(); v = v * r if op == '*' else v / r
        return v

    def _unary(self):
        if self._peek() == '!':
            self._take(); return not self._unary()
        if self._peek() == '-':
            self._take(); return -self._unary()
        return self._primary()

    def _primary(self):
        t = self._take()
        if t == '(':
            v = self._ternary()
            if self._take() != ')':
                raise ValueError(')')
            return v
        if re.fullmatch(r'\d+\.\d*|\d*\.\d+|\d+', t):
            return float(t)
        if self._peek() == '(':
            raise ValueError(f'Funktion {t} nicht unterstützt')
        return self.lookup(t)


def parse_msq(path: str) -> tuple[dict, str | None]:
    """{name: (values|text, rows, cols, units)} and the tune's firmware signature."""
    root = ET.parse(path).getroot()
    ns = {'m': root.tag.split('}')[0].strip('{')} if root.tag.startswith('{') else {}
    q = (lambda t: f'm:{t}') if ns else (lambda t: t)
    info = root.find(q('versionInfo'), ns)
    out = {}
    for c in root.iter(('{%s}constant' % ns['m']) if ns else 'constant'):
        text = (c.text or '').strip()
        rows, cols = int(c.get('rows') or 1), int(c.get('cols') or 1)
        try:
            values = [float(x) for x in text.split()]
        except ValueError:
            values = text.strip('"')
        out[c.get('name')] = (values, rows, cols, c.get('units') or '')
    return out, (info.get('signature') if info is not None else None)


def build_image(ini_path: str, msq_path: str):
    defs, sizes, endian, expressions, ini_sig = parse_ini(ini_path)
    tune, msq_sig = parse_msq(msq_path)
    if ini_sig and msq_sig and ini_sig != msq_sig:
        raise ValueError(f'Firmware der Abstimmung ({msq_sig}) passt nicht zur Definition ({ini_sig})')
    bases = [0]
    for s in sizes:
        bases.append(bases[-1] + s)
    image = bytearray(bases[-1])
    order = '<' if endian == 'little' else '>'

    def option_index(name, label):
        for d in defs.get(name, []):
            if d.kind == 'bits' and label in d.options:
                return float(d.options.index(label))
        return None

    def lookup(name, depth=[0]):
        if name in tune:
            v = tune[name][0]
            if isinstance(v, list) and len(v) == 1:
                return v[0]
            if isinstance(v, str):
                idx = option_index(name, v)
                if idx is not None:
                    return idx
        if name in expressions and depth[0] < 20:
            depth[0] += 1
            try:
                return _Expr(expressions[name], lookup).value()
            finally:
                depth[0] -= 1
        raise ValueError(f'unbekannt: {name}')

    def number(text):
        text = text.strip()
        try:
            return float(text)
        except ValueError:
            return float(_Expr(text, lookup).value())

    refs, stats = [], {'written': 0, 'unresolved': 0, 'clipped_values': 0, 'not_in_definition': 0}
    for name, (values, rows, cols, units) in tune.items():
        variants = [d for d in defs.get(name, []) if d.kind != 'bits']
        if not variants or not isinstance(values, list):
            stats['not_in_definition'] += not variants
            continue
        d = next((v for v in variants if v.units == units), variants[0])   # #if branches differ by units
        if d.page < 1 or d.page > len(sizes) or d.rows * d.cols != len(values):
            stats['unresolved'] += 1; continue
        try:
            scale, translate = number(d.scale), number(d.translate)
        except (ValueError, ZeroDivisionError):
            stats['unresolved'] += 1; continue
        if not scale:
            stats['unresolved'] += 1; continue
        fmt, dtype = TYPES[d.type]
        width = struct.calcsize(fmt)
        base = bases[d.page - 1] + d.offset
        if base + width * len(values) > len(image):
            stats['unresolved'] += 1; continue
        for k, v in enumerate(values):
            raw = v / scale - translate
            if dtype != 'f32':
                lo, hi = (0, 256 ** width - 1) if dtype[0] == 'u' else (-(256 ** width) // 2, 256 ** width // 2 - 1)
                r = int(round(raw))
                if not lo <= r <= hi:
                    stats['clipped_values'] += 1
                raw = min(hi, max(lo, r))
            struct.pack_into(order + fmt, image, base + k * width, raw)
        stats['written'] += 1
        if d.kind == 'array':
            refs.append({'name': name, 'offset': base, 'rows': d.rows, 'cols': d.cols, 'dtype': dtype, 'endian': endian,
                         'factor': scale, 'bias': translate * scale, 'unit': units})
    stats.update(signature=msq_sig, pages=len(sizes), image_size=len(image), arrays=len(refs))
    return bytes(image), refs, stats


def write_reference(refs: list[dict], path: Path) -> None:
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'offset', 'rows', 'cols', 'dtype', 'endian', 'factor', 'bias', 'unit', 'kind', 'notes'])
        for r in refs:
            w.writerow([r['name'], f"0x{r['offset']:X}", r['rows'], r['cols'], r['dtype'], r['endian'],
                        r['factor'], r['bias'], r['unit'], 'Unbekannt', 'TunerStudio-Definition'])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('ini'); p.add_argument('msq'); p.add_argument('out_prefix', type=Path)
    a = p.parse_args(argv)
    image, refs, stats = build_image(a.ini, a.msq)
    a.out_prefix.with_suffix('.bin').write_bytes(image)
    write_reference(refs, a.out_prefix.with_suffix('.csv'))
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
