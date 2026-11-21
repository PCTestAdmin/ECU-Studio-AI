"""What is established about a table's data type and scaling, and from which source (after 1.21.0-rc1).

Data type, per property (value width, sign, byte order), one of four statuses:

  bestätigt    from a definition (A2L, XDF, project) or checked by the user
  abgeleitet   from technical evidence in the image: load instructions of the program code, a
               stored record header, the record structure or the majority of records of this image;
               or the question does not arise (no cell has its top bit set: both sign readings agree)
  alternativ   one reading was chosen, the evidence leaves the listed other readings open
  unbestimmt   only the smoothness of the values supports the reading

Scaling (factor, offset, unit): from a definition with its source (e.g. A2L COMPU_METHOD name and
kind), checked by the user, or unknown: then the values are raw values. A plausible value range
never establishes a conversion here.

This module only reads what the detection already recorded (record layout, notes, alternatives);
it changes no candidate and adds no evidence. The "?" markers of the map list (confidence.dtype_doubt)
stay as they are; a property with status ``alternativ`` or ``unbestimmt`` always has one.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .confidence import CODE, DATA_PATTERN, STRUCTURE, WIDTH_OPEN, _WIDTH_GUESSED, evidence_level
from .model import BinaryImage, MapDefinition

CONFIRMED, DERIVED, ALTERNATIVE, UNDETERMINED = 'bestätigt', 'abgeleitet', 'alternativ', 'unbestimmt'
STATUSES = (CONFIRMED, DERIVED, ALTERNATIVE, UNDETERMINED)
LABELS = {CONFIRMED: 'Bestätigt', DERIVED: 'Abgeleitet', ALTERNATIVE: 'Alternative offen', UNDETERMINED: 'Unbestimmt'}
WIDTH, SIGN, BYTE_ORDER = 'width', 'sign', 'byte-order'
PROPERTY_LABELS = {WIDTH: 'Wertebreite', SIGN: 'Vorzeichen', BYTE_ORDER: 'Byte-Reihenfolge'}
RAW, KNOWN, CHECKED = 'unbekannt', 'aus Definition', 'geprüft'
# Breakpoint arrays: only a strictly rising reading is an axis, so the sign can follow from the values.
AXIS_LAYOUTS = ('candidate:record-axis', 'candidate:count-axis')
SCALING_LABELS = {RAW: 'Unbekannt: Rohwerte', KNOWN: 'Aus Definition', CHECKED: 'Vom Nutzer geprüft'}
# Notes the A2L link writes when it keeps raw values (core/a2l.py)
RAW_NOTE = 'nicht unterstützt: Rohwerte'


@dataclass(frozen=True)
class PropertyStatus:
    key: str                  # WIDTH / SIGN / BYTE_ORDER
    value: str                # e.g. '16 Bit', 'vorzeichenlos', 'little'
    status: str               # one of STATUSES
    source: str               # where the value comes from (a fact, never a probability)
    alternatives: tuple[str, ...] = ()

    def describe(self) -> str:
        alt = (' (auch möglich: ' + ', '.join(self.alternatives) + ')') if self.alternatives else ''
        return f'{PROPERTY_LABELS[self.key]} {self.value}: {LABELS[self.status]} – {self.source}{alt}'


@dataclass(frozen=True)
class Scaling:
    factor: float
    offset: float
    unit: str
    status: str               # RAW / KNOWN / CHECKED
    source: str
    equation: str = ''

    def describe(self) -> str:
        if self.status == RAW:
            return f'Umrechnung: {SCALING_LABELS[RAW]} – {self.source}'
        rule = self.equation or f'phys = roh × {self.factor:g} + {self.offset:g}'
        unit = f' [{self.unit}]' if self.unit else ''
        return f'Umrechnung: {rule}{unit} – {SCALING_LABELS[self.status]} ({self.source})'


@dataclass
class TypeStatus:
    properties: list[PropertyStatus] = field(default_factory=list)

    @property
    def overall(self) -> str:
        """The weakest status of the properties that apply (``bestätigt`` when none applies)."""
        return max((p.status for p in self.properties), key=STATUSES.index, default=CONFIRMED)

    def get(self, key: str) -> PropertyStatus | None:
        return next((p for p in self.properties if p.key == key), None)


def _definition(m: MapDefinition) -> str:
    if m.verified:
        return 'vom Nutzer geprüft'
    return f'Definition ({m.source})'


def _top_bit(image: BinaryImage | None, m: MapDefinition) -> bool | None:
    """True/False when the cells were read; None without image."""
    if image is None:
        return None
    from .fusion import sign_matters
    return sign_matters(image, m)


def _only_rising(image: BinaryImage, m: MapDefinition) -> bool:
    """True if the axis rises strictly in its own sign reading and not in the other one."""
    import dataclasses
    import numpy as np
    other = dataclasses.replace(m, dtype=('u' if m.dtype[0] == 's' else 's') + m.dtype[1:], dtype_alternatives=[])
    try:
        own, alt = (np.asarray(image.matrix(x), dtype=float).ravel() for x in (m, other))
    except (IndexError, ValueError):
        return False
    return len(own) > 1 and bool(np.all(np.diff(own) > 0)) and not bool(np.all(np.diff(alt) > 0))


AXIS_SIGN_OPEN = True


def open_axis_signs(image: BinaryImage, maps: list[MapDefinition]) -> int:
    """Keep the other sign reading open for detected axes whose values do not decide the sign: some value
    has its top bit set and the chosen reading is not the only one that rises strictly (e.g. all values
    negative: both readings rise). Returns how many; the list then shows "?"."""
    from .fusion import sign_matters
    changed = 0
    for m in maps:
        if (not AXIS_SIGN_OPEN or m.source != 'heuristic' or m.record_layout not in AXIS_LAYOUTS
                or m.dtype[1:] not in ('8', '16') or m.dtype_alternatives or not sign_matters(image, m)
                or _only_rising(image, m)):
            continue
        m.dtype_alternatives = [('u' if m.dtype[0] == 's' else 's') + m.dtype[1:]]
        changed += 1
    return changed


def type_status(m: MapDefinition, image: BinaryImage | None = None) -> TypeStatus:
    """Status and source of the value width, sign and byte order of ``m``.

    ``image`` lets the sign question be settled as "does not arise" when no cell has its top bit set.
    Floating point values have no separate sign question; 8-bit values no byte order.
    """
    width_text = f'{m.width * 8} Bit'
    signed = m.dtype.startswith('s')
    sign_text = 'Gleitkomma' if m.dtype.startswith('f') else 'vorzeichenbehaftet' if signed else 'vorzeichenlos'
    props: list[PropertyStatus] = []
    if m.source != 'heuristic' or m.verified:
        src = _definition(m)
        props.append(PropertyStatus(WIDTH, width_text, CONFIRMED, src))
        if not m.dtype.startswith('f'):
            props.append(PropertyStatus(SIGN, sign_text, CONFIRMED, src))
        if m.width > 1:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, CONFIRMED, src))
        return TypeStatus(props)
    level = evidence_level(m)
    notes = m.notes or ''
    # value width
    if WIDTH_OPEN in notes:
        props.append(PropertyStatus(WIDTH, width_text, ALTERNATIVE, 'kein Beleg für die Wertebreite', ('8 Bit',)))
    elif level == DATA_PATTERN:
        props.append(PropertyStatus(WIDTH, width_text, UNDETERMINED, 'nur aus dem Werteverlauf geschätzt'))
    elif any(text in notes for text in _WIDTH_GUESSED):
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'nur aus dem Datensatzaufbau (ungeprüft)'))
    elif level == CODE:
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'Programmcode-Zugriff auf die Tabelle'))
    else:
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'gespeicherter Datensatz (Kopf, Achsen, Folgeobjekt)'))
    # sign
    if not m.dtype.startswith('f'):
        top = _top_bit(image, m)
        if m.dtype_alternatives:
            props.append(PropertyStatus(SIGN, sign_text, ALTERNATIVE, 'die Bytes entscheiden das Vorzeichen nicht',
                                        tuple(m.dtype_alternatives)))
        elif top is False:
            props.append(PropertyStatus(SIGN, sign_text, DERIVED,
                                        'kein Wert mit gesetztem obersten Bit: beide Lesarten gleich'))
        elif level == CODE and m.record_layout == 'candidate:code-call':
            props.append(PropertyStatus(SIGN, sign_text, DERIVED, 'Ladebefehle der Interpolationsroutine'))
        elif top and m.record_layout in AXIS_LAYOUTS and image is not None and _only_rising(image, m):
            props.append(PropertyStatus(SIGN, sign_text, DERIVED, 'nur diese Lesart ergibt steigende Stützstellen'))
        elif level == DATA_PATTERN:
            props.append(PropertyStatus(SIGN, sign_text, UNDETERMINED, 'nur aus dem Werteverlauf geschätzt'))
        else:
            # Records keep the other reading open whenever a top bit is set (axis_records); without
            # an image nothing more can be said here.
            props.append(PropertyStatus(SIGN, sign_text, UNDETERMINED if top else DERIVED,
                                        'kein Beleg für das Vorzeichen' if top else
                                        'Datensatz ohne offene Vorzeichenfrage (Zellen nicht gelesen)'))
    # byte order
    if m.width > 1:
        from .axis_records import ENDIAN_OPEN
        other = 'little' if m.endian == 'big' else 'big'
        if ENDIAN_OPEN in notes:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, ALTERNATIVE,
                                        'die Datensätze dieses Abbilds sind uneinig', (other,)))
        elif level == DATA_PATTERN:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, UNDETERMINED, 'nur aus dem Werteverlauf geschätzt'))
        elif 'aus der Mehrheit der Datensätze' in notes:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, DERIVED, 'Mehrheit der Datensätze dieses Abbilds'))
        elif level == CODE:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, DERIVED, 'Prozessorarchitektur des Programmcodes'))
        else:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, DERIVED, 'Zähler und Achsen des eigenen Datensatzes'))
    return TypeStatus(props)


def scaling_of(m: MapDefinition) -> Scaling:
    """Factor, offset and unit of ``m`` with their source; raw values when no conversion is established.

    Automatic candidates never carry an established conversion: their values are raw values even
    when a factor was carried over (name transfer and similar hints stay unchecked).
    """
    if m.verified:
        return Scaling(m.factor, m.bias, m.unit, CHECKED, m.scaling_source or 'vom Nutzer bestätigt', m.equation)
    if m.source == 'heuristic':
        carried = m.factor != 1 or m.bias != 0 or m.unit
        why = ('übernommene Umrechnung ungeprüft' if carried else 'keine Umrechnung belegt')
        return Scaling(1.0, 0.0, '', RAW, why)
    if RAW_NOTE in (m.notes or '') or (m.scaling_source and RAW_NOTE in m.scaling_source):
        return Scaling(1.0, 0.0, m.unit, RAW, m.scaling_source or f'Definition ({m.source}): Umrechnung nicht unterstützt')
    source = m.scaling_source or (f'Formel der Definition ({m.source})' if m.equation else f'Definition ({m.source})')
    return Scaling(m.factor, m.bias, m.unit, KNOWN, source, m.equation)


def summary(m: MapDefinition, image: BinaryImage | None = None) -> list[str]:
    """Lines for the detail view: one per data-type property, then the conversion."""
    return [p.describe() for p in type_status(m, image).properties] + [scaling_of(m).describe()]


__all__ = ['CONFIRMED', 'DERIVED', 'ALTERNATIVE', 'UNDETERMINED', 'STATUSES', 'LABELS', 'PropertyStatus',
           'Scaling', 'TypeStatus', 'type_status', 'scaling_of', 'summary', 'STRUCTURE']
