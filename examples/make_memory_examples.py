"""Generate two small, entirely fictional sparse memory-record examples."""
from pathlib import Path


def ihex(address, kind, data=b''):
    raw=bytes((len(data),(address>>8)&255,address&255,kind))+data
    return ':'+(raw+bytes([(-sum(raw))%256])).hex().upper()


def srec(kind,address,data=b''):
    widths={'2':3,'8':3}
    content=address.to_bytes(widths[kind],'big')+data
    raw=bytes([len(content)+1])+content
    return 'S'+kind+(raw+bytes([(~sum(raw))&255])).hex().upper()


def main(folder=None):
    dest=Path(folder) if folder else Path(__file__).resolve().parent
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'memory_import_demo.hex').write_text('\n'.join([
        ihex(0,4,b'\x00\x80'),
        ihex(0x0100,0,b'\x10\x20\x30\x40'),
        ihex(0x0110,0,b'\x50\x60'),
        ihex(0,1),
    ])+'\n',encoding='ascii')
    (dest/'memory_import_demo.srec').write_text('\n'.join([
        srec('2',0x801000,b'\x10\x20\x30\x40'),
        srec('2',0x801010,b'\x50\x60'),
        srec('8',0x801000),
    ])+'\n',encoding='ascii')


if __name__=='__main__':main()
