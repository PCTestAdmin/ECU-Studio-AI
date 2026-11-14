"""Conservative count/axis/table record discovery, independent of fixed grids.

Supported *hypothesis*: nx,ny,X[nx],Y[ny],Z[ny,nx], packed, with byte or
word counts and byte/word axes. This is not a universal ECU record decoder.
No physical units or functional names can be inferred from this layout alone.
"""
from __future__ import annotations
from functools import lru_cache
import bisect
import numpy as np
from .model import BinaryImage, MapDefinition
from .axis_inference import _plausibility
from .precision import surface_evidence, narrower_storage_alias, preferred_sign


def _steps(values) -> list:
    return [b-a for a,b in zip(values,values[1:])]


def _monotone(d) -> bool:
    return all(x>0 for x in d) or all(x<0 for x in d)


def _record_axis(values):
    # Plain Python: axes have at most 32 points, where NumPy call overhead
    # dominated the record scan (300 000 calls on a 2 MB image).
    d=_steps(values)
    if not _monotone(d):return False
    # A single jump swallowing almost the whole axis is weak record evidence.
    # Explicit source definitions remain exempt from this discovery heuristic.
    if max(abs(x) for x in d)>.75*abs(values[-1]-values[0]):return False
    return bool(_plausibility(values if d[0]>0 else [-v for v in values]))


def _sign_rank(image: BinaryImage, m: MapDefinition) -> int:
    """0 for the preferred reading of equally scored u16/s16 hypotheses."""
    if m.width not in (1,2):
        return 0
    raw=np.frombuffer(image.read(m.offset,m.length),np.uint8)
    top=bool(np.any((raw if m.width==1 else raw[0::2] if m.endian=='big' else raw[1::2])>=0x80))
    return int(m.dtype.startswith('s')!=top)


def _strict(values) -> bool:
    return _monotone(_steps(values))


def _axis_pair(x, y, wide: bool = True, check=None) -> bool:
    """Both axes plausible; with 16-bit counts and axes one may be relaxed.

    The count header already fixes both lengths, so one axis may carry an
    index (0..n) or a single wide step (e.g. 6000 -> 12000 rpm) as long as the
    other one looks like a breakpoint axis. Only for 16-bit counts and axes
    (``wide``): a byte count of 4..32 occurs by chance every ninth byte, and the
    relaxed rule produced a header in random data (negative control, 2 MB).
    """
    check = check or _record_axis
    if not wide:
        return check(x) and check(y)
    return _strict(x) and _strict(y) and (check(x) or check(y))


CHAIN_GAP=4   # alignment padding between consecutive records


def _chained(rough: list[MapDefinition], accepted: list[MapDefinition]) -> list[MapDefinition]:
    """Noisy-valued records that touch another accepted record (packed record lists).

    Measured on complete A2L (development): noisy records without a neighbour
    added about as many false as true tables; inside a chain they are records.
    """
    heads=np.array(sorted({m.candidate_region_start for m in accepted}),dtype=np.int64)
    ends=np.array(sorted({m.offset+m.length for m in accepted}),dtype=np.int64)
    def near(sorted_a,lo,hi):
        k=np.searchsorted(sorted_a,lo)
        return k<len(sorted_a) and sorted_a[k]<=hi
    return [m for m in rough if near(heads,m.offset+m.length,m.offset+m.length+CHAIN_GAP)
            or near(ends,m.candidate_region_start-CHAIN_GAP,m.candidate_region_start)]


def _bounded_by_next_header(flat: list[MapDefinition], accepted: list[MapDefinition]) -> list[MapDefinition]:
    """Flat records whose value width differs from the axes, kept where it is fixed.

    Flat values do not show their width; the next accepted record header does when it
    starts exactly at the end of this reading (up to HEADER_PAD alignment bytes) and at no
    other width's end. MSD80 (development data) stores byte tables behind 16-bit axes
    (``_REC_MAP_52_u1_s2_s2``), packed in record lists (1.21.0).
    """
    gap=_header_gaps([(0,m) for m in accepted])
    out=[]
    for m in flat:
        mine=gap(m.offset+m.length)
        other=gap(m.offset+m.rows*m.cols*(3-m.width))     # the other width's reading
        if mine is not None and (other is None or mine<other):
            m.label_origin=SHAPE_ONLY_ORIGIN
            m.notes+=(f' Werte ohne glatte Oberfläche: Wertebreite {m.width} Byte, weil der nächste '
                      'Datensatzkopf genau danach beginnt (ungeprüft).')
            out.append(m)
    return out


SIGN_BY_WRAPS = True


def _sign_by_wraps(image: BinaryImage, found: list) -> list:
    """Of unsigned and signed readings of the same bytes, keep the one preferred_sign names.

    Before 1.21.0 the smoother (range-normalised) surface decided, which reads a
    signed byte table with values around zero as unsigned with a wrap. Readings
    whose bytes do not decide the sign stay as before.
    """
    groups={}
    for sc,m in found:
        groups.setdefault((m.offset,m.rows,m.cols,m.width,m.endian),[]).append((sc,m))
    out=[]
    for (off,rows,cols,width,endian),items in groups.items():
        signs={m.dtype[0] for _,m in items}
        if len(signs)>1:
            pick=preferred_sign(image.read(off,rows*cols*width),rows,cols,width,endian)
            if pick is not None:
                chosen=[(sc,m) for sc,m in items if m.dtype[0]==pick]
                if chosen:
                    items=chosen
                    for _,m in items:
                        m.notes+=(' Vorzeichen: Lesart ohne Überlauf benachbarter Zellen'
                                  + (' (vorzeichenbehaftet).' if pick=='s' else ' (vorzeichenlos).'))
        out.extend(items)
    return out


NESTED_HEADERS = True


def _drop_nested_headers(found: list) -> list:
    """Drop readings whose header lies inside the counts/axes of another reading.

    Axis points of a real record read as counts plus shorter axes (8-bit or mixed
    widths) as well. Such a reading starts strictly between another reading's header
    and its data; outer readings that are themselves nested do not count. Development
    data (MEVD17.2, MSD80, 6 images): 569 such readings off the reference, 8 on it
    (1.21.0).
    """
    def span(m):
        return (m.candidate_region_start if m.candidate_region_start is not None else m.offset), m.offset
    spans = sorted({span(m) for _, m in found if span(m)[0] < span(m)[1]})
    starts = [h for h, _ in spans]

    def inside(h, d, pool, keys):
        # any (h2, d2) in pool with h2 < h < d2, other than (h, d) itself
        i = bisect.bisect_left(keys, h)
        return any(h2 < h < d2 for h2, d2 in pool[max(0, i - 64):i] if (h2, d2) != (h, d))
    outer = [x for x in spans if not inside(x[0], x[1], spans, starts)]
    keys = [h for h, _ in outer]
    return [(sc, m) for sc, m in found if not inside(*span(m), outer, keys)]


NEXT_HEADER_WIDTH = True
HEADER_PAD = 3     # alignment bytes before the next header (MSD80 aligns records to 4 bytes)


def _header_gaps(found: list):
    """gap(end) -> bytes from ``end`` to the next accepted header (0..HEADER_PAD), or None."""
    heads=np.array(sorted({m.candidate_region_start for _,m in found}),dtype=np.int64)
    def gap(end):
        if not len(heads):
            return None
        k=np.searchsorted(heads,end)
        return int(heads[k]-end) if k<len(heads) and heads[k]-end<=HEADER_PAD else None
    return gap


def _width_by_next_header(found: list) -> list:
    """Of the value widths read behind one header, keep the one the next header confirms.

    Byte values often read as a valid 16-bit table too (and the reverse). In packed
    record lists the next accepted header starts right behind the true table, after
    at most HEADER_PAD alignment bytes. The width whose end lies closest before a
    header wins when no other width is as close; otherwise all widths stay. MSD80
    (development data): 36 byte tables read as 16 bit, each pushing the next record
    out as an overlap; records there are 4-byte aligned (1.21.0).
    """
    gap=_header_gaps(found)
    groups={}
    for sc,m in found:
        groups.setdefault((m.candidate_region_start,m.offset,m.rows,m.cols),[]).append((sc,m))
    out=[]
    for items in groups.values():
        widths={m.width for _,m in items}
        if len(widths)>1:
            m0=items[0][1]
            gaps={w:gap(m0.offset+m0.rows*m0.cols*w) for w in widths}
            close=sorted((g,w) for w,g in gaps.items() if g is not None)
            if close and (len(close)==1 or close[0][0]<close[1][0]):
                w=close[0][1]
                items=[(sc,m) for sc,m in items if m.width==w]
                for _,m in items:
                    m.notes+=f' Wertebreite {w} Byte: der nächste Datensatzkopf beginnt genau danach.'
        out.extend(items)
    return out


FLAT_REASON='Konstant/zu wenig Dynamik'
ROUGH_REASON='Zu verrauscht oder eindimensional'
FLAT_SCORE=.05   # ranked after every table with a coherent surface
# Own evidence class (confidence.py): shape from header and axes only, values unverified.
SHAPE_ONLY_ORIGIN='Dimensionsheader + zwei monotone Rohachsen, Werte ohne Oberflächenbeleg (ungeprüft)'


def _flat_record(m: MapDefinition, axis_width: int, kind: str, image: BinaryImage) -> bool:
    """Accept a constant or coarse value block when the header alone fixes the shape.

    Calibrations keep many flat tables (unused functions, one value everywhere).
    Their surface carries no evidence, but count header plus two monotone,
    plausible axes do. The value width cannot be read from flat data, so only the
    axis width is accepted (one candidate, no width guessing); the sign is signed
    only if the axes are signed or the values look negative. Measured on the
    complete EDC17CP09 A2L (development): 257 of 443 headed records with valid
    axes were flat and had been dropped.
    """
    if m.width!=axis_width or m.dtype in ('u32','s8'):
        return False
    if axis_width==2:
        raw=np.frombuffer(image.read(m.offset,m.length),('<' if m.endian=='little' else '>')+'u2')
        negative=kind=='i' or bool(np.any(raw>=0x8000))
        if m.dtype!=('s16' if negative else 'u16'):
            return False
    m.label_origin=SHAPE_ONLY_ORIGIN
    m.notes+=' Werte ohne glatte Oberfläche: Größe nur durch Kopf und Achsen belegt, Wertebreite = Achsenbreite (ungeprüft).'
    return True


def _x_axis_possible(buf: bytes, counts: np.ndarray, starts: np.ndarray, phase: int,
                     count_width: int, endian: str) -> np.ndarray:
    """Vectorised pre-filter: headers whose X axis is strictly monotone in some tried reading.

    Every accepted record needs that (both axis rules require strict X), so the
    filter only skips headers the loop below would reject anyway; results are
    unchanged, the record scan gets several times faster.
    """
    b=np.frombuffer(buf,np.uint8).astype(np.int64)
    keep=np.zeros(len(starts),bool)
    cols=counts[starts].astype(np.int64)
    axis_start=phase+starts.astype(np.int64)*count_width+2*count_width
    for axis_width in (1,2):
        for order in (['big'] if axis_width==1 else ['big','little']):
            if count_width==2 and axis_width==2 and order!=endian:continue
            for c in np.unique(cols).tolist():
                sel=np.flatnonzero((cols==c)&~keep)
                if not len(sel):continue
                pos=axis_start[sel][:,None]+axis_width*np.arange(c)[None,:]
                ok=pos[:,-1]+axis_width<=len(b)
                sel,pos=sel[ok],pos[ok]
                if axis_width==1:
                    v=b[pos]
                    variants=(v,)
                else:
                    hi,lo=(b[pos],b[pos+1]) if order=='big' else (b[pos+1],b[pos])
                    v=hi*256+lo
                    variants=(v,np.where(v>=0x8000,v-0x10000,v))
                for w in variants:
                    d=np.diff(w,axis=1)
                    keep[sel[np.all(d>0,axis=1)|np.all(d<0,axis=1)]]=True
    return keep


# Axis widths (X, Y): MSD80 records mix them (16-bit X with 8-bit Y and the reverse; 1.21.0).
AXIS_WIDTHS = ((1, 1), (2, 2), (1, 2), (2, 1))
# Value types; s8 since 1.21.0 (signed byte tables, e.g. MSD80 _REC_MAP_52_UBYTE_s1_s2_s2).
DATA_TYPES = ('u8', 's8', 'u16', 's16', 'u32')


def _axis_values(buf: bytes, at: int, n: int, width: int, order: str, kind: str) -> list:
    """n axis points; 8-bit axes are read unsigned, 16-bit ones in ``order`` and ``kind``."""
    if width == 1:
        return list(buf[at:at + n])
    return np.frombuffer(buf[at:at + 2 * n], ('>' if order == 'big' else '<') + kind + '2').tolist()


ORDER_MIN = 20     # records whose 16-bit counts or axes fix the byte order, before the image votes
ORDER_RATIO = 2.   # majority needed: one CPU, one byte order (1.21.0)
BYTE_ORDER = True


def _image_order(orders: list[str]) -> str | None:
    """Byte order of the image from records whose 16-bit counts or axes fix it, or None.

    One CPU stores all records in one byte order; readings in the other order that
    pass anyway are coincidences. Development data (MEVD17.2 and MSD80 calibrations,
    TriCore): 412-469 records read little endian, 120-177 big endian by chance.
    """
    votes = {o: orders.count(o) for o in ('big', 'little')}
    best, other = sorted(votes, key=votes.get, reverse=True)
    if votes[best] >= ORDER_MIN and votes[best] >= ORDER_RATIO * votes[other]:
        return best
    return None


def _reorder_axes(image: BinaryImage, m: MapDefinition, order: str) -> bool:
    """Re-read the 16-bit axes of an 8-bit-count record in the image byte order.

    Index axes (0, 1, 2 ...) fail the plausibility rule and pass byte-swapped (0, 256,
    512 ...): the header found the record, only the axis byte order was wrong. Kept
    when both axes are strictly monotone in the image order; 16-bit counts in the other
    order are not re-read (their values change, so does the shape).
    """
    n=m.cols+m.rows
    if m.candidate_region_start is None or m.axis_x_offset is None:
        return False
    if m.axis_x_offset-m.candidate_region_start!=2 or m.offset-m.axis_x_offset!=2*n:
        return False
    for kind in ('u','i'):
        v=np.frombuffer(image.read(m.axis_x_offset,2*n),('<' if order=='little' else '>')+kind+'2').tolist()
        x,y=v[:m.cols],v[m.cols:]
        if _strict(x) and _strict(y):
            m.axes_x,m.axes_y=x,y
            m.notes+=(f' Achsen in Byte-Reihenfolge {order} gelesen (Mehrheit der Datensätze dieses Abbilds); '
                      'Stützstellen ohne Plausibilitätsprüfung (z. B. Indexachse).')
            return True
    return False


def scan_axis_records(image: BinaryImage, *, max_results=40, cancelled=None, include_u32=False,
                      evidence_cache_size=512):
    if type(evidence_cache_size) is not int or not 0 <= evidence_cache_size <= 512:
        raise ValueError('Evidence cache size must be between 0 and 512')
    if max_results <= 0 or image.size < 32:return []
    # Surface/width checks depend only on packed values and their interpretation,
    # not on file position or axis labels. Repeating flash patterns used to run
    # identical NumPy percentile/alias checks tens of thousands of times. Bound
    # this cache to one scan; firmware bytes never remain in a global cache.
    @lru_cache(maxsize=evidence_cache_size)
    def value_evidence(rows, cols, dtype, endian, raw):
        sample = BinaryImage(raw)
        view = MapDefinition('', 0, rows, cols, dtype, endian)
        ev = surface_evidence(sample.matrix(view), min_unique=4)
        alias = ev['valid'] and narrower_storage_alias(sample, view, ev)
        return ev, alias

    # Same axis values recur at many header hypotheses (ramps: 140 distinct in
    # 35 649 checks); also bound to this scan.
    @lru_cache(maxsize=4096)
    def axis_ok(values):
        return _record_axis(list(values))

    def record_axis(values):
        return axis_ok(tuple(values))
    buf=image.read(0,min(image.size,2*1024*1024))
    found=[]
    rough=[]   # header + axes fine, values noisy: kept only inside a chain of records
    fixed={}   # id(record) -> (byte order its 16-bit counts or axes fix, record)
    flat_other=[]   # flat values of another width than the axes: kept when the next header fixes it
    for count_width in (1,2):
        for endian in (['big'] if count_width==1 else ['big','little']):
            for phase in range(count_width):
                usable=(len(buf)-phase)//count_width*count_width
                counts=np.frombuffer(buf[phase:phase+usable],dtype=('>' if endian=='big' else '<')+'u'+str(count_width))
                if len(counts)<2:continue
                starts=np.flatnonzero((counts[:-1]>=4)&(counts[:-1]<=32)&
                                     (counts[1:]>=4)&(counts[1:]<=32))
                starts=starts[_x_axis_possible(buf,counts,starts,phase,count_width,endian)]
                for ix,index in enumerate(starts):
                    if ix%128==0 and cancelled and cancelled():return []
                    cols,rows=int(counts[index]),int(counts[index+1])
                    header=phase+int(index)*count_width
                    axis_start=header+2*count_width
                    for xw,yw in AXIS_WIDTHS:
                        end=axis_start+cols*xw+rows*yw
                        if end+rows*cols>len(buf):continue
                        wide=xw==2 or yw==2
                        for order in (['big','little'] if wide else ['big']):
                            if count_width==2 and wide and order!=endian:continue
                            # Signed 16-bit axes (temperatures, Bosch EDC17 SWORD layouts) only
                            # rise when read signed; unsigned reading is tried first.
                            for kind in (('u','i') if wide else ('u',)):
                                x=_axis_values(buf,axis_start,cols,xw,order,kind)
                                y=_axis_values(buf,axis_start+cols*xw,rows,yw,order,kind)
                                if kind=='i' and min((x if xw==2 else [])+(y if yw==2 else []))>=0:continue
                                if _axis_pair(x,y,count_width==2 and xw==yw==2,record_axis):break
                            else:
                                continue
                            for dtype in DATA_TYPES:
                                if dtype=='u32' and not include_u32:continue
                                for storage in (['big'] if dtype[1:]=='8' else ['big','little']):
                                    if dtype[1:]!='8' and ((wide and storage!=order) or
                                                          (count_width==2 and storage!=endian)):continue
                                    axes_note=(f'{xw*8}-Bit Achsen' if xw==yw else f'{xw*8}-Bit X-/{yw*8}-Bit Y-Achse')
                                    m=MapDefinition(f'Achsen-/Header-Kandidat @ 0x{end:08X}',end,rows,cols,
                                        dtype,storage,source='heuristic',confidence=.44,
                                        axes_x=x,axes_y=y,
                                        axis_x_offset=axis_start,axis_y_offset=axis_start+cols*xw,
                                        record_layout='candidate:nx,ny,x,y,z',
                                        candidate_region_start=header,
                                        axes_info='Rohachsen aus Count/Axis-Hypothese; Einheiten und Orientierung ungeprüft',
                                        label_origin='Dimensionsheader + zwei monotone Rohachsen (ungeprüft)',
                                        notes=f'Layout-Hypothese: {count_width*8}-Bit nx/ny, {axes_note} ({order}); keine physikalische Skalierung.')
                                    if end+m.length>len(buf):continue
                                    ev,alias=value_evidence(m.rows,m.cols,m.dtype,m.endian,image.read(m.offset,m.length))
                                    axis_width=xw if xw==yw else 0     # flat values: width only from equal axes
                                    if ev['valid'] and not alias:
                                        found.append((ev['score'],m))
                                    elif ev['reason']==FLAT_REASON and _flat_record(m,axis_width,kind,image):
                                        found.append((FLAT_SCORE,m))
                                    elif (ev['reason']==ROUGH_REASON and record_axis(x) and record_axis(y)
                                          and _flat_record(m,axis_width,kind,image)):
                                        rough.append(m)
                                    elif ev['reason']==FLAT_REASON and m.dtype in ('u8','u16') and m.width!=axis_width:
                                        flat_other.append(m)
                                        continue
                                    else:
                                        continue
                                    if count_width==2 or wide:   # the reference keeps the id unique
                                        fixed[id(m)]=(order if wide else endian,m)
                    if len(found)>max_results*30:
                        found=sorted(found,key=lambda item:-item[0])[:max_results*10]
    found.extend((FLAT_SCORE,m) for m in _chained(rough,[m for _,m in found]))
    found.extend((FLAT_SCORE,m) for m in _bounded_by_next_header(flat_other,[m for _,m in found]))
    order=_image_order([fixed[id(m)][0] for _,m in found if id(m) in fixed]) if BYTE_ORDER else None
    if order:
        # Counts/axes fixed in the other byte order: a coincidence, dropped. Values alone in
        # the other order: the same record in the image order (small values stored in 16 bit
        # read smoother byte-swapped, and their own reading counts as a narrower alias).
        kept=[]
        for sc,m in found:
            if fixed.get(id(m),(order,))[0]!=order and not _reorder_axes(image,m,order):
                continue
            if m.width==2 and m.endian!=order:
                raw=np.frombuffer(image.read(m.offset,m.length),('<' if order=='little' else '>')+'u2')
                m.endian=order
                m.dtype='s16' if bool(np.any(raw>=0x8000)) and m.dtype=='s16' else 'u16'
                m.notes+=(f' Byte-Reihenfolge {order} aus der Mehrheit der Datensätze dieses Abbilds '
                          '(Zähler/Achsen mit 16 Bit), nicht aus den Werten.')
            kept.append((sc,m))
        found=kept
    found=_width_by_next_header(found) if NEXT_HEADER_WIDTH else found
    found=_sign_by_wraps(image,found) if SIGN_BY_WRAPS else found
    found=_drop_nested_headers(found) if NESTED_HEADERS else found
    # One hypothesis per span: u16/s16 readings of the same bytes must not use
    # up the result limit. The better surface wins; on a tie (e.g. all values
    # negative, both readings equally smooth) the signed reading is kept, and
    # the unsigned one where no top bit is set (identical values).
    found.sort(key=lambda item:(-item[0],_sign_rank(image,item[1])))
    unique={}
    for _,m in found:
        unique.setdefault((m.offset,m.rows,m.cols,m.width,m.endian),m)
    return list(unique.values())[:max_results]


RECORD_AXIS_LAYOUT = 'candidate:record-axis'


def record_axes(image: BinaryImage, m: MapDefinition) -> list[MapDefinition]:
    """The X/Y breakpoint arrays of an accepted nx,ny,X,Y,Z header candidate, as 1 x n objects.

    Count and axis widths follow from header position, data start and the point
    counts (unique for 2 + 2 or more points); the byte order and sign are the
    ones that reproduce the axis values the candidate was accepted with.
    """
    if m.record_layout != 'candidate:nx,ny,x,y,z' or m.candidate_region_start is None or not m.axes_x:
        return []
    header = m.candidate_region_start
    for cw in (1, 2):
        for xw, yw in AXIS_WIDTHS:
            start = header + 2 * cw
            if start + m.cols * xw + m.rows * yw != m.offset:
                continue
            for order in ('little', 'big'):
                for kind in ('u', 'i'):
                    x = _axis_values(image.read(start, m.cols * xw), 0, m.cols, xw, order, kind)
                    y = _axis_values(image.read(start + m.cols * xw, m.rows * yw), 0, m.rows, yw, order, kind)
                    if x == list(m.axes_x) and y == list(m.axes_y):
                        def dtype(w):
                            return ('s' if kind == 'i' and w == 2 else 'u') + str(8 * w)
                        return [MapDefinition(f'Achse {label} von 0x{m.offset:08X}', off, 1, count, dtype(w), order,
                                              source='heuristic', confidence=.44, record_layout=RECORD_AXIS_LAYOUT,
                                              candidate_region_start=header,
                                              label_origin='Stützstellen eines Kopf-Datensatzes (ungeprüft)',
                                              label_evidence=f'{label}-Achse des Datensatzes @ 0x{header:X} mit Anzahl-Kopf.',
                                              notes='Achsen-Hypothese aus nx,ny,X,Y,Z-Kopf; Einheit unbekannt.')
                                for label, off, count, w in (('X', start, m.cols, xw), ('Y', start + m.cols * xw, m.rows, yw))]
    return []

