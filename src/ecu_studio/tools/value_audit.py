"""CLI quality report for an explicitly supplied XDF/BIN pair (read-only)."""
from __future__ import annotations
import argparse
from pathlib import Path
from ..core.model import BinaryImage
from ..core.xdf import read_xdf
from ..core.profiles import identify_profile, xdf_match_status
from ..core.quality import audit_catalog, write_quality_csv


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description='Binärwerte, Definitionen und XDF-Zuordnung prüfen; keine Dateiveränderungen')
    p.add_argument('bin',help='ECU-BIN/ORI-Datei')
    p.add_argument('xdf',help='passende XDF-Definitionsdatei')
    p.add_argument('--csv',required=True,help='CSV-Ergebnisdatei')
    args=p.parse_args(argv)
    img=BinaryImage.from_file(args.bin)
    profile=identify_profile(img)
    result=read_xdf(args.xdf,img)
    status,notice=xdf_match_status(profile,args.xdf,result.title)
    if status=='rejected':
        print('ABGEBROCHEN – XDF passt nach Dateikennung nicht zum BIN:', notice)
        return 3
    reports=audit_catalog(img,result.maps)
    write_quality_csv(args.csv,reports)
    invalid=sum(r.status=='REJECT' for r in reports)
    reviews=sum(r.status=='REVIEW' for r in reports)
    print(f'{Path(args.bin).name}: {profile.family} | Software {profile.software_version or "nicht erkannt"}')
    print(f'XDF: {Path(args.xdf).name} | Abgleich: {status} ({notice})')
    print(f'Definitionen: {result.table_count+result.constant_count}; importiert: {len(result.maps)}; '
          f'Verworfene: {sum(result.excluded.values())}')
    print(f'Dekodierfehler: {invalid}; Prüfwarnungen: {reviews}; Bericht: {Path(args.csv).resolve()}')
    print('Kein semantischer Wahrheitsbeweis. Quellfirmware/Patchstand und Fahrzeugsicherheit prüfen!')
    return 4 if invalid else 0


if __name__=='__main__':
    raise SystemExit(main())
