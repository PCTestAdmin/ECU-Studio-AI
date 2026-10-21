"""validate_pair: one BIN + definition -> identity, metrics, results file for the support matrix."""
import json
import numpy as np
from ecu_studio.tools import validate_pair


def test_validate_pair_writes_a_matrix_row(tmp_path, capsys):
    data = bytearray(0x4000)
    data[0x200:0x200 + 33] = b'33/1/EDC17_CP09/11/P_574//V8KB///'
    t = np.array([[20 + 11 * r + 5 * c + (r * c) % 3 for c in range(9)] for r in range(7)], np.uint8)
    data[0x1000:0x1000 + t.size] = t.tobytes()
    b = tmp_path / 'probe.bin'; b.write_bytes(bytes(data))
    ref = tmp_path / 'probe.csv'
    ref.write_text('name,offset,rows,cols,dtype,endian,factor,bias,unit,kind,notes\nT,0x1000,7,9,u8,big,1,0,,Unbekannt,\n',
                   encoding='utf-8')
    results = tmp_path / 'val.json'
    assert validate_pair.main([str(b), str(ref), '--family', 'Bosch EDC17CP09', '--complete',
                               '--results', str(results)]) == 0
    out = capsys.readouterr().out
    assert 'EDC17CP09' in out and 'Gemessen: 1 von 1' in out
    rows = json.loads(results.read_text(encoding='utf-8'))['rows']
    assert len(rows) == 1 and rows[0]['family'] == 'Bosch EDC17CP09' and rows[0]['exact_2d'] == 1
    validate_pair.main([str(b), str(ref), '--family', 'Bosch EDC17CP09', '--results', str(results)])
    assert len(json.loads(results.read_text(encoding='utf-8'))['rows']) == 1     # same file: replaced, not doubled
