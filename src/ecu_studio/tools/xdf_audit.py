"""Standalone CLI: audit exact XDF-to-BIN importability without modifying files."""
from __future__ import annotations
import argparse
from pathlib import Path
from ..core.model import BinaryImage
from ..core.xdf import read_xdf
from ..core.profiles import identify_profile, xdf_match_status


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description='XDF-Katalog gegen BIN prüfen (nur lesend)')
    parser.add_argument('bin',help='originale BIN/ORI-Datei')
    parser.add_argument('xdf',help='zugehörige TunerPro-XDF')
    parser.add_argument('--csv',help='vollständigen Ergebnisbericht als CSV schreiben')
    parser.add_argument('--limit',type=int,default=25,help='Anzahl angezeigter Kennfeldnamen')
    args=parser.parse_args(argv)
    image=BinaryImage.from_file(args.bin)
    profile=identify_profile(image)
    result=read_xdf(args.xdf,image)
    print(f'Datei: {Path(args.bin).name} · {image.size:,} Bytes · SHA-256 {image.digest[:16]}…')
    print(f'ECU-Profil: {profile.family} · Software {profile.software_version or "unbekannt"}')
    status, explanation=xdf_match_status(profile,args.xdf,result.title)
    print('Kompatibilitätsprüfung:',status,'—',explanation)
    print(result.summary())
    for m in result.maps[:max(0,args.limit)]:
        print(f'  {m.name[:70]:70}  0x{m.offset:06X}  '
              f'{m.rows}x{m.cols} {m.dtype}  {m.kind}')
    if args.csv:
        result.write_audit_csv(args.csv)
        print(f'Importbericht: {Path(args.csv).resolve()}')
    print('Achtung: Definitionsimport belegt keine Firmware-Kompatibilität oder Flashbarkeit.')
    return 3 if status=='rejected' else (0 if result.maps else 2)


if __name__=='__main__':
    raise SystemExit(main())
