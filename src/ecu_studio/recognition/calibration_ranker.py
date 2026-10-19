"""Portable structural ranking learned from attributed open-ECU presets.

No functional labels, OEM binaries, or user BINs enter this model. It ranks
geometry, and never confirms a map, an ECU family, or a tuning action.
"""
from functools import lru_cache
from pathlib import Path
from .structure_rejector import StructureRejector


@lru_cache(maxsize=1)
def installed_ranker():
    path=Path(__file__).parent/'data'/'calibration_ranker_v113.json'
    try:
        model=StructureRejector.load(path)
        return model if model.metrics.get('ranking_release_gate') else None
    except (OSError,ValueError,TypeError,KeyError):
        return None


def training_status():
    path=Path(__file__).parent/'data'/'calibration_ranker_v113.json'
    if not path.exists():return {'status':'not-trained'}
    model=StructureRejector.load(path)
    return {**model.metrics,'training_hash':model.training_hash,'threshold':model.threshold}
