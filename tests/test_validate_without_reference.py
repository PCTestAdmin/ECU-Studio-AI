import json


def test_scan_only_row_is_experimental_and_anonymous(tmp_path):
    from ecu_studio.core.showcase import generate_showcase
    from ecu_studio.tools.support_matrix import build, markdown
    from ecu_studio.tools.validate_pair import main
    path = generate_showcase(str(tmp_path))
    renamed = path.with_name('Kunde_Mustermann_WVWZZZ1KZ6W000001.bin')
    path.rename(renamed)
    results = tmp_path / 'ergebnisse.json'
    assert main([str(renamed), '--family', 'Bosch MG1CS002', '--results', str(results)]) == 0
    row = json.loads(results.read_text(encoding='utf-8'))['rows'][0]
    assert row['no_reference'] and row['found_2d'] > 0
    assert 'Mustermann' not in row['name'] and 'WVWZZZ' not in json.dumps(row)   # file name never stored
    data = build([{'rows': [row]}])
    mg1 = next(e for e in data['entries'] if e['family'].startswith('Bosch MG1'))
    assert mg1['status'] == 'experimentell'      # never 'validiert' without a reference
    assert 'ohne Referenz' in markdown(data)
