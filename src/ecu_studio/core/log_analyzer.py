"""Offline CSV log diagnostics and axis-bound bilinear sample occupancy.

Rules explain measured deviations; they never claim a mechanical cause or
propose safe tuning values. No firmware writes or learning occur here.
"""
from __future__ import annotations
from dataclasses import dataclass
import csv
import html
import io
import math
import re
from pathlib import Path
import numpy as np
from .model import MapDefinition
from .storage import atomic_write

CHANNELS = {
    'rpm': ('rpm','engine speed','motordrehzahl','drehzahl','nmot'),
    'load': ('load','engine load','last','motorlast'),
    'boost_target': ('boost target','boost specified','boost requested','ladedruck soll'),
    'boost_actual': ('boost actual','boost measured','ladedruck ist'),
    'lambda_target': ('lambda target','lambda specified','lambda soll'),
    'lambda_actual': ('lambda actual','lambda measured','lambda ist','lambda'),
    'ignition': ('ignition','ignition timing','zündwinkel','zuendwinkel','spark advance'),
    'iat': ('iat','intake air temperature','ansauglufttemperatur'),
    'coolant': ('coolant','coolant temperature','kühlmitteltemperatur'),
    'time': ('time','timestamp','zeit'),
}
UNITS = {'rpm':'rpm','load':'%','boost_target':'mbar','boost_actual':'mbar',
         'lambda_target':'1','lambda_actual':'1','ignition':'deg','iat':'C','coolant':'C','time':'s'}


@dataclass
class LogChannel:
    key: str
    header: str
    unit: str
    values: np.ndarray
    pressure_reference: str = 'unknown'


@dataclass
class LogData:
    path: str
    headers: list[str]
    channels: dict[str,LogChannel]
    sample_count: int
    invalid_values: int
    unassigned: list[str]
    delimiter: str


def _normalize(text):
    return re.sub(r'[_\s-]+',' ',text.strip().casefold())


def infer_header(header):
    unit_match = re.search(r'[\[(]([^\])]+)[\])]',header)
    unit = unit_match.group(1).strip() if unit_match else ''
    base = _normalize(re.sub(r'[\[(][^\])]+[\])]','',header))
    base = re.sub(r'\s+(absolute|absolut|gauge|relativ)$','',base)
    key = next((k for k, names in CHANNELS.items() if base in names or base==k.replace('_',' ')), '')
    if not unit and key in ('rpm','lambda_actual','lambda_target'):
        unit = UNITS[key]
    return key,unit


def convert_values(values, unit, target):
    key = unit.strip().casefold().replace('°','').replace(' ','')
    options = {
        'rpm': {'rpm':(1,0),'1/min':(1,0),'min-1':(1,0)},
        '%': {'%':(1,0),'percent':(1,0),'fraction':(100,0)},
        'mbar': {'mbar':(1,0),'hpa':(1,0),'kpa':(10,0),'bar':(1000,0),'pa':(.01,0),'psi':(68.9475729,0)},
        '1': {'1':(1,0),'lambda':(1,0),'':(1,0)},
        'deg': {'deg':(1,0),'degca':(1,0),'kw':(1,0)},
        'C': {'c':(1,0),'degc':(1,0),'f':(5/9,-32*5/9),'k':(1,-273.15)},
        's': {'s':(1,0),'sec':(1,0),'ms':(.001,0)},
    }
    try:
        factor,bias = options[target][key]
    except KeyError:
        raise ValueError(f'Einheit {unit!r} kann nicht eindeutig nach {target} umgerechnet werden') from None
    return np.asarray(values,dtype=float)*factor+bias


def read_log(path: str, overrides: dict[str,tuple[str,str]] | None=None, *, max_rows=1_000_000) -> LogData:
    source = Path(path)
    if source.stat().st_size > 100*1024**2:
        raise ValueError('Log größer als 100 MiB')
    data = source.read_bytes()
    try:
        content = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        content = data.decode('cp1252')
    lines = content.splitlines()
    # Explicit, bounded preamble detection; no arbitrary logger format claims.
    chosen = None
    for index,line in enumerate(lines[:50]):
        for delimiter in (';',',','\t'):
            row = next(csv.reader([line],delimiter=delimiter))
            if len(row)>1 and (any(infer_header(h)[0] for h in row) or
                               (overrides and any(h in overrides for h in row))):
                chosen = (index,delimiter)
                break
        if chosen:
            break
    if chosen is None:
        raise ValueError('Keine unterstützte CSV-Kopfzeile in den ersten 50 Zeilen (Kanäle/Einheiten zuordnen)')
    start,delimiter = chosen
    reader = csv.reader(io.StringIO('\n'.join(lines[start:])),delimiter=delimiter)
    headers = [h.strip() for h in next(reader)]
    if len(set(headers))!=len(headers) or len(headers)>256:
        raise ValueError('Doppelte oder mehr als 256 Spalten')
    assigned = {}
    unassigned = []
    values = {}
    for i,h in enumerate(headers):
        key,unit = (overrides or {}).get(h,infer_header(h))
        if not key:
            unassigned.append(h)
            continue
        if key not in CHANNELS or key in values:
            raise ValueError(f'Unbekannter oder doppelt zugeordneter Kanal: {key}')
        # Missing units cannot quietly acquire physical meaning.
        convert_values([],unit,UNITS[key])
        assigned[i] = (key,h,unit)
        values[key] = []
    if not assigned:
        raise ValueError('Keine zugeordneten Kanäle')
    count = invalid = 0
    for row in reader:
        if not row or all(not x.strip() for x in row):
            continue
        if len(row)!=len(headers):
            raise ValueError(f'Uneinheitliche Spaltenzahl in Datenzeile {count+1}')
        count += 1
        if count>max_rows:
            raise ValueError('Zu viele Logzeilen')
        for i,(key,_,_) in assigned.items():
            try:
                v = float(row[i].strip().replace(',','.'))
                if not math.isfinite(v):
                    raise ValueError()
            except ValueError:
                v = math.nan
                invalid += 1
            values[key].append(v)
    if not count:
        raise ValueError('Keine Messwerte im Log')
    channels = {}
    for key,h,u in assigned.values():
        # Pressure reference is metadata, not derivable from a numeric range.
        ref = 'absolute' if 'absolute' in h.casefold() or 'absolut' in h.casefold() else (
            'gauge' if 'gauge' in h.casefold() or 'relativ' in h.casefold() else 'unknown')
        channels[key] = LogChannel(key,h,UNITS[key],convert_values(values[key],u,UNITS[key]),ref)
    return LogData(str(source.resolve()),headers,channels,count,invalid,unassigned,delimiter)


def inspect_log_headers(path):
    with Path(path).open('r',encoding='utf-8-sig',errors='replace') as stream:
        for _ in range(50):
            line=stream.readline()
            if not line:
                break
            for delimiter in (';',',','\t'):
                row=next(csv.reader([line],delimiter=delimiter))
                if len(row)>1 and any(infer_header(h)[0] for h in row):
                    return [h.strip() for h in row]
    raise ValueError('Keine bekannte CSV-Kopfzeile gefunden')


def analyze_log(log: LogData, *, boost_threshold_mbar=150., lambda_threshold=.05):
    if not math.isfinite(boost_threshold_mbar) or boost_threshold_mbar<=0 or not math.isfinite(lambda_threshold) or lambda_threshold<=0:
        raise ValueError('Positive endliche Schwellen erforderlich')
    findings = []
    mask = np.zeros(log.sample_count,dtype=bool)
    for prefix,threshold,unit in (('boost',boost_threshold_mbar,'mbar'),('lambda',lambda_threshold,'1')):
        actual = log.channels.get(prefix+'_actual')
        target = log.channels.get(prefix+'_target')
        if actual is None or target is None:
            findings.append(dict(channel=prefix,status='unavailable',reason='Soll-/Ist-Kanal fehlt'))
            continue
        if prefix=='boost' and actual.pressure_reference!=target.pressure_reference:
            findings.append(dict(channel=prefix,status='unavailable',reason='Druckbezüge unterscheiden sich (absolut/relativ/unbekannt)'))
            continue
        valid = np.isfinite(actual.values)&np.isfinite(target.values)
        delta = actual.values-target.values
        abnormal = valid & (np.abs(delta)>threshold)
        mask |= abnormal
        findings.append(dict(channel=prefix,status='measured',unit=unit,threshold=threshold,
                             valid_samples=int(valid.sum()),deviation_samples=int(abnormal.sum()),
                             maximum_absolute_deviation=float(np.max(np.abs(delta[valid]))) if valid.any() else None,
                             mean_signed_deviation=float(np.mean(delta[valid])) if valid.any() else None,
                             sample_indices=np.flatnonzero(abnormal)[:200].tolist(),
                             reason=('Gemessene Soll-/Ist-Abweichung. Kalibrierung, Sensorik, Regelung und Betriebszustand separat prüfen.'
                                     + (' Druckbezug in beiden Kanälen nicht dokumentiert.' if prefix=='boost' and actual.pressure_reference=='unknown' else ''))))
    summary = {}
    for key,ch in log.channels.items():
        finite = ch.values[np.isfinite(ch.values)]
        summary[key] = dict(unit=ch.unit,valid_samples=len(finite),minimum=float(finite.min()) if len(finite) else None,
                            maximum=float(finite.max()) if len(finite) else None)
    return dict(samples=log.sample_count,invalid_values=log.invalid_values,channels=summary,
                findings=findings,abnormal_mask=mask,
                explanation='Regelbasierte Offline-Auswertung; keine belegte Ursachenfeststellung und keine automatischen Kalibrierwerte.')


def _axis(values, expected, name):
    axis = np.asarray(values,dtype=float)
    if len(axis)!=expected or expected<2 or not np.isfinite(axis).all():
        raise ValueError(f'{name}: vollständige, endliche Achse mit mindestens zwei Stützstellen erforderlich')
    if not (np.all(np.diff(axis)>0) or np.all(np.diff(axis)<0)):
        raise ValueError(f'{name}: Achse muss streng monoton sein')
    return axis


def map_occupancy(log: LogData, m: MapDefinition, abnormal_mask=None):
    if not m.verified:
        raise ValueError('Kennfelddefinition muss fachlich bestätigt sein')
    x = _axis(m.axes_x,m.cols,'X')
    y = _axis(m.axes_y,m.rows,'Y')
    try:
        xc,yc = log.channels[m.axis_x_channel],log.channels[m.axis_y_channel]
    except KeyError:
        raise ValueError('Benötigte Eingangssignale nicht zugeordnet/vorhanden') from None
    xv = convert_values(xc.values,xc.unit,m.axis_x_unit)
    yv = convert_values(yc.values,yc.unit,m.axis_y_unit)
    valid = np.isfinite(xv)&np.isfinite(yv)&(xv>=min(x))&(xv<=max(x))&(yv>=min(y))&(yv<=max(y))
    indices = np.flatnonzero(valid)
    # Descending axes retain their original cell orientation.
    def bins(axis, values):
        descending = axis[-1]<axis[0]
        asc = axis[::-1] if descending else axis
        lower = np.clip(np.searchsorted(asc,values,side='right')-1,0,len(asc)-2)
        weight = (values-asc[lower])/(asc[lower+1]-asc[lower])
        return ((len(asc)-1-lower if descending else lower),
                (len(asc)-2-lower if descending else lower+1),weight)
    x0,x1,wx = bins(x,xv[indices])
    y0,y1,wy = bins(y,yv[indices])
    counts = np.zeros((m.rows,m.cols))
    anomalies = np.zeros_like(counts)
    marked = np.zeros(log.sample_count,dtype=bool) if abnormal_mask is None else np.asarray(abnormal_mask,dtype=bool)
    if marked.shape!=(log.sample_count,):
        raise ValueError('Abweichungsmaske hat falsche Länge')
    for yy,xx,w in ((y0,x0,(1-wy)*(1-wx)),(y0,x1,(1-wy)*wx),
                    (y1,x0,wy*(1-wx)),(y1,x1,wy*wx)):
        np.add.at(counts,(yy,xx),w)
        np.add.at(anomalies,(yy,xx),w*marked[indices])
    return dict(map=m.name,counts=counts.tolist(),anomalies=anomalies.tolist(),
                mapped_samples=len(indices),excluded_samples=log.sample_count-len(indices),
                interpretation='Bilinear gewichtete Messpunkte, keine Verweildauer und kein Nachweis der tatsächlichen ECU-Kennfeldwahl.')


def write_log_report(path, log:LogData, analysis:dict, occupancy=None, *, protected=()):
    esc = html.escape
    rows = ''.join('<tr>'+''.join('<td>'+esc(str(v))+'</td>' for v in (key,info['unit'],info['valid_samples'],info['minimum'],info['maximum']))+'</tr>'
                   for key,info in analysis['channels'].items())
    notes = ''.join('<li>'+esc(str(item))+'</li>' for item in analysis['findings'])
    cells = ''
    if occupancy:
        counts = np.asarray(occupancy['counts'])
        maximum = max(1.,float(counts.max()))
        cells = '<h2>'+esc(occupancy['map'])+'</h2><p>'+esc(occupancy['interpretation'])+'</p><table>'
        for row in counts:
            cells += '<tr>'+''.join(f'<td style="background:rgba(68,162,225,{v/maximum:.3f})">{v:.2f}</td>' for v in row)+'</tr>'
        cells += '</table>'
    document = ('<!doctype html><meta charset="utf-8"><title>ECU Studio · Log-to-Map</title>'
                '<style>body{font:15px Segoe UI,sans-serif;background:#17202b;color:#e2e7f0;margin:32px}td,th{padding:8px;border:1px solid #485263}table{border-collapse:collapse}</style>'
                '<h1>Log-to-Map Diagnosebericht</h1><p>'+esc(log.path)+f' · {log.sample_count} Messpunkte</p>'
                '<p>'+esc(analysis['explanation'])+'</p><table><tr><th>Kanal</th><th>Einheit</th><th>Gültig</th><th>Min</th><th>Max</th></tr>'+rows+'</table><ul>'+notes+'</ul>'+cells)
    atomic_write(path,document.encode('utf-8'),protected=(log.path,*protected))
