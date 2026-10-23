import json
import numpy as np
import pytest
from ecu_studio.tools.benchmark_suite import run, group_images, axes_agreement, markdown, main
from ecu_studio.core.model import MapDefinition


def _pair(tmp_path, name, seed, complete=True, role='test'):
    data = bytearray(0x4000)                      # erased-style background; seed varies one byte below
    data[0x3000] = seed
    # Same shape as the structure_scan tests: rows restart low (row wrap), so the pitch is unambiguous.
    t = np.array([[20 + 11 * r + 5 * c + (r * c) % 3 for c in range(9)] for r in range(7)], np.uint8)
    data[0x1000:0x1000 + t.size] = t.tobytes()
    b = tmp_path / f'{name}.bin'; b.write_bytes(bytes(data))
    ref = tmp_path / f'{name}.csv'
    ref.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\n'
                   'T,0x1000,7,9,u8,big,1,0,,Unbekannt,\n', encoding='utf-8')
    return {'name': name, 'family': 'Synthetisch', 'bin': str(b), 'reference': str(ref),
            'complete': complete, 'role': role}


def test_precision_only_for_complete_references_and_roles_are_kept(tmp_path):
    entries = [_pair(tmp_path, 'voll', 1), _pair(tmp_path, 'teil', 2, complete=False, role='development')]
    result = run(entries)
    full, part = result['rows']
    assert full['reference_2d'] == 1 and full['exact_2d'] == 1 and 'precision_2d' in full
    assert full['false_negatives_2d'] == 0
    assert 'precision_2d' not in part and 'false_positives_2d' not in part
    assert result['independent_pairs'] == 1 and part['role'] == 'development'
    assert '| teil |' in markdown(result) and '| – |' in markdown(result)


def test_near_identical_images_share_a_group(tmp_path):
    a = _pair(tmp_path, 'a', 1); b = _pair(tmp_path, 'b', 1); c = _pair(tmp_path, 'c', 3)
    raw = bytearray(open(b['bin'], 'rb').read()); raw[0x10:0x20] = b'' * 16; open(b['bin'], 'wb').write(raw)
    open(c['bin'], 'wb').write(np.random.default_rng(3).integers(0, 256, 0x4000, dtype=np.uint8).tobytes())
    assert group_images([a, b, c]) == [0, 0, 2]


def test_unknown_role_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run([_pair(tmp_path, 'x', 1, role='egal')])


def test_axes_count_as_correct_only_when_linear_and_same_length():
    ref = MapDefinition('r', 0x100, 3, 4, dtype='u8', axes_x=[0, 1000, 2000, 3000], axes_y=[10, 20, 30])
    good = MapDefinition('g', 0x100, 3, 4, dtype='u8', axes_x=[0, 10, 20, 30], axes_y=[1, 2, 3])
    bad = MapDefinition('b', 0x100, 3, 4, dtype='u8', axes_x=[0, 10, 50, 30])
    assert axes_agreement([good], [ref]) == {'with_axes': 1, 'axes_correct': 1}
    assert axes_agreement([bad], [ref]) == {'with_axes': 1, 'axes_correct': 0}


def test_cli_writes_json_and_markdown(tmp_path):
    manifest = tmp_path / 'm.json'
    manifest.write_text(json.dumps([_pair(tmp_path, 'cli', 4)]), encoding='utf-8')
    main([str(manifest), '--out', str(tmp_path / 'r.json'), '--markdown', str(tmp_path / 'r.md')])
    assert json.loads((tmp_path / 'r.json').read_text(encoding='utf-8'))['rows'][0]['name'] == 'cli'
    assert (tmp_path / 'r.md').read_text(encoding='utf-8').startswith('| Paar |')


def _row(name, exact, found, precision=None, sha='x'):
    return {'name': name, 'family': 'F', 'role': 'test', 'sha256': sha, 'complete_reference': precision is not None,
            'exact_2d': exact, 'found_2d': found, 'recall_2d': .5, 'precision_2d': precision, 'exact_1d': 0, 'seconds': 1}


def test_comparison_needs_more_exact_maps_and_stable_precision():
    from ecu_studio.tools.benchmark_suite import compare_runs, comparison_markdown
    before = {'version': '1', 'commit': 'a', 'rows': [_row('up', 10, 20, .80), _row('more', 10, 20), _row('prec', 10, 20, .80),
                                                      _row('down', 10, 20), _row('other', 1, 1, sha='y')]}
    after = {'version': '2', 'commit': 'b', 'rows': [_row('up', 12, 22, .80), _row('more', 10, 30), _row('prec', 12, 40, .70),
                                                     _row('down', 9, 20), _row('other', 1, 1, sha='z')]}
    diff = compare_runs(before, after)
    verdicts = {p['name']: p['verdict'] for p in diff['pairs']}
    assert verdicts == {'up': 'verbessert', 'more': 'nur mehr Kandidaten', 'prec': 'schlechter',
                        'down': 'schlechter', 'other': 'nicht vergleichbar'}
    assert diff['regressions'] == ['prec', 'down']
    assert '10 → 12' in comparison_markdown(diff)


def test_result_names_version_commit_and_reference_provenance(tmp_path):
    entry = dict(_pair(tmp_path, 'prov', 5), source='synthetisch', license='CC0')
    result = run([entry])
    row = result['rows'][0]
    assert result['version'] and 'commit' in result
    assert (row['reference_source'], row['reference_license']) == ('synthetisch', 'CC0')
    assert row['group_pairs_reference'] == 0 and 'Gruppenpaare' in markdown(result)
