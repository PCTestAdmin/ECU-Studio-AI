"""Strict read-only Intel HEX and Motorola S-record parsers.

Parses records with byte-level checksums, addresses and overlaps checked. Sparse
images are never silently filled; callers explicitly choose a gap filler.
These parsers do not infer ECU memory maps or fix ECU checksums.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryRecord:
    address: int
    payload: bytes


@dataclass
class MemoryImage:
    records: list[MemoryRecord]
    format: str
    entry_address: int | None = None

    def __post_init__(self):
        if not self.records:
            raise ValueError('Keine Nutzdaten im Speicherabbild')
        self.records.sort(key=lambda r: r.address)
        last = -1
        for r in self.records:
            if r.address < 0 or not r.payload or r.address + len(r.payload) > 0x1_0000_0000:
                raise ValueError('Speicheradresse außerhalb 32-Bit-Bereich')
            if r.address < last:
                raise ValueError(f'Überlappende Speicherrecords bei 0x{r.address:X}')
            last = r.address + len(r.payload)
        if last - self.start > 128*1024*1024:
            raise ValueError('Zusammenhängendes Speicherfenster > 128 MiB')

    @property
    def start(self) -> int:
        return self.records[0].address

    @property
    def end(self) -> int:
        return self.records[-1].address + len(self.records[-1].payload)

    @property
    def payload_bytes(self) -> int:
        return sum(len(r.payload) for r in self.records)

    @property
    def gap_bytes(self) -> int:
        return self.end - self.start - self.payload_bytes

    @property
    def segments(self) -> list[tuple[int,int]]:
        """Merged contiguous address intervals [start,end), independent of records."""
        merged=[]
        for r in self.records:
            a,b=r.address,r.address+len(r.payload)
            if merged and merged[-1][1] == a:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a,b))
        return merged

    def to_binary(self, *, fill: int | None = None) -> bytes:
        if self.gap_bytes and (type(fill) is not int or not 0 <= fill <= 255):
            raise ValueError(f'{self.gap_bytes:,} Byte Adresslücken: Füllbyte ausdrücklich angeben')
        if fill is not None and (type(fill) is not int or not 0 <= fill <= 255):
            raise ValueError('Ungültiges Füllbyte')
        out = bytearray([fill if fill is not None else 0] * (self.end-self.start))
        for r in self.records:
            pos=r.address-self.start
            out[pos:pos+len(r.payload)] = r.payload
        return bytes(out)


def _hexbytes(payload: str, line: int) -> bytes:
    if len(payload)%2:
        raise ValueError(f'Zeile {line}: ungerade Zahl Hex-Zeichen')
    try:return bytes.fromhex(payload)
    except ValueError as exc:raise ValueError(f'Zeile {line}: unzulässiger Hex-Wert') from exc


DOS_EOF='\x1a'


def _intel_hex(source: str) -> MemoryImage:
    records=[]
    base=0
    eof=False
    entry=None
    for num,raw in enumerate(source.splitlines(),1):
        line=raw.strip()
        if not line:continue
        # A lone Ctrl-Z (0x1A) is the DOS end-of-file marker many Windows tools
        # append after the EOF record; it carries no data. Anything else is refused.
        if eof and line==DOS_EOF:continue
        if eof:raise ValueError(f'Zeile {num}: Daten nach Intel-HEX-EOF')
        if not line.startswith(':'):raise ValueError(f'Zeile {num}: kein Intel-HEX-Record')
        record=_hexbytes(line[1:],num)
        if len(record)<5 or record[0]+5!=len(record):
            raise ValueError(f'Zeile {num}: Intel-HEX-Länge inkorrekt')
        if sum(record)%256 != 0:
            raise ValueError(f'Zeile {num}: Intel-HEX-Prüfsumme ungültig')
        count,address_hi,address_lo,record_type=record[:4]
        addr=address_hi*256+address_lo
        data=record[4:-1]
        if record_type==0x00:
            if data:records.append(MemoryRecord(base+addr,data))
        elif record_type==0x01:
            if count or addr:raise ValueError(f'Zeile {num}: ungültiger EOF-Record')
            eof=True
        elif record_type==0x02:
            if count!=2 or addr:raise ValueError(f'Zeile {num}: ungültiger Segment-Adressrecord')
            base=int.from_bytes(data,'big') << 4
        elif record_type==0x04:
            if count!=2 or addr:raise ValueError(f'Zeile {num}: ungültiger Linear-Adressrecord')
            base=int.from_bytes(data,'big') << 16
        elif record_type==0x03:
            if count!=4 or addr:raise ValueError(f'Zeile {num}: ungültiger Start-Segment-Record')
            cs,ip=int.from_bytes(data[:2],'big'),int.from_bytes(data[2:],'big')
            entry=cs*16+ip
        elif record_type==0x05:
            if count!=4 or addr:raise ValueError(f'Zeile {num}: ungültiger Start-Linear-Record')
            entry=int.from_bytes(data,'big')
        else:raise ValueError(f'Zeile {num}: unbekannter Recordtyp 0x{record_type:02X}')
    if not eof:raise ValueError('Intel-HEX-EOF fehlt')
    return MemoryImage(records,'Intel HEX',entry)


def _srec(source: str) -> MemoryImage:
    records=[]
    terminated=False
    entry=None
    data_count=0
    declared_count=None
    addr_sizes={'0':2,'1':2,'2':3,'3':4,'5':2,'6':3,'7':4,'8':3,'9':2}
    for num,raw in enumerate(source.splitlines(),1):
        line=raw.strip()
        if not line:continue
        if terminated and line==DOS_EOF:continue
        if terminated:raise ValueError(f'Zeile {num}: Daten nach S-Record-Abschluss')
        kind=line[1:2]
        if len(line)<4 or line[0] != 'S' or kind not in addr_sizes:
            raise ValueError(f'Zeile {num}: unbekannter S-Record-Typ')
        data=_hexbytes(line[2:],num)
        if len(data)<2 or data[0]+1!=len(data) or data[0]<addr_sizes[kind]+1:
            raise ValueError(f'Zeile {num}: S-Record-Länge inkorrekt')
        if sum(data)%256 != 255:
            raise ValueError(f'Zeile {num}: S-Record-Prüfsumme ungültig')
        width=addr_sizes[kind]
        address=int.from_bytes(data[1:1+width],'big')
        payload=data[1+width:-1]
        if kind in ('1','2','3'):
            if payload:records.append(MemoryRecord(address,payload))
            data_count+=1
        elif kind in ('5','6'):
            if payload or declared_count is not None:raise ValueError(f'Zeile {num}: ungültiger S-Count-Record')
            declared_count=address
        elif kind in ('7','8','9'):
            if payload:raise ValueError(f'Zeile {num}: unerwartete Nutzdaten in End-Record')
            entry=address
            terminated=True
    if not terminated:raise ValueError('Motorola-S-Record-Abschluss (S7/S8/S9) fehlt')
    if declared_count is not None and declared_count!=data_count:
        raise ValueError('Motorola-S-Record-Anzahl stimmt nicht')
    return MemoryImage(records,'Motorola S-Record',entry)


def parse_memory_text(source: str, *, format: str = 'auto') -> MemoryImage:
    data = source.lstrip('\ufeff \r\n\t')
    if format=='auto':
        format = 'intel' if data.startswith(':') else 'srec' if data.startswith('S') else 'unknown'
    if format=='intel':return _intel_hex(data)
    if format=='srec':return _srec(data)
    raise ValueError('Unbekanntes Dateiformat (Intel HEX oder Motorola S-Record erwartet)')


def read_memory_file(path: str) -> MemoryImage:
    p=Path(path)
    if p.stat().st_size > 128*1024*1024:
        raise ValueError('Quelldatei größer als 128 MiB')
    return parse_memory_text(p.read_text(encoding='utf-8-sig'))
