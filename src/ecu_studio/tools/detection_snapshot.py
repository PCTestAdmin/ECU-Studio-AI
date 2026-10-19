"""Portable detector-output snapshot; can run against the archived v1.10 source."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.scoped_scan import scan_calibration_candidates


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    cases=[]
    for file in ('demo_synthetic.bin','demo_multi_map.bin','holdout_synthetic_tcu.bin','xdf_stride_demo.bin'):
        data=(root/'examples'/file).read_bytes()
        cases.append((file,data))
    cases.append(('random_seed_42',np.random.default_rng(42).bytes(131072)))
    results=[]
    for name,data in cases:
        maps=scan_calibration_candidates(BinaryImage(data))
        results.append({'case':name,'data_kind':'synthetic','sha256':hashlib.sha256(data).hexdigest(),
                        'maps':[{'offset':m.offset,'rows':m.rows,'cols':m.cols,'dtype':m.dtype,
                                 'endian':m.endian,'confidence':m.confidence,'kind':m.kind,'verified':m.verified} for m in maps]})
    Path(args.out).write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
