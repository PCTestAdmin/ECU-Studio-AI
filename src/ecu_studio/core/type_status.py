"""What is established about a table's data type and scaling, and from which source (after 1.21.0-rc1).

Data type, per property (value width, sign, byte order), one of six statuses, strongest first:

  bestätigt    from a definition (A2L, XDF, map pack, project) or checked by the user
  codebelegt   from the program code: load instructions of the interpolation routine that reads
               the table (TriCore), or the processor architecture of that code (byte order)
  abgeleitet   from the stored data structure: record header, record layout, the majority of the
               records of this image, the only strictly rising reading of an axis; or carried over
               from a proposal source (name transfer, public preview, library reference) whose
               placement in this file is unchecked
  wertgleich   both sign readings give the same numbers for every cell (no top bit set). The values
               do not tell which type the program uses; writing a value with the top bit set would
               make the difference visible
  alternativ   one reading was chosen, the evidence leaves the listed other readings open, which
               give different values
  unbestimmt   only the smoothness of the values supports the reading, or nothing does

A property whose sources disagree (records of the image, or detection against the definition) says
so in ``contradiction``; its status never rises because of it.

Scaling (factor, offset, unit): from a definition with its source (e.g. A2L COMPU_METHOD name and
kind), checked by the user, or unknown: then the values are raw values. A plausible value range
never establishes a conversion here, and proposals (name transfer, detection) never carry one.

This module only reads what the detection already recorded (record layout, notes, alternatives);
it changes no candidate and adds no evidence. The "?" markers of the map list (confidence.dtype_doubt)
stay as they are; a property with status ``alternativ`` or ``unbestimmt`` always has one.
"""
from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
from .confidence import CODE as CODE_LEVEL, DATA_PATTERN, STRUCTURE, WIDTH_OPEN, _WIDTH_GUESSED, evidence_level
from .model import BinaryImage, MapDefinition

CONFIRMED, CODE, DERIVED, EQUAL, ALTERNATIVE, UNDETERMINED = (
    'bestätigt', 'codebelegt', 'abgeleitet', 'wertgleich', 'alternativ', 'unbestimmt')
STATUSES = (CONFIRMED, CODE, DERIVED, EQUAL, ALTERNATIVE, UNDETERMINED)
LABELS = {CONFIRMED: 'Bestätigt', CODE: 'Durch Programmcode belegt', DERIVED: 'Abgeleitet',
          EQUAL: 'Lesarten wertgleich', ALTERNATIVE: 'Alternative offen', UNDETERMINED: 'Unbestimmt'}
WIDTH, SIGN, BYTE_ORDER = 'width', 'sign', 'byte-order'
PROPERTY_LABELS = {WIDTH: 'Wertebreite', SIGN: 'Vorzeichen', BYTE_ORDER: 'Byte-Reihenfolge'}
RAW, KNOWN, CHECKED = 'unbekannt', 'aus Definition', 'geprüft'
# Breakpoint arrays: only a strictly rising reading is an axis, so the sign can follow from the values.
AXIS_LAYOUTS = ('candidate:record-axis', 'candidate:count-axis')
SCALING_LABELS = {RAW: 'Unbekannt: Rohwerte', KNOWN: 'Aus Definition', CHECKED: 'Vom Nutzer geprüft'}
# Notes the A2L link writes when it keeps raw values (core/a2l.py)
RAW_NOTE = 'nicht unterstützt: Rohwerte'
# Automatic candidates: the detection's own evidence decides (record layout, notes).
HEURISTIC_SOURCES = frozenset({'heuristic', 'ml-proposed', 'tcu-pair-heuristic', 'synthetic'})
# Proposals: the type comes from elsewhere and is carried over; its placement here is unchecked.
PROPOSAL_SOURCES = {'transfer-proposed': 'Definition des Quellstands übernommen, Lage hier ungeprüft (Namensübertragung)',
                    'xdf-preview': 'öffentliche Definition, Zuordnung zu dieser Datei ungeprüft',
                    'exact-reference': 'Referenzsignatur der Bibliothek, Zuordnung ungeprüft',
                    'manual_2d': 'manuell in den Rohdaten gewählt, ungeprüft'}
_CONFLICT_PROPERTY = {'Zellbreite': WIDTH, 'Vorzeichen': SIGN, 'Byte-Reihenfolge': BYTE_ORDER}


@dataclass(frozen=True)
class PropertyStatus:
    key: str                  # WIDTH / SIGN / BYTE_ORDER
    value: str                # e.g. '16 Bit', 'vorzeichenlos', 'little'
    status: str               # one of STATUSES
    source: str               # where the value comes from (a fact, never a probability)
    alternatives: tuple[str, ...] = ()
    contradiction: str = ''   # sources that disagree, said aloud

    def describe(self) -> str:
        alt = (' (auch möglich: ' + ', '.join(self.alternatives) + ')') if self.alternatives else ''
        contra = f' – Widerspruch: {self.contradiction}' if self.contradiction else ''
        return f'{PROPERTY_LABELS[self.key]} {self.value}: {LABELS[self.status]} – {self.source}{alt}{contra}'


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

    @property
    def contradictions(self) -> list[PropertyStatus]:
        return [p for p in self.properties if p.contradiction]

    def get(self, key: str) -> PropertyStatus | None:
        return next((p for p in self.properties if p.key == key), None)


def source_class(m: MapDefinition) -> str:
    """'user' (checked), 'definition', 'proposal' or 'heuristic'."""
    if m.verified:
        return 'user'
    if m.source in HEURISTIC_SOURCES:
        return 'heuristic'
    if m.source in PROPOSAL_SOURCES or m.source.startswith('transfer'):
        return 'proposal'
    return 'definition'


def _top_bit(image: BinaryImage | None, m: MapDefinition) -> bool | None:
    """True/False when the cells were read; None without image."""
    if image is None:
        return None
    from .fusion import sign_matters
    return sign_matters(image, m)


def _only_rising(image: BinaryImage, m: MapDefinition) -> bool:
    """True if the axis rises strictly in its own sign reading and not in the other one."""
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


def _conflicts(texts) -> dict[str, str]:
    """Property -> note, from fusion conflict texts ('0x..: <kind> – behalten ...')."""
    out: dict[str, str] = {}
    for text in texts or ():
        head = text.split(' – ', 1)[0]
        for kind, key in _CONFLICT_PROPERTY.items():
            if kind in head:
                out.setdefault(key, 'Erkennung und Definition uneinig')
    return out


def type_status(m: MapDefinition, image: BinaryImage | None = None, conflicts=()) -> TypeStatus:
    """Status and source of the value width, sign and byte order of ``m``.

    ``image`` lets the sign question be settled as "wertgleich" when no cell has its top bit set.
    ``conflicts`` are fusion conflict texts at this table (detection against definition).
    Floating point values have no separate sign question; 8-bit values no byte order.
    """
    width_text = f'{m.width * 8} Bit'
    signed = m.dtype.startswith('s')
    sign_text = 'Gleitkomma' if m.dtype.startswith('f') else 'vorzeichenbehaftet' if signed else 'vorzeichenlos'
    contra = _conflicts(conflicts)
    props: list[PropertyStatus] = []
    origin = source_class(m)
    if origin != 'heuristic':
        if origin == 'proposal':
            status = UNDETERMINED if m.source == 'manual_2d' else DERIVED
            src = PROPOSAL_SOURCES.get(m.source, PROPOSAL_SOURCES['transfer-proposed'])
        else:
            status, src = CONFIRMED, 'vom Nutzer geprüft' if origin == 'user' else f'Definition ({m.source})'
        props.append(PropertyStatus(WIDTH, width_text, status, src, contradiction=contra.get(WIDTH, '')))
        if not m.dtype.startswith('f'):
            props.append(PropertyStatus(SIGN, sign_text, status, src, contradiction=contra.get(SIGN, '')))
        if m.width > 1:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, status, src, contradiction=contra.get(BYTE_ORDER, '')))
        return TypeStatus(props)
    level = evidence_level(m if m.source == 'heuristic' else dataclasses.replace(m, source='heuristic'))
    notes = m.notes or ''
    # value width
    if WIDTH_OPEN in notes:
        props.append(PropertyStatus(WIDTH, width_text, ALTERNATIVE, 'kein Beleg für die Wertebreite', ('8 Bit',)))
    elif level == DATA_PATTERN:
        props.append(PropertyStatus(WIDTH, width_text, UNDETERMINED, 'nur aus dem Werteverlauf geschätzt'))
    elif any(text in notes for text in _WIDTH_GUESSED):
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'nur aus dem Datensatzaufbau (ungeprüft)'))
    elif level == CODE_LEVEL:
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'Programmcode-Zugriff auf die Tabelle'))
    else:
        props.append(PropertyStatus(WIDTH, width_text, DERIVED, 'gespeicherter Datensatz (Kopf, Achsen, Folgeobjekt)'))
    # sign
    if not m.dtype.startswith('f'):
        top = _top_bit(image, m)
        code_call = level == CODE_LEVEL and m.record_layout == 'candidate:code-call'
        if m.dtype_alternatives:
            props.append(PropertyStatus(SIGN, sign_text, ALTERNATIVE,
                                        'die Belege entscheiden das Vorzeichen nicht; die Lesarten ergeben '
                                        'unterschiedliche Werte' if top else
                                        'die Belege entscheiden das Vorzeichen nicht',
                                        tuple(m.dtype_alternatives),
                                        'Ladebefehle der Routine uneinig' if code_call else ''))
        elif code_call:
            props.append(PropertyStatus(SIGN, sign_text, CODE, 'Ladebefehle der Interpolationsroutine'))
        elif top and m.record_layout in AXIS_LAYOUTS and image is not None and _only_rising(image, m):
            props.append(PropertyStatus(SIGN, sign_text, DERIVED, 'nur diese Lesart ergibt steigende Stützstellen'))
        elif top is False:
            props.append(PropertyStatus(SIGN, sign_text, EQUAL,
                                        'kein Wert mit gesetztem obersten Bit: beide Lesarten ergeben dieselben '
                                        'Zahlen; welchen Typ der Programmcode verwendet, ist nicht belegt'))
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
        from .axis_records import ENDIAN_OPEN, ENDIAN_OPEN_AXES
        other = 'little' if m.endian == 'big' else 'big'
        if ENDIAN_OPEN_AXES in notes:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, ALTERNATIVE, 'die Werte entscheiden es nicht', (other,),
                                        'gegen die Mehrheit der Datensätze dieses Abbilds gelesen'))
        elif ENDIAN_OPEN in notes:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, ALTERNATIVE, 'keine Mehrheit entscheidet', (other,),
                                        'die Datensätze dieses Abbilds sind uneinig'))
        elif level == DATA_PATTERN:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, UNDETERMINED, 'nur aus dem Werteverlauf geschätzt'))
        elif 'aus der Mehrheit der Datensätze' in notes:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, DERIVED, 'Mehrheit der Datensätze dieses Abbilds'))
        elif level == CODE_LEVEL:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, CODE, 'Prozessorarchitektur des Programmcodes'))
        else:
            props.append(PropertyStatus(BYTE_ORDER, m.endian, DERIVED, 'Zähler und Achsen des eigenen Datensatzes'))
    if contra:
        props = [dataclasses.replace(p, contradiction=p.contradiction or contra.get(p.key, '')) for p in props]
    return TypeStatus(props)


def scaling_of(m: MapDefinition) -> Scaling:
    """Factor, offset and unit of ``m`` with their source; raw values when no conversion is established.

    Automatic candidates and proposals never carry an established conversion: their values are raw
    values even when a factor was carried over (name transfer and similar hints stay unchecked).
    """
    if m.verified:
        return Scaling(m.factor, m.bias, m.unit, CHECKED, m.scaling_source or 'vom Nutzer bestätigt', m.equation)
    if source_class(m) in ('heuristic', 'proposal'):
        carried = m.factor != 1 or m.bias != 0 or m.unit
        why = ('übernommene Umrechnung ungeprüft' if carried else 'keine Umrechnung belegt')
        return Scaling(1.0, 0.0, '', RAW, why)
    if RAW_NOTE in (m.notes or '') or (m.scaling_source and RAW_NOTE in m.scaling_source):
        return Scaling(1.0, 0.0, m.unit, RAW, m.scaling_source or f'Definition ({m.source}): Umrechnung nicht unterstützt')
    source = m.scaling_source or (f'Formel der Definition ({m.source})' if m.equation else f'Definition ({m.source})')
    return Scaling(m.factor, m.bias, m.unit, KNOWN, source, m.equation)


def summary(m: MapDefinition, image: BinaryImage | None = None, conflicts=()) -> list[str]:
    """Lines for the detail view: one per data-type property, then the conversion."""
    return [p.describe() for p in type_status(m, image, conflicts).properties] + [scaling_of(m).describe()]


__all__ = ['CONFIRMED', 'CODE', 'DERIVED', 'EQUAL', 'ALTERNATIVE', 'UNDETERMINED', 'STATUSES', 'LABELS',
           'PropertyStatus', 'Scaling', 'TypeStatus', 'type_status', 'scaling_of', 'summary', 'source_class',
           'STRUCTURE']
