"""Learned scorer for data-only candidates (portable JSON logistic regression).

Applies only to candidates whose evidence is value smoothness (row pitch or
legacy grid); code- and axis-backed candidates keep their measured class rates.
The calibrated rate is the held-out (family-out) hit rate of the candidate's
score bin, see tools/train_candidate_model.py.
"""
from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from .model import BinaryImage, MapDefinition
from .candidate_features import candidate_features, FEATURES

DATA = Path(__file__).resolve().parents[1] / 'recognition' / 'data' / 'candidate_model.json'
DATA_ONLY_CLASSES = ('pitch', 'raster')


@lru_cache(maxsize=1)
def load_model() -> dict | None:
    try:
        model = json.loads(DATA.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return model if model.get('features') == list(FEATURES) else None


def score(features: list[float], model: dict) -> float:
    z = (np.asarray(features) - np.asarray(model['mean'])) / np.asarray(model['std'])
    t = float(np.dot(z, model['coef']) + model['intercept'])
    return 1. / (1. + math.exp(-max(-40., min(40., t))))


def heldout_rate(p: float, model: dict) -> float:
    for lo, hi, rate, _ in model['heldout_rate_table']:
        if lo <= p <= hi:
            return rate
    table = model['heldout_rate_table']
    return table[0][2] if p < table[0][0] else table[-1][2]


def score_candidates(image: BinaryImage, maps: list[MapDefinition], data_mask=None) -> dict[int, tuple[float, float]]:
    """{index: (model score, held-out hit rate)} for data-only candidates."""
    from .confidence import evidence_class
    model = load_model()
    if model is None:
        return {}
    out = {}
    for i, m in enumerate(maps):
        if m.source != 'heuristic' or evidence_class(m) not in DATA_ONLY_CLASSES:
            continue
        f = candidate_features(image, m, data_mask)
        if f is not None:
            p = score(f, model)
            out[i] = (p, heldout_rate(p, model))
    return out
