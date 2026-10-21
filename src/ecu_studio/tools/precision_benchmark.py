"""Reproducible *synthetic* structural scan regression, NOT ECU accuracy validation.

Run: python -m ecu_studio.tools.precision_benchmark --out PRECISION_BENCHMARK.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from ecu_studio.core.model import BinaryImage
from ecu_studio.core.detection import discover_maps
from ecu_studio.core.detection_extended import scan_u8
from ecu_studio.core.detection_32 import scan_32
from ecu_studio.core.detection_signed import scan_s16
from ecu_studio.core.precision import rank_candidates


def candidates(image):
    return (discover_maps(image,max_results=70)+
            scan_u8(image,max_results=40)+
            scan_32(image,max_results=30)+
            scan_s16(image,max_results=25))


def run() -> dict:
    fixtures=Path(__file__).resolve().parents[3]/'examples'/'demo'
    tests=[]
    for label, payload, anchors in (
        ('synthetic_two_maps',(fixtures/'demo_synthetic.bin').read_bytes(),[0x1000,0x2000]),
        ('synthetic_multi_map',(fixtures/'demo_multi_map.bin').read_bytes(),[0x1000,0x1500,0x2000,0x3800,0x5000,0x5800,0x6800]),
        ('deterministic_random_bytes',np.random.default_rng(35).integers(0,256,32768,dtype=np.uint8).tobytes(),[]),
    ):
        im=BinaryImage(payload)
        initial=candidates(im)
        filtered=rank_candidates(im,initial)
        present={m.offset for m in filtered}
        tests.append({'test':label,'preliminary_candidates':len(initial),
                      'filtered_candidates':len(filtered),'predefined_positive_offsets':len(anchors),
                      'detected_predefined_offsets':sum(x in present for x in anchors),
                      'all_unverified':all(not m.verified and m.kind=='Unbekannt' for m in filtered)})
    return {'benchmark_type':'Synthetic/demo regression only – NO real ECU semantic accuracy',
            'cases':tests,
            'firmware_holdout_accuracy':None,
            'ecus_automatically_identified_from_new_brands':0,
            'warning':'Nicht mit realer Kennfeld-Erkennungsquote oder Funktionsgenauigkeit verwechseln.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out')
    a=p.parse_args();r=run();s=json.dumps(r,ensure_ascii=False,indent=2)
    if a.out:Path(a.out).write_text(s+'\n',encoding='utf8')
    print(s)

if __name__=='__main__':main()
