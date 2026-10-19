"""Conservative TunerPro XDF 1.60/1.70 import for a flat ECU binary.

This is an independent XML reader, not TunerPro code. It deliberately declines
unrepresentable layouts and non-affine math instead of mislabeling raw values.
Never imports patches/scripts and never edits BIN content while parsing.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field
import csv
from pathlib import Path
import math
import re
from defusedxml import ElementTree as ET

from .model import BinaryImage, MapDefinition
from .intelligence import label_from_metadata
from .equations import parse_equation, evaluate_equation


@dataclass
class XDFResult:
    maps: list[MapDefinition] = field(default_factory=list)
    excluded: Counter = field(default_factory=Counter)
    table_count: int = 0
    constant_count: int = 0
    title: str = ''
    base_offset: int = 0
    base_subtract: bool = False
    categories: dict[int,str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Per-definition audit: precise rejections help improve actual XDF coverage.
    entries: list[dict[str, str | int]] = field(default_factory=list)

    def write_audit_csv(self, path: str | Path) -> None:
        with Path(path).open('w', encoding='utf-8-sig', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=['name', 'kind', 'xdf_address',
                               'bin_offset', 'status', 'reason'], delimiter=';')
            writer.writeheader()
            writer.writerows(self.entries)

    @property
    def coverage(self) -> float:
        total = self.table_count + self.constant_count
        return len(self.maps) / total if total else 0.0

    def summary(self) -> str:
        excluded = ', '.join(f'{key}: {count}' for key,count in self.excluded.most_common(7))
        return (f'{self.title}\nTabellen: {self.table_count:,}, Konstanten: {self.constant_count:,}\n'
                f'Importierbar: {len(self.maps):,} ({self.coverage:.1%})\nAusgeschlossen: {sum(self.excluded.values()):,}'
                + (f'\nGründe: {excluded}' if excluded else ''))


def _integer(s: str | None, default: int=0) -> int:
    if s is None or not str(s).strip(): return default
    s = str(s).strip()
    return int(s, 16) if s.lower().startswith('0x') else int(s,10)


def _affine(formula: str | None) -> tuple[float,float]:
    """Safely accept only formulas provably affine in X.

    Returns (factor, offset). No eval, function calls or arbitrary symbols.
    """
    equation = (formula or 'X').strip().replace('^','**')
    root = ast.parse(equation, mode='eval')
    if sum(1 for _ in ast.walk(root))>60: raise ValueError('too complex')
    # Compute coefficients, exact for the supported arithmetic grammar.
    def walk(node) -> tuple[float,float]:
        if isinstance(node, ast.Expression): return walk(node.body)
        if isinstance(node, ast.Name) and node.id.casefold()=='x': return (1.,0.)
        if isinstance(node, ast.Constant) and type(node.value) in (float,int): return (0.,float(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd,ast.USub)):
            a,b=walk(node.operand)
            return (-a,-b) if isinstance(node.op,ast.USub) else (a,b)
        if isinstance(node, ast.BinOp):
            a,b=walk(node.left); c,d=walk(node.right)
            if isinstance(node.op,ast.Add):return a+c,b+d
            if isinstance(node.op,ast.Sub):return a-c,b-d
            if isinstance(node.op,ast.Mult):
                if a and c:raise ValueError('nonlinear product')
                return a*d+b*c,b*d
            if isinstance(node.op,ast.Div):
                if c or d==0:raise ValueError('nonlinear/zero divisor')
                return a/d,b/d
            if isinstance(node.op,ast.Pow):
                if c or d not in (0.,1.) or (d==0 and (a or b==0)):
                    raise ValueError('nonlinear exponent')
                return (1.,0.) if d==0 else (a,b)
        raise ValueError('unsupported expression')
    factor,bias=walk(root)
    if not math.isfinite(factor) or not math.isfinite(bias) or factor==0:
        raise ValueError('nonfinite or noninvertible equation')
    return factor,bias


def _math(axis: ET.Element) -> tuple[float,float]:
    m=axis.find('MATH')
    return _affine(m.get('equation') if m is not None else None)


def _mapped(address: int,base: int,subtract: bool)->int:
    return address-base if subtract else address+base


def _axis_values(axis:ET.Element|None, count:int, image: BinaryImage,
                 base:int,subtract:bool,lookup:dict[str,ET.Element]) -> list[float]:
    if axis is None or count<=0 or count>512:return []
    labels=axis.findall('LABEL')
    if labels:
        values=[None]*count
        for label in labels:
            try:
                idx=_integer(label.get('index'))
                if 0<=idx<count:values[idx]=float(label.get('value','').strip())
            except (ValueError,TypeError):pass
        if all(v is not None and math.isfinite(v) for v in values):
            return [float(x) for x in values]
    emb=axis.find('EMBEDDEDDATA')
    # A linked axis is a separately stored scalar/table. Follow only one level.
    link=axis.find('embedinfo')
    # Type 3 selects a linked object. Some XDFs retain an obsolete embedded
    # address/stride as well; reading that placeholder silently corrupts axes.
    use_link = link is not None and (link.get('type') == '3' or
                                    emb is None or emb.get('mmedaddress') is None)
    if use_link:
        linked=lookup.get((link.get('linkobjid') or '').lower())
        if linked is not None:
            emb=linked.find('EMBEDDEDDATA')
            if emb is None:
                z=linked.find("XDFAXIS[@id='z']")
                emb=z.find('EMBEDDEDDATA') if z is not None else None
            if emb is not None:
                # apply the linked axis's own scaling if present
                if linked.find('MATH') is not None or linked.find("XDFAXIS[@id='z']/MATH") is not None:
                    scaling_axis=linked if linked.find('MATH') is not None else linked.find("XDFAXIS[@id='z']")
                    try:
                        mtag=scaling_axis.find('MATH')
                        expression=mtag.get('equation','X') if mtag is not None else 'X'
                        parse_equation(expression)
                    except (ValueError,SyntaxError):return []
                else:
                    try:
                        mtag=axis.find('MATH')
                        expression=mtag.get('equation','X') if mtag is not None else 'X'
                        parse_equation(expression)
                    except (ValueError,SyntaxError):return []
            else:return []
        else:return []
    else:
        try:
            mtag=axis.find('MATH')
            expression=mtag.get('equation','X') if mtag is not None else 'X'
            parse_equation(expression)
        except (ValueError,SyntaxError):return []
    if emb is None or not emb.get('mmedaddress'):return []
    bits=_integer(emb.get('mmedelementsizebits'),8)
    if bits not in (8,16,32):return []
    flags=_integer(emb.get('mmedtypeflags'))
    if flags & ~0x07:return []
    width=bits//8
    step_bits=_integer(emb.get('mmedmajorstridebits'),0)
    # A stride of 0 means default packed axis. Other explicit forms are
    # accepted only if they are exactly equivalent to packed 1D storage.
    if step_bits and (abs(step_bits)<bits or step_bits%8):return []
    # TunerPro has inconsistent negative minor axis semantics; abstain.
    if _integer(emb.get('mmedminorstridebits'))<0:return []
    try:
        start=_mapped(_integer(emb.get('mmedaddress')),base,subtract)
        stride=(abs(step_bits)//8 if step_bits else width)
        if start<0 or start+(count-1)*stride+width>image.size:return []
        values=[]
        for idx in range(count):
            physical_idx=count-1-idx if step_bits<0 else idx
            raw=int.from_bytes(image.read(start+physical_idx*stride,width),
                               'little' if flags&0x02 else 'big',signed=bool(flags&0x01))
            v=evaluate_equation(expression,raw)
            if not math.isfinite(v):return []
            values.append(round(v,8))
        return values
    except (ValueError,IndexError,OverflowError):return []


def recognize_ms43(image:BinaryImage) -> dict:
    """Conservative in-file identification, without reading VIN or private metadata."""
    if image.size not in (524288,65536):return {'ecu':'Unbekannt','version':None,'cal_start':None}
    calstart=0x70000 if image.size==524288 else 0
    block=image.read(calstart,min(160,image.size-calstart))
    # The fixed SW field avoids shifted matches in other long numeric header
    # fields (real 430069 headers also contain incidental "430006" substrings).
    marker=block[8:14]
    projects=set(re.findall(rb'ca(4300[0-9]{2})\.DAT',block))
    version=(marker.decode('ascii') if re.fullmatch(rb'4300[0-9]{2}',marker)
             and (not projects or projects=={marker}) else None)
    return {'ecu':'Siemens MS43 (Indiz)' if version else 'Unbekannt',
            'version':version,'cal_start':calstart if version else None,
            'full_read': image.size==524288}


def read_xdf(path: str, image:BinaryImage, *, include_constants:bool=True) -> XDFResult:
    """Read tables and constants with contiguous 8/16/32 bit storage only.

    Incompatible definitions are rejected rather than importing wrong values.
    This parser DOES NOT validate firmware/hardware match: caller must gate it.
    """
    source=Path(path)
    if source.stat().st_size>25*1024*1024:raise ValueError('XDF über 25 MiB nicht unterstützt')
    with source.open('rb') as fp:
        if fp.read(3)==b'XDF':
            return read_legacy_xdf(source,image,include_constants=include_constants)
    # ET does not perform network fetches/resolve external general entities.
    try:
        root=ET.parse(source).getroot()
    except ET.ParseError:
        # TunerPro tolerates Latin-1 bytes (e.g. "°C") in files read as UTF-8 and
        # stray "&" in descriptions; repair both, keep defusedxml protections.
        raw=source.read_bytes()
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:text=raw.decode('latin-1')
        text=re.sub(r'^<\?xml[^>]*\?>','',text.lstrip('﻿'))
        text=re.sub(r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)','&amp;',text)
        root=ET.fromstring(text)
    if root.tag.upper()!='XDFFORMAT':raise ValueError('Kein TunerPro-XDF (XDFFORMAT)')
    result=XDFResult()
    header=root.find('XDFHEADER')
    if header is not None:
        result.title=header.findtext('deftitle') or source.stem
        offset=header.find('BASEOFFSET')
        if offset is not None:
            result.base_offset=_integer(offset.get('offset'))
            result.base_subtract=bool(_integer(offset.get('subtract')))
        elif header.findtext('baseoffset'):
            result.base_offset=_integer(header.findtext('baseoffset'))
        result.categories={_integer(c.get('index')):c.get('name','') for c in header.findall('CATEGORY')}
    else:result.title=source.stem
    lookup={elem.get('uniqueid','').lower():elem for elem in root
            if elem.get('uniqueid')}
    for entry in root:
        if entry.tag not in ('XDFTABLE','XDFCONSTANT'):continue
        table=entry.tag=='XDFTABLE'
        if table:result.table_count+=1
        else:result.constant_count+=1
        if not table and not include_constants:continue
        name=(entry.findtext('title') or 'Ohne Namen').strip()
        record={'name':name, 'kind':'Tabelle' if table else 'Konstante',
                'xdf_address':'', 'bin_offset':'', 'status':'abgelehnt', 'reason':''}
        result.entries.append(record)
        def reject(reason: str) -> None:
            result.excluded[reason] += 1
            record['reason'] = reason
        desc=(entry.findtext('description') or '').strip()
        z=entry.find("XDFAXIS[@id='z']") if table else entry
        if z is None:
            reject('Ohne Z-Achse');continue
        emb=z.find('EMBEDDEDDATA')
        if emb is None or not emb.get('mmedaddress'):
            reject('Keine Datenadresse');continue
        try:
            bits=_integer(emb.get('mmedelementsizebits'),8)
            flags=_integer(emb.get('mmedtypeflags'))
            if bits not in (8,16,32) or flags&~0x07:
                reject('Datentyp/Flags nicht darstellbar');continue
            dtype=('s' if flags&1 else 'u')+str(bits)
            endian='little' if flags&2 else 'big'
            storage_order='column-major' if flags&4 else 'row-major'
            if table:
                x=entry.find("XDFAXIS[@id='x']")
                y=entry.find("XDFAXIS[@id='y']")
                cols=_integer(emb.get('mmedcolcount'), _integer(x.findtext('indexcount') if x is not None else None, 1))
                rows=_integer(emb.get('mmedrowcount'), _integer(y.findtext('indexcount') if y is not None else None, 1))
            else:
                rows=cols=1
            if not (1<=rows<=512 and 1<=cols<=512):
                reject('Ungültige Dimension');continue
            # TunerPro: major = element-to-element step within each line;
            # minor = last element of line to first of next (both in bits).
            # Negative values reverse logical traversal, not binary contents.
            major=_integer(emb.get('mmedmajorstridebits'))
            minor=_integer(emb.get('mmedminorstridebits'))
            if (major and (abs(major)<bits or major%8)) or minor%8:
                reject('Nicht darstellbare Bit-/Überlappungsstrides');continue
            z_math=z.find('MATH')
            eq=z_math.get('equation','X') if z_math is not None else 'X'
            nonlinear=''
            try:
                factor,bias=_affine(eq)
            except ValueError:
                parse_equation(eq)  # Reject unsupported/dangerous syntax; never eval arbitrary code.
                factor,bias=1.,0.
                nonlinear=eq
            ecu_address=_integer(emb.get('mmedaddress'))
            record['xdf_address']=f'0x{ecu_address:X}'
            offset=_mapped(ecu_address,result.base_offset,result.base_subtract)
            record['bin_offset']=f'0x{offset:X}' if offset>=0 else str(offset)
            if offset<0:
                reject('Adresse außerhalb BIN');continue
            ax_x=_axis_values(x,cols,image,result.base_offset,result.base_subtract,lookup) if table else []
            ax_y=_axis_values(y,rows,image,result.base_offset,result.base_subtract,lookup) if table else []
            kind='Unbekannt'
            unit=(z.findtext('units') or '').strip()
            categories=[]
            for cm in entry.findall('CATEGORYMEM'):
                c=_integer(cm.get('category'),-1)
                # CATEGORYMEM is one-based in TunerPro XDFs. Prefer c-1 even
                # when an adjacent CATEGORY index also exists (Axis/Unsorted).
                value=result.categories.get(c-1) or result.categories.get(c)
                if value and value not in categories:categories.append(value)
            combined_desc=' | '.join(filter(None,[desc,*categories]))
            m=MapDefinition(name=name,offset=offset,rows=rows,cols=cols,
                dtype=dtype,endian=endian,factor=factor,bias=bias,unit=unit,
                kind=kind,source='xdf',confidence=0.,verified=False,
                notes=('XDF: '+combined_desc[:650] if combined_desc else 'TunerPro-XDF')+
                      f' | Formel: {(z.find("MATH").get("equation") if z.find("MATH") is not None else "X")}',
                ecu_address=ecu_address,axes_x=ax_x,axes_y=ax_y,
                axis_x_unit=(x.findtext('units') or '').strip() if table and x is not None else '',
                axis_y_unit=(y.findtext('units') or '').strip() if table and y is not None else '',
                folder=categories[0] if categories else '',
                axes_info='XDF X/Y; nicht gelesene Achsen sind ungeprüft',
                storage_order=storage_order,
                major_stride_bits=major,minor_stride_bits=minor,equation=nonlinear)
            m.validate(image.size)
            if nonlinear:
                # Validate representative corner/center cells BEFORE adding this map:
                # unsupported numeric domains must not crash the 2D/3D painter.
                points={(0,0),(rows-1,cols-1),(rows//2,cols//2),(0,cols-1),(rows-1,0)}
                for r,c in points:
                    image.physical_value(m,r,c)
            label_from_metadata(m,description=combined_desc)
            if m.kind=='Unbekannt' and categories:
                m.kind='XDF-Kategorie: '+categories[0][:65]
                m.label_evidence='Kategorie stammt aus der XDF-Definition; funktionale Einordnung ungeprüft.'
            m.label_origin='XDF: benannter Eintrag'+(f' · {m.label_origin}' if m.label_origin else '')
            m.label_evidence=('Name/Adresse/Skalierung aus XDF; richtige Firmware- und Layoutvariante '
                              'muss geprüft werden. '+m.label_evidence)[:800]
            result.maps.append(m)
            record['status']='importiert'
            record['reason']='Schreibgeschützt: nichtlineare Formel' if nonlinear else ''
        except (ValueError,SyntaxError,IndexError,OverflowError,TypeError) as exc:
            reject('Ungültige/komplexe Definition')
            record['reason'] += ': '+str(exc)[:110]
    return result


_LEGACY_LINE = re.compile(r'^\s*(\d{6})\s+(\w+)\s*=(.*)$', re.M)


def read_legacy_xdf(path, image: BinaryImage, *, include_constants: bool = True) -> XDFResult:
    """TunerPro XDF 1.x text format ("XDF\\n1.1x" + %%HEADER%%/%%TABLE%%/%%CONSTANT%% blocks).

    Used by many older definitions (e.g. Bosch Motronic, Renault Fenix). Same
    rules as the XML reader: contiguous 8/16/32-bit data, affine formulas only
    for editing, anything else rejected instead of guessed.
    """
    source = Path(path)
    text = source.read_bytes().decode('latin-1')
    result = XDFResult(title=source.stem)
    for kind, body in re.findall(r'%%(\w+)%%(.*?)%%END%%', text, re.S):
        fields = {name: value.strip() for _, name, value in _LEGACY_LINE.findall(body)}
        def string(key, default=''):
            return fields.get(key, default).strip('"')
        if kind == 'HEADER':
            result.title = string('DefTitle') or source.stem
            result.base_offset = _integer(fields.get('BaseOffset'), 0)
            result.categories = {int(k[8:]): string(k) for k in fields if k.startswith('Category') and k[8:].isdigit()}
            continue
        if kind not in ('TABLE', 'CONSTANT'):
            continue
        table = kind == 'TABLE'
        if table:
            result.table_count += 1
        else:
            result.constant_count += 1
            if not include_constants:
                continue
        name = string('Title') or 'Ohne Namen'
        record = {'name': name, 'kind': 'Tabelle' if table else 'Konstante',
                  'xdf_address': fields.get('Address', ''), 'bin_offset': '', 'status': 'abgelehnt', 'reason': ''}
        result.entries.append(record)
        try:
            bits = _integer(fields.get('SizeInBits'), 8)
            flags = _integer(fields.get('Flags'), 0)
            if bits not in (8, 16, 32):
                raise ValueError('Datentyp nicht darstellbar')
            dtype = ('s' if flags & 1 else 'u') + str(bits)
            endian = 'little' if flags & 2 else 'big'
            rows, cols = (_integer(fields.get('Rows'), 1), _integer(fields.get('Cols'), 1)) if table else (1, 1)
            equation = (fields.get('ZEq' if table else 'Equation') or 'X').split(',')[0].strip() or 'X'
            nonlinear = ''
            try:
                factor, bias = _affine(equation)
            except ValueError:
                parse_equation(equation)
                factor, bias, nonlinear = 1., 0., equation
            ecu_address = _integer(fields.get('Address'))
            offset = ecu_address + result.base_offset
            record['bin_offset'] = f'0x{offset:X}'
            category = result.categories.get(_integer(fields.get('Cat0ID'), -1) - 1) or ''
            desc = string('Desc')
            m = MapDefinition(name=name, offset=offset, rows=rows, cols=cols, dtype=dtype, endian=endian,
                              factor=factor, bias=bias, unit=string('ZUnits') or string('Units'),
                              source='xdf', verified=False, ecu_address=ecu_address, equation=nonlinear,
                              storage_order='column-major' if fields.get('PopByCol', '0') not in ('', '0', '0x0') else 'row-major',
                              folder=category, axis_x_unit=string('XUnits'), axis_y_unit=string('YUnits'),
                              notes=('XDF 1.x: ' + ' | '.join(filter(None, [desc[:500], category])) + f' | Formel: {equation}'),
                              axes_info='XDF 1.x; Achsen nicht gelesen')
            m.validate(image.size)
            label_from_metadata(m, description=' | '.join(filter(None, [desc, category])))
            if m.kind == 'Unbekannt' and category:
                m.kind = 'XDF-Kategorie: ' + category[:65]
            m.label_origin = 'XDF 1.x: benannter Eintrag' + (f' · {m.label_origin}' if m.label_origin else '')
            m.label_evidence = ('Name/Adresse/Skalierung aus XDF 1.x; Firmware-Variante prüfen. ' + m.label_evidence)[:800]
            result.maps.append(m)
            record['status'] = 'importiert'
        except (ValueError, SyntaxError, IndexError, OverflowError, TypeError) as exc:
            result.excluded['Ungültige/komplexe Definition'] += 1
            record['reason'] = str(exc)[:110]
    return result
