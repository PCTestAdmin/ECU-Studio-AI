"""Flash preflight: deterministic checks on the pending changes before export.

Each finding names the address and the reason. The traffic light summarises
them: red = very likely a mistake, yellow = check before flashing, green = no
finding. Green is NOT a flash, emission or roadworthiness approval.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from .model import BinaryImage, MapDefinition
from .axis_arrays import scan_count_axes
from .data_regions import data_mask
from .checksum_audit import verify_checksums

LEVELS = ('grün', 'gelb', 'rot')
MIN_TWIN_BYTES = 16
JUMP_FACTOR, JUMP_FLOOR = 2.0, .35


@dataclass
class Finding:
    level: str          # 'gelb' or 'rot'
    code: str
    title: str
    detail: str
    offset: int | None = None


@dataclass
class PreflightReport:
    findings: list[Finding] = field(default_factory=list)
    changed_bytes: int = 0
    checksum_verified: bool = False

    @property
    def status(self) -> str:
        return max((f.level for f in self.findings), key=LEVELS.index, default='grün')

    @property
    def checks_passed(self) -> bool:
        """Green AND every *declared* checksum slot verified.

        This is NOT a flash approval: a profile may declare only some of the
        checksums, signatures or monitoring blocks an ECU actually checks, and
        the preflight covers a fixed list of plausibility tests only.
        """
        return self.status == 'grün' and self.checksum_verified

    def add(self, *args, **kwargs):
        self.findings.append(Finding(*args, **kwargs))

    def text(self) -> str:
        lines = [f'FLASH-PREFLIGHT: {self.status.upper()}', '']
        for f in sorted(self.findings, key=lambda f: -LEVELS.index(f.level)):
            where = f' @ 0x{f.offset:08X}' if f.offset is not None else ''
            lines.append(f'[{f.level.upper()}] {f.title}{where}\n      {f.detail}')
        if not self.findings:
            lines.append('Keine Befunde in den geprüften Punkten.')
        lines.append('')
        lines.append(f'Geprüft: {self.changed_bytes} geänderte Byte, jede Position einzeln.')
        lines.append('Checksummen: ' + ('alle im Profil deklarierten Prüffelder stimmen (das Profil kann '
                                         'unvollständig sein; weitere ECU-Prüfungen bleiben ungeprüft).'
                                         if self.checksum_verified
                                         else 'NICHT verifiziert – Datei ist nicht flashbereit.'))
        lines += ['Grün bedeutet nur: keiner der geprüften Fehler gefunden. Auch mit verifizierten '
                  'Prüffeldern ist das KEINE Flash-, Abgas- oder Straßenfreigabe.']
        return '\n'.join(lines)


def _changed_positions(original: bytes, modified: bytes) -> np.ndarray:
    """Every byte position that differs, from the bytes themselves (not the edit log)."""
    if len(original) != len(modified):
        raise ValueError('Original und geänderte Datei sind unterschiedlich groß')
    a, b = np.frombuffer(original, np.uint8), np.frombuffer(modified, np.uint8)
    return np.flatnonzero(a != b)


def _runs(pos: np.ndarray) -> list[tuple[int, int]]:
    if not len(pos):
        return []
    breaks = np.flatnonzero(np.diff(pos) != 1)
    starts = np.r_[pos[0], pos[breaks + 1]]
    ends = np.r_[pos[breaks], pos[-1]] + 1
    return list(zip(starts.tolist(), ends.tolist()))


def _covered(pos: np.ndarray, intervals) -> np.ndarray:
    """Per position: inside any of the [start, end) intervals (overlaps allowed)."""
    marks = np.zeros(len(pos) + 1, np.int64)
    for s, e in intervals:
        marks[np.searchsorted(pos, s)] += 1
        marks[np.searchsorted(pos, e)] -= 1
    return np.cumsum(marks)[:-1] > 0


def _report_runs(report, level, code, title, detail, pos, limit=10):
    """One finding per run (first `limit`), plus a total so nothing is hidden."""
    runs = _runs(pos)
    for s, e in runs[:limit]:
        report.add(level, code, title, f'{e - s} Byte; {detail}', s)
    if len(runs) > limit:
        report.add(level, code, f'{title}: insgesamt {len(pos)} Byte in {len(runs)} Bereichen',
                   f'Weitere {len(runs) - limit} Bereiche nicht einzeln aufgeführt.', runs[limit][0])


def _overlaps(m: MapDefinition, s: int, e: int) -> bool:
    return m.offset < e and s < m.offset + m.length


def run_preflight(image: BinaryImage, maps: list[MapDefinition], *, checksum_profile=None,
                  cal_window: tuple[int, int] | None = None) -> PreflightReport:
    report = PreflightReport()
    original = image.original
    modified = image.materialize()
    pos = _changed_positions(original, modified)
    runs = _runs(pos)
    report.changed_bytes = len(pos)

    # 1. Checksums (also for an unchanged file: a broken read must not look fine)
    status = verify_checksums(image, checksum_profile)
    report.checksum_verified = status['status'] == 'match'
    if status['status'] == 'mismatch':
        report.add('rot', 'checksum', 'Checksumme stimmt nicht', status['message'])
    elif status['status'] != 'match' and runs:
        report.add('gelb', 'checksum', 'Checksumme unbekannt',
                   'Kein Checksummenprofil geladen; vor dem Flashen mit geeignetem Werkzeug korrigieren.')
    if not runs:
        return report

    # 2. Changes in program code, decided per byte: a run that touches a map or
    # a data block must not hide its other bytes.
    in_map = _covered(pos, [(m.offset, m.offset + m.length) for m in maps])
    if cal_window and cal_window[0] is not None:
        outside = (pos < cal_window[0]) | (pos >= cal_window[1])
        _report_runs(report, 'rot', 'code', 'Änderung außerhalb des Kalibrierbereichs',
                     'dort liegt bei diesem Steuergerät Programmcode.', pos[outside])
    else:
        mask = data_mask(original)
        in_data = mask[pos]
        _report_runs(report, 'rot', 'code', 'Änderung im vermuteten Programmcode',
                     'in einem Block ohne Datenstruktur und ohne Kennfeld.', pos[~in_data & ~in_map])
        # Unconfirmed automatic candidates do not prove that code bytes are data.
        guessed = [m.source == 'heuristic' and not m.verified for m in maps]
        by_guess = _covered(pos, [(m.offset, m.offset + m.length) for m, g in zip(maps, guessed) if g])
        by_def = _covered(pos, [(m.offset, m.offset + m.length) for m, g in zip(maps, guessed) if not g])
        _report_runs(report, 'gelb', 'code-candidate', 'Änderung in ungeprüftem Kandidaten im vermuteten Code',
                     'nur ein automatischer Kandidat deckt diese Bytes ab; der Block sieht nach Programmcode aus.',
                     pos[~in_data & by_guess & ~by_def])

    # 3. Twins: unchanged copies of a modified map
    changed_maps = [m for m in maps if any(_overlaps(m, s, e) for s, e in runs)]
    for m in changed_maps:
        block = original[m.offset:m.offset + m.length]
        if len(block) < MIN_TWIN_BYTES or len(set(block)) < 4:
            continue
        hit = original.find(block)
        while hit != -1:
            k = int(np.searchsorted(pos, hit))
            if hit != m.offset and not (k < len(pos) and pos[k] < hit + len(block)):
                report.add('rot', 'twin', f'Zwilling von „{m.name}“ nicht angepasst',
                           f'Identische Kopie bei 0x{hit:08X} ist unverändert; Überwachungs- oder '
                           'Variantenkopien führen sonst oft zu Notlauf/Fehlerspeicher.', hit)
            hit = original.find(block, hit + 1)
    # near-identical twins among known maps of the same shape
    for m in changed_maps:
        a0 = np.frombuffer(original[m.offset:m.offset + m.length], dtype=np.uint8)
        for o in maps:
            if o is m or o.offset == m.offset or (o.rows, o.cols, o.dtype) != (m.rows, m.cols, m.dtype):
                continue
            if any(_overlaps(o, s, e) for s, e in runs):
                continue
            b0 = np.frombuffer(original[o.offset:o.offset + o.length], dtype=np.uint8)
            if len(b0) != len(a0) or bytes(b0) == bytes(a0):
                continue   # exact copies are reported above
            if np.std(a0) > 0 and np.std(b0) > 0 and np.corrcoef(a0.astype(float), b0.astype(float))[0, 1] > .995:
                report.add('gelb', 'twin-similar', f'Sehr ähnliches Kennfeld zu „{m.name}“ unverändert',
                           f'„{o.name}“ bei 0x{o.offset:08X} hat fast denselben Inhalt (Korrelation > 0,995).', o.offset)

    # 4. Axes that lost their ordering
    for ax in scan_count_axes(original):
        if not any(s < ax.end and ax.header < e for s, e in runs):
            continue
        w = ax.width
        raw = modified[ax.offset:ax.offset + ax.count * w]
        kind = 'i' if min(ax.values) < 0 else 'u'
        v = np.frombuffer(raw, np.dtype(kind + '1') if w == 1 else np.dtype('<' + kind + '2')).astype(np.int64)
        count = modified[ax.header] if w == 1 else modified[ax.header] | modified[ax.header + 1] << 8
        if count != ax.count or np.any(np.diff(v) <= 0):
            report.add('rot', 'axis', 'Achse nicht mehr aufsteigend',
                       f'Stützstellen-Array mit {ax.count} Punkten wurde so geändert, dass Anzahl oder '
                       'Reihenfolge nicht mehr stimmt; die Interpolation im Steuergerät wird ungültig.', ax.header)

    # 5. Jumps much larger than anywhere in the original surface
    for m in changed_maps:
        if min(m.rows, m.cols) < 2:
            continue
        try:
            new = image.matrix(m).astype(float)
            old_def = MapDefinition(**m.asdict())
            old = BinaryImage(original).matrix(old_def).astype(float)
        except (ValueError, IndexError):
            continue
        span = float(old.max() - old.min()) or 1.
        def worst(x):
            return max(np.abs(np.diff(x, axis=1)).max(initial=0), np.abs(np.diff(x, axis=0)).max(initial=0))
        before, after = worst(old), worst(new)
        if after > max(JUMP_FACTOR * before, before + JUMP_FLOOR * span):
            report.add('gelb', 'jump', f'Ungewöhnlicher Sprung in „{m.name}“',
                       f'Größter Nachbarsprung {after:g} statt bisher {before:g} (Rohwerte); Tippfehler prüfen.', m.offset)

    # 6. Changes that belong to no known map
    loose = pos[~in_map]
    if len(loose):
        report.add('gelb', 'unmapped', f'{len(loose)} geänderte Byte außerhalb bekannter Kennfelder',
                   'Änderungen ohne Definition lassen sich nicht auf Plausibilität prüfen.', int(loose[0]))
    return report
