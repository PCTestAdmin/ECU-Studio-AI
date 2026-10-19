"""Hex pattern scan with ?? wildcard, reference diff and reusable patch report."""
import csv
from pathlib import Path
from .model import BinaryImage


def bit_pattern_search(image:BinaryImage,pattern:str,max_hits=500):
    import numpy as np
    bits=''.join(pattern.split()).replace('_','').replace('*','?')
    if not bits or len(bits)%8 or len(bits)>4096 or any(c not in '01?' for c in bits):
        raise ValueError('Bitmuster benötigt 8–4096 Bits (Vielfaches von 8), Zeichen 0/1/?')
    if not 1<=max_hits<=10000:
        raise ValueError('Ungültiges Trefferlimit')
    needles=[]
    for i in range(0,len(bits),8):
        token=bits[i:i+8]
        needles.append((int(''.join('0' if c=='?' else c for c in token),2),
                        int(''.join('0' if c=='?' else '1' for c in token),2)))
    count=max(0,image.size-len(needles)+1)
    hits=[]
    for start in range(0,count,1024**2):
        n=min(1024**2,count-start)
        data=np.frombuffer(image.read(start,n+len(needles)-1),dtype=np.uint8)
        match=np.ones(n,dtype=bool)
        for i,(value,mask) in enumerate(needles):
            if mask:
                match &= (data[i:i+n]&mask)==value
            if not match.any():
                break
        hits.extend((np.flatnonzero(match)+start).tolist()[:max_hits-len(hits)])
        if len(hits)>=max_hits:
            break
    return hits


def raw_value_search(image:BinaryImage,value:int,dtype='u16',endian='big',max_hits=500):
    import struct
    from .model import FORMATS
    if dtype not in FORMATS or endian not in ('big','little') or type(value) is not int:
        raise ValueError('Ungültiger Rohwert/Datentyp/Bytefolge')
    code,width,lo,hi=FORMATS[dtype]
    if not lo<=value<=hi:
        raise ValueError('Rohwert liegt außerhalb des Datentyps')
    pattern=struct.pack(('>' if endian=='big' else '<')+code,value).hex(' ')
    # Full byte-pattern search includes unaligned occurrences intentionally.
    return hex_pattern_search(image,pattern,max_hits)


def hex_pattern_search(image: BinaryImage, pattern: str, max_hits: int = 500) -> list[int]:
    tokens = pattern.replace(",", " ").strip().split()
    if not tokens or len(tokens) > 512:
        raise ValueError("Erwartet 1 bis 512 Hex-Bytes, z. B. 0A FF ?? 20")
    needles = []
    for tok in tokens:
        if tok in ("??", "**"):
            needles.append(None)
        elif len(tok) == 2 and all(c in "0123456789abcdefABCDEF" for c in tok):
            needles.append(int(tok, 16))
        else:
            raise ValueError(f"Ungültiges Hex-Byte: {tok}")
    data = image.materialize()
    pivot = next((i for i, val in enumerate(needles) if val is not None), None)
    if pivot is None:
        return list(range(min(len(data) - len(needles) + 1, max_hits)))
    positions = []
    start = 0
    key = bytes([needles[pivot]])
    while len(positions) < max_hits:
        hit = data.find(key, start)
        if hit < 0:
            break
        offset = hit - pivot
        if offset >= 0 and offset + len(needles) <= len(data):
            if all(v is None or data[offset + i] == v for i, v in enumerate(needles)):
                positions.append(offset)
        start = hit + 1
    return positions


def compare_reference(image: BinaryImage, path: str, max_ranges: int = 250) -> tuple[int, list[tuple[int, int]]]:
    if Path(path).stat().st_size != image.size:
        raise ValueError(f"Dateigrößen unterschiedlich: {Path(path).stat().st_size} vs. {image.size} Bytes")
    reference = Path(path).read_bytes()
    current = image.materialize()
    if len(reference) != len(current):
        raise ValueError(f"Dateigrößen unterschiedlich: {len(reference)} vs. {len(current)} Bytes")
    total = 0
    ranges = []
    begin = None
    for i, (a, b) in enumerate(zip(current, reference)):
        if a != b:
            total += 1
            if begin is None:
                begin = i
        elif begin is not None:
            if len(ranges) < max_ranges:
                ranges.append((begin, i - begin))
            begin = None
    if begin is not None and len(ranges) < max_ranges:
        ranges.append((begin, len(current) - begin))
    return total, ranges


def export_patch_csv(path: str, image: BinaryImage) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file_offset", "original_hex", "modified_hex", "bytes_changed_in_region"])
        for start, original, modified in image.changed_ranges():
            w.writerow([f"0x{start:08X}", original.hex(" ").upper(), modified.hex(" ").upper(), len(original)])
