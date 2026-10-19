"""Independent RomRaider XML reader. Exact internal ROM ID + size are mandatory.

Only flat byte-addressed numeric tables are supported. Inherited addresses are
resolved per ROM, axes per type; switches and unrepresentable layouts abstain.
No network access, scripts, OEM binaries, or bundled third-party XML needed.
"""
from copy import deepcopy
from pathlib import Path
import math
import re
from defusedxml import ElementTree as ET
from .model import BinaryImage, MapDefinition
from .xdf import XDFResult, _affine
from .equations import parse_equation
from .intelligence import label_from_metadata

DTYPES = {'uint8':'u8','uint16':'u16','uint32':'u32',
          'int8':'s8','int16':'s16','int32':'s32','float':'f32'}


def _size(text):
    match = re.fullmatch(r'\s*(\d+)\s*(kb|kib|bytes|b)?\s*', text or '', re.I)
    if not match: raise ValueError('ROM-Dateigröße fehlt oder unbekannt')
    return int(match[1]) * (1024 if (match[2] or '').lower() in ('kb','kib') else 1)


def _merge(base, overlay):
    result = deepcopy(base)
    result.attrib.update(overlay.attrib)
    for child in overlay:
        # Nested axes inherit by TYPE, not by their translated display names.
        key = child.get('type') if child.tag == 'table' else None
        prior = next((x for x in result if x.tag == child.tag and
                      (child.tag != 'table' or x.get('type') == key)), None)
        if prior is not None:
            idx = list(result).index(prior)
            result.remove(prior)
            result.insert(idx, _merge(prior, child) if child.tag == 'table' else deepcopy(child))
        else: result.append(deepcopy(child))
    return result


def _numeric(node, image, rows, cols, name):
    if node.get('storagetype') not in DTYPES:
        raise ValueError('Datentyp nicht unterstützt')
    if node.get('storageaddress') is None:
        raise ValueError('Speicheradresse fehlt')
    if any(k in node.attrib for k in ('startbit','bitmask','swapxy')):
        raise ValueError('Bit-/Transpositionslayout nicht unterstützt')
    m = MapDefinition(name, int(node.get('storageaddress'),16), rows, cols,
                      dtype=DTYPES[node.get('storagetype')],
                      endian=node.get('endian','big'), source='romraider', verified=False)
    scale = node.find('scaling')
    expression = scale.get('expression','x') if scale is not None else 'x'
    parse_equation(expression)
    try: m.factor,m.bias = _affine(expression)
    except ValueError: m.equation = expression
    m.unit = scale.get('units','') if scale is not None else ''
    m.validate(image.size)
    # Decode the whole table, including formula domains; no NaN/Inf in views.
    if not all(math.isfinite(float(v)) for row in image.matrix(m,physical=True) for v in row):
        raise ValueError('Nichtendliche Werte')
    return m


def read_romraider(path, image: BinaryImage) -> XDFResult:
    path = Path(path)
    if path.stat().st_size > 32*1024*1024: raise ValueError('XML größer als 32 MiB')
    root = ET.fromstring(path.read_bytes(), forbid_dtd=True, forbid_entities=True)
    if root.tag != 'roms': raise ValueError('Keine RomRaider-ROM-Definition')
    roms = {}
    matches = []
    for rom in root.findall('rom'):
        ident = rom.findtext('romid/xmlid')
        if not ident or ident in roms: raise ValueError('Fehlende/doppelte XML-ROM-ID')
        roms[ident] = rom
        internal = rom.findtext('romid/internalidstring')
        address = rom.findtext('romid/internalidaddress')
        if internal and address:
            try:
                expected = internal.encode('ascii')
                offset = int(address,16)  # RomRaider addresses are hexadecimal, also without 0x.
                if _size(rom.findtext('romid/filesize')) == image.size and image.read(offset,len(expected)) == expected:
                    matches.append(ident)
            except (ValueError,UnicodeError): continue
    if len(matches) != 1:
        raise ValueError('Keine eindeutige ROM-Zuordnung über interne ID und Dateigröße')
    cache = {}
    def resolve(ident, trail=()):
        if ident in trail or len(trail)>16: raise ValueError('Zyklische/zu tiefe ROM-Vererbung')
        if ident in cache: return cache[ident]
        if ident not in roms: raise ValueError('ROM-Basis fehlt: '+ident)
        rom = roms[ident]
        if rom.findall('include'): raise ValueError('Externe Includes nicht unterstützt')
        tables = dict(resolve(rom.get('base'),trail+(ident,))) if rom.get('base') else {}
        seen = set()
        for table in rom.findall('table'):
            name = table.get('name')
            if not name or name in seen: raise ValueError('Fehlender/doppelter Tabellenname')
            seen.add(name)
            tables[name] = _merge(tables[name],table) if name in tables else deepcopy(table)
        cache[ident] = tables
        return tables
    ident = matches[0]
    result = XDFResult(title='RomRaider · '+ident)
    result.notes.append('Interne ROM-ID und Dateigröße passen; Quellenbezeichnungen bleiben ungeprüft.')
    for name,table in resolve(ident).items():
        result.table_count += 1
        address = table.get('storageaddress','')
        try:
            if table.get('type') not in ('2D','3D'):
                raise ValueError('Schalter/Tabellentyp nicht unterstützt')
            rows,cols = int(table.get('sizey','1')),int(table.get('sizex','1'))
            m = _numeric(table,image,rows,cols,name)
            for direction,count in (('X',cols),('Y',rows)):
                axis = next((a for a in table.findall('table') if a.get('type') in
                             (direction+' Axis','Static '+direction+' Axis')),None)
                values = []
                if axis is not None:
                    if axis.get('type').startswith('Static'):
                        labels = [d.text or '' for d in axis.findall('data')]
                        if len(labels)!=count:
                            raise ValueError('Statische Achse passt nicht zur Dimension')
                        try:values = [float(v) for v in labels]
                        except ValueError:
                            # Categorical labels (e.g. gear names/enable states)
                            # are not physical breakpoints. Keep the labels as
                            # provenance and let the view show explicit indices.
                            values = []
                            m.axes_info += f'{direction}-Beschriftungen (Indexachse): '+', '.join(labels)+'; '
                        if not all(map(math.isfinite,values)):
                            raise ValueError('Nichtendliche statische Achse')
                        scale = axis.find('scaling')
                        unit = scale.get('units','') if scale is not None else ''
                    else:
                        am = _numeric(axis,image,1,count,axis.get('name',''))
                        values = list(map(float,image.matrix(am,physical=True)[0]))
                        unit = am.unit
                    setattr(m,'axes_'+direction.lower(),values)
                    setattr(m,'axis_'+direction.lower()+'_unit',unit)
                    setattr(m,'axis_'+direction.lower()+'_channel',axis.get('name',''))
                elif count>1:
                    raise ValueError('Achse fehlt für Tabellendimension')
            m.folder = table.get('category','')
            m.notes = table.findtext('description','')
            m.record_layout = 'RomRaider:flat-byte-addressed'
            label_from_metadata(m,description=m.notes)
            m.label_origin = 'RomRaider-Quellenmetadaten · '+ident
            m.label_evidence = 'ROM-ID und Größe gebunden; keine unabhängige Funktionsbestätigung'
            result.maps.append(m)
            result.entries.append(dict(name=name,kind='table',xdf_address=address,bin_offset=m.offset,status='imported',reason=''))
        except (ValueError,TypeError,OverflowError,ZeroDivisionError) as exc:
            reason = str(exc)
            result.excluded[reason] += 1
            result.entries.append(dict(name=name,kind='table',xdf_address=address,bin_offset='',status='excluded',reason=reason))
    return result
