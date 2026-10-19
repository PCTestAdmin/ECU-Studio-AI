"""Local, read-only detection audit. Reports no VIN, filename or firmware bytes."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from time import perf_counter
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from ecu_studio.core.profiles import identify_profile


def audit(path, output, baseline=None):
    image=BinaryImage.from_file(path)
    begin=perf_counter()
    maps=scan_calibration_candidates(image)
    elapsed=perf_counter()-begin
    report={'format':1,'version':'1.14.0','size':image.size,'sha256':image.digest,
            'profile':identify_profile(image).asdict(),'elapsed_seconds':round(elapsed,3),
            'maps':len(maps),'sources':dict(Counter(m.source for m in maps)),
            'dimensions':dict(Counter('2D' if min(m.rows,m.cols)>1 else 'curve' for m in maps)),
            'datatypes':dict(Counter(m.dtype for m in maps)),
            'verified':sum(m.verified for m in maps),
            'method':'Community-definition agreement and structural checks; NOT measured ECU ground-truth precision.'}
    report['spot_checks']=[]
    for name in ('ip_cur_igc_sp__n__maf','ip_dly_adc_ivvt_ex__n__toil','ip_ti_tco_2_pl_ivvt_1__n__maf'):
        m=next((m for m in maps if m.name==name),None)
        if m:
            raw=image.matrix(m)
            report['spot_checks'].append({'name':m.name,'offset':hex(m.offset),'rows':m.rows,'cols':m.cols,
                'dtype':m.dtype,'endian':m.endian,'factor':m.factor,'bias':m.bias,'unit':m.unit,
                'raw_min':int(raw.min()),'raw_max':int(raw.max()),
                'first_physical':image.physical_value(m,0,0),
                'axis_x_unit':m.axis_x_unit,'axis_y_unit':m.axis_y_unit,
                'axis_x':m.axes_x,'axis_y':m.axes_y})
    if baseline:
        before=json.loads(Path(baseline).read_text(encoding='utf-8'))
        if before['sha256']!=image.digest:raise ValueError('Baseline belongs to a different binary')
        keys={(m.offset,m.rows,m.cols,m.dtype,m.endian if m.width>1 else '') for m in maps}
        agrees=sum((m['offset'],m['rows'],m['cols'],m['dtype'],m['endian'] if m['dtype'] not in ('u8','s8') else '') in keys for m in before['maps'])
        report['baseline_comparison']={'old_proposals':len(before['maps']),
            'old_layouts_matching_new_source_proposals':agrees,
            'old_u32_proposals':sum(m['dtype']=='u32' for m in before['maps']),
            'notice':'Agreement with a source definition is not independent correctness evidence.'}
    report['original_unchanged']=(not image.dirty_bytes and image.digest==hashlib.sha256(Path(path).read_bytes()).hexdigest())
    if not report['original_unchanged']:raise RuntimeError('Original changed during audit')
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin');parser.add_argument('--output',required=True);parser.add_argument('--baseline')
    args=parser.parse_args()
    report=audit(args.bin,args.output,args.baseline)
    print(json.dumps({k:report[k] for k in ('maps','elapsed_seconds','verified','original_unchanged')}))


if __name__=='__main__':main()
