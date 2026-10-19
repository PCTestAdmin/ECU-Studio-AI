"""Measure CPU decoding / peak sampling only; not Qt rendering or Windows scroll FPS."""
from __future__ import annotations
import argparse
from pathlib import Path
import statistics
from time import perf_counter
from ..core.model import BinaryImage
from ..core.raw_trace import raw_trace


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument('file',help='BIN / ORI path')
    p.add_argument('--runs',type=int,default=80)
    p.add_argument('--count',type=int,default=32768)
    args=p.parse_args(argv)
    img=BinaryImage.from_file(args.file)
    if args.runs < 1: raise ValueError('--runs muss >=1 sein')
    results=[]
    max_start=max(1,img.size//2-args.count)
    for i in range(args.runs):
        start=((i*731)%max_start)*2
        begin=perf_counter()
        raw_trace(img,start,min(args.count,65536),'u16','little',max_points=1200)
        results.append((perf_counter()-begin)*1000)
    print(f'{Path(args.file).name}: {args.runs} Fensterwechsel · '
          f'Median CPU-Dekodierung {statistics.median(results):.3f} ms · '
          f'95%-Perzentil {sorted(results)[int(.95*(len(results)-1))]:.3f} ms')
    print('Nicht enthalten: Qt-Repaint, GPU/Windows, Massenspeicher oder GUI-Reaktionszeit.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
