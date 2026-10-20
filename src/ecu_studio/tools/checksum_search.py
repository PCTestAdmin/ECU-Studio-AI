"""Find range/algorithm hypotheses for a stored checksum and write a draft profile.

Usage:
  python -m ecu_studio.tools.checksum_search BIN --at 0x7FFE [--at ...] [--confirm OTHER.bin ...]
                                             [--step 0x100] [--out draft.json]

Hypotheses are printed with the expected number of chance matches. Only those
that also hold on every --confirm file are written to the draft. The draft has
reviewed=false and is refused by the verifier until a person reviews it.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.checksum_search import search_checksums, confirm, draft_profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bin')
    parser.add_argument('--at', action='append', required=True, type=lambda v: int(v, 0),
                        help='Dateioffset des gespeicherten Prüfwerts')
    parser.add_argument('--confirm', action='append', default=[], help='weitere Datei gleicher Software')
    parser.add_argument('--step', type=lambda v: int(v, 0), default=0x100)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    image = BinaryImage.from_file(args.bin)
    result = search_checksums(image.read(0, image.size), args.at, step=args.step)
    hyps = result['hypotheses']
    print(f"{result['tested']} Kombinationen geprüft, {len(hyps)} Treffer; "
          f"zufällig erwartet: {result['expected_chance_matches']}")
    if args.confirm:
        hyps = confirm(hyps, [Path(p).read_bytes() for p in args.confirm])
        print(f'{len(hyps)} Hypothese(n) gelten auch auf allen {len(args.confirm)} Vergleichsdatei(en).')
    elif hyps:
        print('Ohne --confirm sind Treffer nicht von Zufall zu unterscheiden.')
    for h in hyps[:40]:
        print(f'  {h.algorithm:16s} 0x{h.start:06X}–0x{h.end:06X} → 0x{h.storage_offset:06X} '
              f'{h.endian} Komplement={h.complement} (gilt auf {h.confirmed_on} Datei(en))')
    if args.out:
        args.out.write_text(json.dumps(draft_profile(image, hyps, f'checksum_search {Path(args.bin).name}'),
                                       indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Entwurf geschrieben: {args.out} (reviewed=false – vor Nutzung manuell prüfen)')


if __name__ == '__main__':
    main()
