"""Active-learning human review queue: no auto-labeling and no ECU edits."""
from __future__ import annotations
import json
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.profiles import identify_profile
from ecu_studio.core.scoped_scan import scan_calibration_candidates
from .structure_model import ShapeModel
from .catalog import DefinitionCatalog


def review_queue(image:BinaryImage,db:DefinitionCatalog,model:ShapeModel,*,limit:int=40)->dict:
    profile=identify_profile(image)
    family=profile.family
    software=profile.software_version or profile.calibration_id or ''
    if family!=model.family or software!=model.software:
        return {'status':'abstain','queue':[],'reason':'Falscher ECU-Familien-/Firmware-Stand'}
    known=db.firmware_maps(image)
    candidates=scan_calibration_candidates(image)
    queue=[]
    for m in candidates[:500]:
        if not 3<=m.rows<=128 or not 3<=m.cols<=128 or m.rows*m.cols>4096:continue
        if any((m.offset < other.offset+other.length and other.offset < m.offset+m.length)
               for other in known):continue
        try:
            raw=[[image.raw_value(m,y,x) for x in range(m.cols)] for y in range(m.rows)]
            pred=model.similar(raw,family=family,software=software,max_matches=2)
            distance=float(pred.get('distance',10**5))
            # Close to threshold is where human labels are most informative.
            closeness=abs(distance-model.novelty_threshold)
            queue.append({'offset':m.offset,'rows':m.rows,'cols':m.cols,
                'kind':'Unbekannt','verified':False,
                'review_priority':round(closeness,4),
                'nearest_reference':pred.get('candidates',[{}])[0].get('source_name'),
                'structure_distance':round(distance,4),
                'reason':'Manuell mit exakter A2L/XDF und korrekten Achsen/Skalierungen prüfen'})
        except (ValueError,KeyError,IndexError):continue
    queue.sort(key=lambda x:(x['review_priority'],x['offset']))
    dedup=[]
    for item in queue:
        if not any(abs(item['offset']-other['offset'])<64 for other in dedup):
            dedup.append(item)
        if len(dedup)>=limit:break
    return {'status':'review_only','family':family,'software':software,
            'queue':dedup,'eligible_for_training':0,
            'review_process':'Nur nach unabhängiger Verifikation in den Trainingskatalog übernehmen; sonst unbekannt oder ablehnen.'}
