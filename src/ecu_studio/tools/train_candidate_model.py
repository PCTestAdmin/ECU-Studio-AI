"""Train the candidate scorer on labelled candidates, evaluated family-out.

Input: JSON lines {"family", "cls", "y", "x": [features]} (one per candidate,
label y = candidate starts exactly at a reference-definition object).
Each family is predicted by a model trained on the other families only; the
reported metrics and the score->hit-rate table come from those held-out
predictions. The shipped model is logistic regression (portable JSON, no
pickle) trained on all families; gradient boosting is reported for comparison.

Usage: python -m ecu_studio.tools.train_candidate_model DATA.jsonl [--out FILE]
"""
from __future__ import annotations
import argparse
import datetime
import json
from pathlib import Path
import numpy as np
from ecu_studio.core.candidate_features import FEATURES
from ecu_studio.core.candidate_model import DATA as MODEL_PATH, DATA_ONLY_CLASSES


def load(path):
    rows = [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if r['cls'] in DATA_ONLY_CLASSES]
    X = np.array([r['x'] for r in rows], float)
    y = np.array([r['y'] for r in rows], int)
    fam = np.array([r['family'] for r in rows])
    return X, y, fam


def precision_at_recall(y, p, recall):
    order = np.argsort(-p); ys = y[order]
    tp = np.cumsum(ys); k = np.searchsorted(tp, recall * ys.sum())
    k = min(max(k, 0), len(ys) - 1)
    return float(tp[k] / (k + 1)), float(p[order][k])


def main(argv=None):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data'); parser.add_argument('--out', type=Path, default=MODEL_PATH)
    args = parser.parse_args(argv)
    X, y, fam = load(args.data)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    held = {'lr': np.zeros(len(y)), 'gb': np.zeros(len(y))}
    report = {}
    for f in sorted(set(fam)):
        tr, te = fam != f, fam == f
        if y[tr].sum() < 10 or te.sum() < 10:
            continue
        lr = LogisticRegression(max_iter=2000, C=1.0, class_weight='balanced').fit(Z[tr], y[tr])
        gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=.05, class_weight='balanced').fit(X[tr], y[tr])
        held['lr'][te] = lr.predict_proba(Z[te])[:, 1]
        held['gb'][te] = gb.predict_proba(X[te])[:, 1]
        row = {'n': int(te.sum()), 'positives': int(y[te].sum()), 'base_rate': round(float(y[te].mean()), 3)}
        for k in ('lr', 'gb'):
            p = held[k][te]
            row[k] = {'auc': round(float(roc_auc_score(y[te], p)), 3) if 0 < y[te].sum() < te.sum() else None,
                      'precision_at_recall_80': round(precision_at_recall(y[te], p, .8)[0], 3)}
        report[f] = row
        print(f"{f:8s} n={row['n']:5d} Basisrate {row['base_rate']:.0%} | LR AUC {row['lr']['auc']} P@R80 {row['lr']['precision_at_recall_80']:.0%}"
              f" | GB AUC {row['gb']['auc']} P@R80 {row['gb']['precision_at_recall_80']:.0%}")
    # Held-out score -> hit-rate table (deciles of LR scores), used as calibrated rate.
    p = held['lr']
    edges = np.quantile(p, np.linspace(0, 1, 11))
    table = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (p >= lo) & (p <= hi)
        if sel.sum():
            table.append([round(float(lo), 4), round(float(hi), 4), round(float(y[sel].mean()), 4), int(sel.sum())])
    final = LogisticRegression(max_iter=2000, C=1.0, class_weight='balanced').fit(Z, y)
    model = {'format': 1, 'trained_on': datetime.date.today().isoformat(), 'features': list(FEATURES),
             'mean': mu.round(6).tolist(), 'std': sd.round(6).tolist(),
             'coef': final.coef_[0].round(6).tolist(), 'intercept': round(float(final.intercept_[0]), 6),
             'heldout_rate_table': table, 'families': report,
             'samples': int(len(y)), 'positives': int(y.sum()),
             'note': 'Family-out evaluation; rates are held-out hit rates of data-only candidates, not guarantees.'}
    args.out.write_text(json.dumps(model, indent=1), encoding='utf-8')
    print('Gesamt: LR held-out AUC', round(float(roc_auc_score(y, held['lr'])), 3),
          '| GB held-out AUC', round(float(roc_auc_score(y, held['gb'])), 3), '| Modell:', args.out)


if __name__ == '__main__':
    main()
