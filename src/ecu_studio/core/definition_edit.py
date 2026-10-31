"""Checked editing of one map definition: validate, preview, commit with undo.

Only the DEFINITION changes (name, geometry, type, scaling, axes); firmware bytes
are never written. A proposal is built from the existing ``MapDefinition`` and
validated against the image before anything is committed; the commit goes
through ``BinaryImage.commit_metadata`` and is therefore undoable like byte
edits. ``verified`` is only set when the caller passes the user's explicit
choice - automatic detection never verifies.
"""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass, field
from .model import FORMATS, BinaryImage, MapDefinition, map_from_record

# Fields the guided editor may change. Everything else is carried over unchanged.
EDITABLE = ('name', 'notes', 'offset', 'rows', 'cols', 'dtype', 'endian', 'factor', 'bias', 'unit',
            'axis_x_offset', 'axis_y_offset', 'axis_x_unit', 'axis_y_unit', 'verified')
# Changes that make an earlier review meaningless (where and how values and axes are read and scaled).
STRUCTURAL = ('offset', 'rows', 'cols', 'dtype', 'endian', 'factor', 'bias', 'axis_x_offset', 'axis_y_offset',
              'axes_x', 'axes_y')


@dataclass
class AxisSpec:
    """Where and how a stored axis is read (None offset = no stored axis)."""
    offset: int | None = None
    dtype: str = 'u16'
    endian: str = 'big'
    factor: float = 1.0
    bias: float = 0.0


@dataclass
class EditProposal:
    original: MapDefinition
    proposed: MapDefinition
    warnings: list[str] = field(default_factory=list)

    @property
    def changes(self) -> dict[str, tuple[object, object]]:
        """Field -> (before, after) for every edited field that differs."""
        a, b = self.original.asdict(), self.proposed.asdict()
        keys = [*EDITABLE, 'axes_x', 'axes_y']
        return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}


def read_axis(image: BinaryImage, spec: AxisSpec, count: int) -> list[float]:
    """Physical axis values ``count`` x ``spec.dtype`` from ``spec.offset`` (validated)."""
    if spec.offset is None:
        return []
    if spec.dtype not in FORMATS:
        raise ValueError('Nicht unterstützter Achsen-Datentyp')
    if not math.isfinite(spec.factor) or spec.factor == 0 or not math.isfinite(spec.bias):
        raise ValueError('Ungültige Achsenskalierung')
    width = FORMATS[spec.dtype][1]
    if spec.offset < 0 or spec.offset + count * width > image.size:
        raise ValueError('Achse liegt (teilweise) außerhalb der BIN-Datei')
    probe = MapDefinition('Achse', spec.offset, 1, count, spec.dtype, spec.endian, spec.factor, spec.bias)
    return [round(float(image.physical_value(probe, 0, i)), 8) for i in range(count)]


def propose(image: BinaryImage, current: MapDefinition, fields: dict, *,
            axis_x: AxisSpec | None = None, axis_y: AxisSpec | None = None,
            reconfirmed: bool = False) -> EditProposal:
    """Validated proposal; raises ValueError with a user-readable reason when invalid.

    ``axis_x``/``axis_y``: None keeps the axis as it is; ``AxisSpec(None)`` removes the stored axis address and
    its values. A structural change of a verified definition resets ``verified`` unless the user explicitly
    confirmed the review again for this edit (``reconfirmed``).
    """
    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise ValueError('Nicht bearbeitbare Felder: ' + ', '.join(sorted(unknown)))
    record = copy.deepcopy(current.asdict())
    record.update(fields)
    proposed = map_from_record(record, set())
    proposed._unknown_fields = copy.deepcopy(current._unknown_fields)
    proposed.name = proposed.name.strip()
    if not proposed.name:
        raise ValueError('Name darf nicht leer sein')
    if current.equation and (proposed.factor != current.factor or proposed.bias != current.bias):
        raise ValueError('Nichtlineare Formel aus der Definition kann nicht durch Faktor/Offset ersetzt werden')
    geometry_changed = (proposed.rows, proposed.cols) != (current.rows, current.cols)
    warnings = []
    for which, spec, count in (('x', axis_x, proposed.cols), ('y', axis_y, proposed.rows)):
        values = getattr(proposed, f'axes_{which}')
        if spec is not None:
            values = read_axis(image, spec, count)
            if spec.offset is None and getattr(current, f'axis_{which}_offset') is not None:
                warnings.append(f'{which.upper()}-Achsenadresse entfernt – die daraus gelesenen Werte ebenfalls.')
            setattr(proposed, f'axis_{which}_offset', spec.offset)
            if spec.offset is not None and len(set(values)) == len(values) and values != sorted(values) \
                    and values != sorted(values, reverse=True):
                warnings.append(f'{which.upper()}-Achse ist nicht monoton – Adresse oder Datentyp prüfen.')
        elif geometry_changed and values and len(values) != count:
            # Old axis values no longer fit the new size: drop them instead of mislabelling cells.
            values = []
            setattr(proposed, f'axis_{which}_offset', None)
            warnings.append(f'{which.upper()}-Achsenwerte passen nicht mehr zur neuen Größe und wurden entfernt.')
        setattr(proposed, f'axes_{which}', values)
    proposed.validate(image.size)
    for which, count in (('x', proposed.cols), ('y', proposed.rows)):
        values = getattr(proposed, f'axes_{which}')
        if values and len(values) != count:
            raise ValueError(f'{which.upper()}-Achse hat {len(values)} Werte, das Kennfeld {count}')
    if proposed.verified and not current.verified:
        warnings.append('Wird als geprüft markiert – nur nach fachlicher Prüfung bestätigen.')
    structural = [key for key in STRUCTURAL if getattr(proposed, key) != getattr(current, key)]
    if structural and current.verified and proposed.verified:
        if reconfirmed:
            warnings.append('Struktur einer geprüften Definition geändert – Prüfung ausdrücklich erneut bestätigt.')
        else:
            # The review covered the old address/type/scaling/axes; it does not carry over to new ones.
            proposed.verified = False
            fields_text = ', '.join(structural)
            warnings.append(f'Struktur geändert ({fields_text}) – Prüfstatus zurückgesetzt. '
                            'Nach erneuter Prüfung den Prüfstatus ausdrücklich wieder setzen.')
    return EditProposal(current, proposed, warnings)


def preview_values(image: BinaryImage, m: MapDefinition, limit: int = 32) -> list[list[float]]:
    """Physical cell values of the proposal (at most ``limit`` x ``limit``), from the current bytes."""
    return [[float(image.physical_value(m, r, c)) for c in range(min(m.cols, limit))]
            for r in range(min(m.rows, limit))]


def commit(image: BinaryImage, maps: list[MapDefinition], proposal: EditProposal, *,
           confirmed: bool) -> MapDefinition:
    """Replace the definition in ``maps`` (undoable metadata change). Bytes stay untouched."""
    if not confirmed:
        raise ValueError('Änderung muss ausdrücklich bestätigt werden')
    try:
        index = next(i for i, m in enumerate(maps) if m is proposal.original)
    except StopIteration:
        raise ValueError('Definition ist nicht mehr im Katalog – bitte neu öffnen') from None
    if maps[index].asdict() != proposal.original.asdict():
        raise ValueError('Definition wurde inzwischen geändert – bitte neu prüfen')
    if not proposal.changes:
        return proposal.original
    proposal.proposed.validate(image.size)
    new = copy.deepcopy(proposal.proposed)
    new.source = 'manual' if new.source in ('heuristic', 'reference-shape', 'ml-proposed') else new.source
    before = list(maps)
    after = [*maps[:index], new, *maps[index + 1:]]
    image.commit_metadata(maps, before, after, label=f'Definition bearbeitet: {new.name}',
                          evidence={'fields': sorted(proposal.changes)})
    return maps[index]
