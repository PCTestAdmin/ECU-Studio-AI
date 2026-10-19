"""CLI-v1.7 parity and end-to-end demo proof with no Qt dependency."""
from pathlib import Path
from ecu_studio.tools.pro_workflows import build_parser, execute

ROOT=Path(__file__).resolve().parents[1]

def test_cli_scan_and_comparison_seed(tmp_path):
    parser=build_parser()
    args=parser.parse_args(['--db',str(tmp_path/'db.sqlite'),'scan',str(ROOT/'examples/demo_synthetic.bin'),'--axes'])
    result=execute(args)
    assert {4096,8192}.issubset({m['offset'] for m in result['candidates']})
    assert all(m['name']=='Unbekannt' and not m['verified'] for m in result['candidates'])
    args=parser.parse_args(['--db',str(tmp_path/'db.sqlite'),'compare',
        str(ROOT/'examples/demo_synthetic.bin'),str(ROOT/'examples/demo_modified_synthetic.bin'),
        '--maps',str(ROOT/'examples/demo_definitions.csv'),
        '--csv',str(tmp_path/'maps.csv'),'--cells-csv',str(tmp_path/'cells.csv')])
    cmp=execute(args)
    assert cmp['changed_bytes']==3 and cmp['changed_bytes_outside_maps']==1
    assert cmp['maps_changed']==2 and len(cmp['cell_changes'])==2
    assert (tmp_path/'maps.csv').is_file() and (tmp_path/'cells.csv').is_file()


def test_cli_brand_coverage_doesnt_upgrade_source_to_training(tmp_path):
    parser=build_parser()
    r=execute(parser.parse_args(['--db',str(tmp_path/'db.sqlite'),'coverage']))
    assert r['source_records']>=7
    assert r['verified_firmware_maps_across_all_brands']==0
    assert r['source_only_not_training']==r['source_records']
    r=execute(parser.parse_args(['--db',str(tmp_path/'db.sqlite'),'coverage','--brand','Mercedes-Benz']))
    assert r['source_records_by_brand']['Mercedes-Benz']>=1
    assert r['verified_firmware_maps_across_all_brands']==0
