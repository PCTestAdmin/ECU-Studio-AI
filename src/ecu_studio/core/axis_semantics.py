"""Axis semantics: ranked hypotheses for quantity and scaling of a raw breakpoint array.

Common engine-ECU normalisations are tried; a hypothesis scores when the
scaled breakpoints land in the quantity's usual operating range with a typical
span and spacing. Raw values alone are ambiguous (a byte axis 20..200 can be a
temperature, a speed or a percentage), so results are ranked *suggestions*
with their measured hit rate, never applied as units automatically.
"""
from __future__ import annotations
from dataclasses import dataclass

# (quantity, unit, storage width, factor, offset, typical min, typical max, minimum useful span)
HYPOTHESES = (
    ('Drehzahl', 'rpm', 1, 32.0, 0.0, 300, 8000, 1000),
    ('Drehzahl', 'rpm', 2, 1.0, 0.0, 300, 8500, 1000),
    ('Drehzahl', 'rpm', 2, 0.25, 0.0, 300, 8500, 1000),
    ('Temperatur', '°C', 1, 0.75, -48.0, -45, 145, 30),
    ('Temperatur', '°C', 1, 1.0, -40.0, -40, 150, 30),
    ('Temperatur', '°C', 1, 1.0, -128.0, -40, 127, 20),
    ('Temperatur', '°C', 2, 0.1, -273.15, -40, 1100, 30),
    ('Last / Luftmasse', 'mg/Hub', 1, 5.447, 0.0, 50, 1400, 200),
    ('Last / Luftmasse', 'mg/Hub', 2, 0.0212, 0.0, 50, 1400, 200),
    ('Luftmasse', 'kg/h', 2, 0.25, 0.0, 5, 1200, 50),
    ('Relativ / Pedal', '%', 1, 0.390625, 0.0, 0, 100, 15),
    ('Relativ / Last', '%', 2, 0.0234375, 0.0, 0, 200, 15),
    ('Spannung', 'V', 1, 0.102, 0.0, 6, 17, 2),
    ('Geschwindigkeit', 'km/h', 1, 1.0, 0.0, 0, 260, 30),
    ('Zündwinkel', '°KW', 1, 0.375, 0.0, 0, 60, 5),
    ('Druck', 'hPa', 2, 0.0829, 0.0, 300, 3000, 100),
)


# Engineers pick round breakpoints: step and tolerance per unit for "roundness".
ROUND = {'rpm': (50, 8), '°C': (5, .4), 'mg/Hub': (25, 3), 'kg/h': (10, 1), '%': (5, .5),
         'V': (.5, .06), 'km/h': (5, .5), '°KW': (1, .2), 'hPa': (50, 5)}


def roundness(physical, unit: str) -> float:
    step, tol = ROUND[unit]
    return sum(abs(p - round(p / step) * step) <= tol for p in physical) / len(physical)


@dataclass(frozen=True)
class AxisGuess:
    quantity: str
    unit: str
    factor: float
    offset: float
    score: float

    def describe(self) -> str:
        sign = '+' if self.offset >= 0 else '−'
        formula = f'{self.factor:g}·X' + (f' {sign} {abs(self.offset):g}' if self.offset else '')
        return f'{self.quantity} ({self.unit}, {formula})'


def guess_axis(values, width: int, top: int = 3) -> list[AxisGuess]:
    """Ranked quantity/scaling hypotheses for raw increasing breakpoints."""
    if len(values) < 2:
        return []
    raw_lo, raw_hi = min(values), max(values)
    guesses = []
    for quantity, unit, w, factor, offset, lo, hi, span in HYPOTHESES:
        if w != width:
            continue
        p_lo, p_hi = raw_lo * factor + offset, raw_hi * factor + offset
        if p_lo < lo - .1 * (hi - lo) or p_hi > hi + .1 * (hi - lo) or p_hi - p_lo < span:
            continue
        # Natural fit: round breakpoints and a fair share of the typical range.
        coverage = min(1., (p_hi - p_lo) / (hi - lo))
        rounded = roundness([v * factor + offset for v in values], unit)
        guesses.append(AxisGuess(quantity, unit, factor, offset, round(.35 * coverage + .65 * rounded, 3)))
    guesses.sort(key=lambda g: -g.score)
    return guesses[:top]
