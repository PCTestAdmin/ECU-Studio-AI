"""Train the candidate scorer on labelled candidates, evaluated family-out, with a replacement gate.

Input: JSON lines {"family", "cls", "y", "x": [features], "role", "complete"}
(tools/build_candidate_dataset.py; label y = candidate starts exactly at a
reference-definition object). Each family is predicted by a model trained on
the other families only (leave-one-family-out); the reported metrics and the
score->hit-rate table come from those held-out predictions. Software versions
of one family therefore never sit on both sides of a split.

- Training rows: roles given by --roles (default "training"), complete
  references only (partial references have unknown negatives). Rows with role
  "test" are NEVER fitted or used to pick anything; they are only reported
  with the final model ("blind").
- The shipped model is scored on the same held-out rows. It was trained on
  other data (some of it overlaps, e.g. MS4x), so this comparison favours it:
  a new model must beat it clearly to replace it.
- The shipped model (recognition/data/candidate_model.json) is only replaced
  with --promote AND when the gate passes: mean held-out AUC higher by
  >= GATE_AUC and precision at 80 % recall not worse than GATE_DROP in any
  family. Otherwise the new model is written next to the data as a candidate.
- Seed, data hash, library versions and all metrics go to the log (--log).

Usage: python -m ecu_studio.tools.train_candidate_model DATA.jsonl [--roles training,development]
       [--seed 0] [--out FILE] [--log FILE] [--promote]
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import numpy as np
from ecu_studio.core.candidate_features import FEATURES
from ecu_studio.core.candidate_model import DATA as MODEL_PATH, DATA_ONLY_CLASSES, score as model_score

GATE_AUC = .01
GATE_DROP = .02


def load(path, roles=('training',), complete_only=True):
    rows = [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if r['cls'] in DATA_ONLY_CLASSES]
    test = [r for r in rows if r.get('role') == 'test']
    rows = [r for r in rows if r.get('role', 'training') in roles and r.get('role') != 'test'
            and (r.get('complete', True) or not complete_only)]

    def arrays(rs):
        return (np.array([r['x'] for r in rs], float).reshape(len(rs), len(FEATURES)),
                np.array([r['y'] for r in rs], int), np.array([r['family'] for r in rs]))
    return arrays(rows), arrays(test)


def precision_at_recall(y, p, recall):
    order = np.argsort(-p); ys = y[order]
    tp = np.cumsum(ys); k = np.searchsorted(tp, recall * ys.sum())
    k = min(max(k, 0), len(ys) - 1)
    return float(tp[k] / (k + 1)), float(p[order][k])


def _metrics(y, p):
    from sklearn.metrics import roc_auc_score
    both = 0 < y.sum() < len(y)
    return {'auc': round(float(roc_auc_score(y, p)), 3) if both else None,
            'precision_at_recall_80': round(precision_at_recall(y, p, .8)[0], 3) if y.sum() else None}


def gate(report: dict) -> tuple[bool, str]:
    """Replace only when the new model is measurably better on the same held-out families."""
    fams = [f for f, r in report.items() if r['new']['auc'] is not None and r['shipped']['auc'] is not None]
    if len(fams) < 2:
        return False, f'zu wenige auswertbare Familien ({len(fams)}) für einen familienübergreifenden Vergleich'
    new = np.mean([report[f]['new']['auc'] for f in fams]); old = np.mean([report[f]['shipped']['auc'] for f in fams])
    worse = [f for f in fams if (report[f]['new']['precision_at_recall_80'] or 0)
             < (report[f]['shipped']['precision_at_recall_80'] or 0) - GATE_DROP]
    if new < old + GATE_AUC:
        return False, f'mittlere AUC {new:.3f} nicht um {GATE_AUC} besser als ausgeliefert {old:.3f}'
    if worse:
        return False, 'Präzision bei 80 % Trefferquote schlechter in: ' + ', '.join(worse)
    return True, f'mittlere AUC {old:.3f} -> {new:.3f}, keine Familie schlechter'


def main(argv=None):
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('data', type=Path)
    parser.add_argument('--roles', default='training')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--promote', action='store_true', help='ausgeliefertes Modell ersetzen, wenn das Gate besteht')
    args = parser.parse_args(argv)
    roles = tuple(r.strip() for r in args.roles.split(',') if r.strip())
    if 'test' in roles:
        parser.error('Rolle "test" wird nie zum Trainieren verwendet')
    (X, y, fam), (Xt, yt, famt) = load(args.data, roles)
    if not len(y) or y.sum() < 10:
        parser.error(f'zu wenige Trainingsdaten ({len(y)} Zeilen, {int(y.sum())} Treffer)')
    try:
        shipped = json.loads(MODEL_PATH.read_text(encoding='utf-8'))
        shipped = shipped if shipped.get('features') == list(FEATURES) else None
    except (OSError, ValueError):
        shipped = None
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    held = {'lr': np.full(len(y), np.nan), 'gb': np.full(len(y), np.nan)}
    report = {}
    for f in sorted(set(fam)):
        tr, te = fam != f, fam == f
        if y[tr].sum() < 10 or te.sum() < 10:
            print(f'{f}: übersprungen (zu wenige Daten außerhalb/innerhalb der Familie)')
            continue
        m_tr, s_tr = X[tr].mean(0), X[tr].std(0) + 1e-9          # scaling from the training folds only
        lr = LogisticRegression(max_iter=2000, C=1.0, class_weight='balanced').fit((X[tr] - m_tr) / s_tr, y[tr])
        gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=.05, class_weight='balanced',
                                            random_state=args.seed).fit(X[tr], y[tr])
        held['lr'][te] = lr.predict_proba((X[te] - m_tr) / s_tr)[:, 1]
        held['gb'][te] = gb.predict_proba(X[te])[:, 1]
        row = {'n': int(te.sum()), 'positives': int(y[te].sum()), 'base_rate': round(float(y[te].mean()), 3),
               'new': _metrics(y[te], held['lr'][te]), 'gb': _metrics(y[te], held['gb'][te])}
        row['shipped'] = (_metrics(y[te], np.array([model_score(x, shipped) for x in X[te]]))
                          if shipped else {'auc': None, 'precision_at_recall_80': None})
        report[f] = row
        print(f"{f:22s} n={row['n']:5d} Basisrate {row['base_rate']:.0%} | neu {row['new']} | "
              f"ausgeliefert {row['shipped']} | GB {row['gb']}")
    ok = ~np.isnan(held['lr'])
    table = []
    if ok.sum():
        p, yy = held['lr'][ok], y[ok]
        edges = np.quantile(p, np.linspace(0, 1, 11))
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (p >= lo) & (p <= hi)
            if sel.sum():
                table.append([round(float(lo), 4), round(float(hi), 4), round(float(yy[sel].mean()), 4), int(sel.sum())])
    final = LogisticRegression(max_iter=2000, C=1.0, class_weight='balanced').fit(Z, y)
    passed, reason = gate(report)
    data_sha = hashlib.sha256(args.data.read_bytes()).hexdigest()
    model = {'format': 1, 'trained_on': datetime.date.today().isoformat(), 'features': list(FEATURES),
             'mean': mu.round(6).tolist(), 'std': sd.round(6).tolist(),
             'coef': final.coef_[0].round(6).tolist(), 'intercept': round(float(final.intercept_[0]), 6),
             'heldout_rate_table': table, 'families': report, 'samples': int(len(y)), 'positives': int(y.sum()),
             'roles': list(roles), 'seed': args.seed, 'data_sha256': data_sha, 'firmware_bytes_included': False,
             'note': 'Family-out evaluation; rates are held-out hit rates of data-only candidates, not guarantees.'}
    if shipped and 'drop_below' in shipped:
        model['drop_below_note'] = 'drop_below des ausgelieferten Modells nicht übernommen: neu bestimmen.'
    blind = {}
    if len(yt):
        pt = np.array([model_score(x, model) for x in Xt])
        for f in sorted(set(famt)):
            sel = famt == f
            blind[f] = {'n': int(sel.sum()), 'positives': int(yt[sel].sum()), 'new': _metrics(yt[sel], pt[sel]),
                        'shipped': _metrics(yt[sel], np.array([model_score(x, shipped) for x in Xt[sel]]))
                        if shipped else None}
    promoted = bool(args.promote and passed)
    out = MODEL_PATH if promoted else (args.out or args.data.with_suffix('.model.json'))
    out.write_text(json.dumps(model, indent=1), encoding='utf-8')
    log = {'created': datetime.datetime.now().isoformat(timespec='seconds'), 'data': str(args.data),
           'data_sha256': data_sha, 'seed': args.seed, 'roles': list(roles),
           'versions': {'numpy': np.__version__, 'sklearn': sklearn.__version__},
           'train_rows': int(len(y)), 'train_positives': int(y.sum()), 'families_out': report,
           'blind_test': blind, 'gate_passed': passed, 'gate_reason': reason, 'promoted': promoted, 'model': str(out)}
    if args.log:
        args.log.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding='utf-8')
    if ok.sum() and 0 < y[ok].sum() < ok.sum():
        print('Gesamt: LR held-out AUC', round(float(roc_auc_score(y[ok], held['lr'][ok])), 3))
    print('Gate:', 'bestanden' if passed else 'nicht bestanden', '–', reason)
    print('Modell:', out, '(ausgeliefertes Modell ersetzt)' if promoted else '(Kandidat, ausgeliefertes Modell unverändert)')


if __name__ == '__main__':
    main()
