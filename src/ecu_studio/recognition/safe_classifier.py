"""Conservative supervised training, per ECU family, with strict quality gates.

All training samples must come from independently checked catalog records.
Never silently train on imported XDF metadata or guesses. A model only becomes
usable after multiple held-out firmware versions meet accuracy thresholds.
"""
from __future__ import annotations
from dataclasses import dataclass
from .catalog import DefinitionCatalog
from .ml import train, Model
from .families import require_family

class _FamilyView:
    def __init__(self,db:DefinitionCatalog,family:str):
        self.db=db;self.family=family
    def records(self):
        provenance=self.db.training_provenance()
        # ORI/MOD versions in one reviewed lineage form ONE held-out group.
        return [{**r,'firmware_sha':provenance[r['firmware_sha']]['independence_group']}
                for r in self.db.records() if r['family']==self.family and r['firmware_sha'] in provenance]

def train_safe(db:DefinitionCatalog,family:str,*,min_firmwares=4,minimum_per_class=12,
               minimum_macro_recall=.85,minimum_class_recall=.75)->Model:
    require_family(family)
    allrecs=[r for r in db.records() if r['family']==family and r['verified'] and r['sample_json']]
    provenance=db.training_provenance()
    if any(r['firmware_sha'] not in provenance for r in allrecs):
        raise ValueError('Geprüfte Nutzungsrechte und unabhängige ORI/MOD-Firmwaregruppen fehlen. Trainingsherkunft zuerst importieren.')
    firms={r['firmware_sha'] for r in allrecs}
    if len(firms)<min_firmwares:
        raise ValueError(f'{family}: mindestens {min_firmwares} voneinander unabhängige, überprüfte Firmwarestände erforderlich; bisher {len(firms)}.')
    model=train(_FamilyView(db,family),min_per_label=minimum_per_class,
                min_firmwares_per_label=min_firmwares)
    recall=model.metrics['recall_per_label']
    precision=model.metrics['precision_per_label']
    holdout=model.metrics['heldout_counts_per_label']
    if any(int(n)<3 for n in holdout.values()):
        raise ValueError('Zu wenig Testbeispiele pro Klasse im komplett getrennten Firmware-Holdout')
    crossval=model.metrics['leave_one_firmware_out']
    if (model.metrics['heldout_macro_recall']<minimum_macro_recall
            or crossval['macro_recall']<minimum_macro_recall
            or any(float(v)<minimum_class_recall for v in recall.values())
            or any(float(v)<minimum_class_recall for v in precision.values())
            or any(float(v)<minimum_class_recall for v in crossval['recall_per_label'].values())
            or any(float(v)<minimum_class_recall for v in crossval['precision_per_label'].values())):
        raise ValueError('Single-Holdout/Leave-One-Firmware-Out-Ziel nicht erreicht: '
                         'Modell wird NICHT freigegeben. '+str(crossval['recall_per_label']))
    model.metrics['family']=family
    model.metrics['training_provenance']=[provenance[sha] for sha in sorted(firms)]
    model.metrics['model_version']='1.11-reviewed-lineage'
    model.metrics['release_gate']='Mehrere Firmwarestände / per-class Recall / Leave-One-Firmware-Out; Typen dennoch ungeprüfte Vorschläge'
    model.metrics['threshold_min_macro']=minimum_macro_recall
    model.metrics['threshold_min_class']=minimum_class_recall
    return model
