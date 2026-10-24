"""Open ECU Studio map-pack v2; metadata only, never firmware or byte patches.

v1 remains readable. Imports always require a preview and keep definitions
unverified. Other originals must be aligned through version_compare with the
local source BIN; equal offsets are not evidence.
"""
from __future__ import annotations
import copy
import bisect
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re

from .axis_groups import shared_axis_groups
from .identification import identify
from .model import BinaryImage, MapDefinition, map_from_record
from .storage import atomic_write, canonical_digest

FORMAT = 'ecu-studio-map-pack'
VERSION = 2
MAX_BYTES = 16 * 1024**2
MAX_MAPS = 5000
MAX_CELLS = 5_000_000
MAP_FIELDS = set(MapDefinition.__dataclass_fields__) - {'_unknown_fields'}
TOP_FIELDS = {'format', 'version', 'source_sha256', 'source_size', 'identity', 'maps',
              'axis_groups', 'integrity_sha256', 'provenance'}


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key')
        obj[key] = value
    return obj


def _bounded(value, depth=0):
    if depth > 12:
        raise ValueError('Package nesting limit exceeded')
    if isinstance(value, str):
        if len(value) > 4096 or any(c in value for c in ('\x00', '\r')):
            raise ValueError('Invalid package text')
    elif isinstance(value, dict):
        for k, v in value.items():
            _bounded(k, depth + 1); _bounded(v, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_MAPS:
            raise ValueError('Package list limit exceeded')
        for v in value:
            _bounded(v, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite package value')


def _identity(image):
    i = identify(BinaryImage(image.original))
    return {'family': i.family or '', 'hardware': list(i.hardware), 'software': list(i.software)}


def _groups(maps):
    return json.loads(json.dumps([asdict(g) for g in shared_axis_groups(maps)]))


def _validate_map(record, size):
    if not isinstance(record, dict):
        raise ValueError('Invalid package map')
    m = map_from_record(record, set())
    ints = ('offset', 'rows', 'cols', 'major_stride_bits', 'minor_stride_bits')
    if any(type(getattr(m, k)) is not int for k in ints):
        raise ValueError('Map addresses and dimensions must be integers')
    if type(m.verified) is not bool:
        raise ValueError('Map verification must be a boolean')
    if m.ecu_address is not None and (type(m.ecu_address) is not int or not 0 <= m.ecu_address <= 0xFFFFFFFF):
        raise ValueError('Invalid symbolic ECU address')
    if m.calibrated_rate is not None and (type(m.calibrated_rate) not in (int, float) or not 0 <= m.calibrated_rate <= 1):
        raise ValueError('Invalid calibrated rate')
    if not isinstance(m.type_alternatives, list) or any(not isinstance(s, str) for s in m.type_alternatives):
        raise ValueError('Invalid map alternatives')
    defaults = MapDefinition('', 0)
    for k in MAP_FIELDS:
        v, default = getattr(m, k), getattr(defaults, k)
        if isinstance(default, str) and not isinstance(v, str):
            raise ValueError('Invalid map text field')
        if type(default) is bool and type(v) is not bool:
            raise ValueError('Invalid map boolean')
        if type(default) is float and (type(v) not in (int, float) or not math.isfinite(v)):
            raise ValueError('Invalid map numeric field')
    m.validate(size)
    if not m.name.strip():
        raise ValueError('Map name required')
    for values, count, offset in ((m.axes_x, m.cols, m.axis_x_offset), (m.axes_y, m.rows, m.axis_y_offset)):
        if not isinstance(values, list) or (values and len(values) != count):
            raise ValueError('Axis point count mismatch')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Invalid axis value')
        # The current model has no independent axis storage type. Even the
        # minimum possible byte span must fit; do not invent an axis width.
        if offset is not None and offset + count > size:
            raise ValueError('Axis storage exceeds source image')
    return m


@dataclass(frozen=True)
class MapPack:
    document: dict
    unknown_fields: tuple[str, ...]

    @property
    def sha256(self):
        return self.document['source_sha256']

    def maps(self):
        return [_validate_map(r, self.document['source_size']) for r in self.document['maps']]


def parse_pack(obj: dict) -> MapPack:
    _bounded(obj)
    if not isinstance(obj, dict) or obj.get('format') != FORMAT or type(obj.get('version')) is not int or obj['version'] not in (1, 2):
        raise ValueError('Unsupported map-pack format/version')
    if not isinstance(obj.get('source_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', obj['source_sha256']):
        raise ValueError('Invalid source SHA-256')
    size = obj.get('source_size')
    if type(size) is not int or not 1 <= size <= 128 * 1024**2:
        raise ValueError('Invalid source image size')
    records = obj.get('maps')
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_MAPS:
        raise ValueError('Expected 1..5000 package maps')
    if 'integrity_sha256' in obj and canonical_digest(obj) != obj['integrity_sha256']:
        raise ValueError('Map-pack integrity mismatch')
    if obj['version'] == 2 and 'integrity_sha256' not in obj:
        raise ValueError('Map-pack integrity field required')
    unknown = set(obj) - TOP_FIELDS
    maps, cells = [], 0
    for r in records:
        m = _validate_map(r, size)
        cells += m.rows * m.cols
        if cells > MAX_CELLS:
            raise ValueError('Package cell budget exceeded')
        unknown.update('maps.' + k for k in set(r) - MAP_FIELDS)
        maps.append(m)
    identity = obj.get('identity', {'family': '', 'hardware': [], 'software': []})
    if not isinstance(identity, dict) or not isinstance(identity.get('family'), str):
        raise ValueError('Invalid ECU identity')
    unknown.update('identity.' + k for k in set(identity) - {'family', 'hardware', 'software'})
    for k in ('hardware', 'software'):
        if not isinstance(identity.get(k), list) or any(not isinstance(s, str) or not s.strip() for s in identity[k]):
            raise ValueError('Invalid hardware/software identity')
    provenance = obj.get('provenance', {})
    if not isinstance(provenance, dict) or any(not isinstance(v, str) for v in provenance.values()):
        raise ValueError('Invalid package provenance')
    unknown.update('provenance.' + k for k in set(provenance) - {'trust', 'description'})
    if obj['version'] == 2 and obj.get('axis_groups') != json.loads(json.dumps(_groups(maps))):
        raise ValueError('Shared axis groups disagree with map addresses')
    return MapPack(copy.deepcopy(obj), tuple(sorted(unknown)))


def read_pack(path) -> MapPack:
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Map-pack exceeds 16 MiB')
    try:
        obj = json.loads(data, object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON value')))
        return parse_pack(obj)
    except (RecursionError, UnicodeError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError('Invalid map-pack structure') from exc


def make_pack(image, maps, *, include_axes=True, include_annotations=False) -> MapPack:
    records = []
    for m in maps:
        if m._unknown_fields:
            raise ValueError('Export requires a version that understands all map fields')
        record = m.asdict()
        # Free-form annotations may contain customer names, paths or ECU bytes.
        # The export keeps the explicit definition fields and source class only.
        for key in ('notes', 'label_evidence', 'label_origin', 'axes_info', 'folder'):
            if include_annotations and key in ('notes', 'label_evidence'):
                continue
            record[key] = ''
        record['source'] = m.source if m.source in ('a2l', 'xdf', 'romraider', 'csv', 'manual', 'pack', 'heuristic', 'transfer-proposed') else 'definition'
        if not include_axes:
            for key in ('axis_x_offset', 'axis_y_offset'):
                record[key] = None
            record['axis_x_ref'] = record['axis_y_ref'] = ''
        # Reject absolute paths in explicit names instead of silently exporting them.
        for v in [*record.values(), *record['type_alternatives']]:
            if isinstance(v, str) and re.search(r'[A-Za-z]:[\\/]|\\\\|(?:^|\s)/(?:home|Users|tmp)/', v):
                raise ValueError('Private filesystem path in exported definition')
        records.append(record)
    obj = {'format': FORMAT, 'version': VERSION, 'source_sha256': image.digest,
           'source_size': image.size, 'identity': _identity(image), 'maps': records,
           'axis_groups': _groups([map_from_record(r) for r in records]),
           'provenance': {'trust': 'author-declared; not independently verified',
                          'description': 'Definitions only; no firmware or patches'}}
    obj['integrity_sha256'] = canonical_digest(obj)
    return parse_pack(obj)


def write_pack(path, pack: MapPack, *, protected=()):
    validated = parse_pack(pack.document)
    data = json.dumps(validated.document, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('Map-pack exceeds 16 MiB')
    atomic_write(path, data, protected=protected)


def _key(m):
    return m.offset, m.rows, m.cols, m.dtype, m.endian


@dataclass(frozen=True)
class PackPreview:
    target_sha256: str
    catalog_digest: str
    pack_digest: str
    records: tuple[dict, ...]
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...]


def catalog_digest(maps):
    return canonical_digest({'maps': [m.asdict() for m in maps]})


def preview_pack(pack: MapPack, image, existing) -> PackPreview:
    pack = parse_pack(pack.document)
    if pack.sha256 != image.digest or pack.document['source_size'] != image.size:
        raise ValueError('SHA-256 differs: use the local source BIN in software version comparison')
    if pack.unknown_fields:
        raise ValueError('Unknown package fields: ' + ', '.join(pack.unknown_fields))
    claimed, actual = pack.document.get('identity'), _identity(image)
    if claimed:
        if claimed['family'] and claimed['family'] != actual['family']:
            raise ValueError('ECU family mismatch')
        for key in ('hardware', 'software'):
            if claimed[key] and set(claimed[key]) != set(actual[key]):
                raise ValueError('ECU hardware/software mismatch')
    pending, conflicts, keys = [], [], {_key(m) for m in existing}
    spans = sorted((m.offset, m.offset + m.length, m.name, i) for i, m in enumerate(pack.maps()))
    # Conservative byte-envelope overlap test includes padded/strided layouts.
    end, owner = -1, ''
    for start, stop, name, _ in spans:
        if start < end:
            conflicts.append(f'{name}: overlapping package map {owner}')
        if stop > end:
            end, owner = stop, name
    existing_spans = sorted((m.offset, m.offset + m.length) for m in existing)
    starts, ends = [], []
    for start, stop in existing_spans:
        starts.append(start); ends.append(max(stop, ends[-1] if ends else -1))
    for m in pack.maps():
        if _key(m) in keys:
            conflicts.append(f'{m.name}: duplicate/existing definition')
        keys.add(_key(m))
        i = bisect.bisect_left(starts, m.offset + m.length)
        if i and ends[i - 1] > m.offset:
            conflicts.append(f'{m.name}: overlaps existing definition')
        origin = m.source
        source_verified = m.verified
        m.verified = False
        m.source = 'pack'
        m.label_origin = 'ECU Studio map pack'
        m.label_evidence = f'SHA-256 {pack.sha256}; source {origin}; author verified={source_verified}; target review required'
        pending.append(m.asdict())
    return PackPreview(image.digest, catalog_digest(existing), canonical_digest(pack.document), tuple(pending),
                       tuple(conflicts), ('Author verification is a declaration; imported definitions require target review.',))


def apply_pack(image, maps, preview: PackPreview, *, confirmed=False, snapshots=None):
    if not confirmed or preview.conflicts:
        raise ValueError('Explicit confirmation and conflict-free preview required')
    if image.digest != preview.target_sha256 or catalog_digest(maps) != preview.catalog_digest:
        raise ValueError('Catalog changed; calculate a new preview')
    added = [_validate_map(copy.deepcopy(r), image.size) for r in preview.records]
    if any(m.verified for m in added):
        raise ValueError('Imported definitions must remain unverified')
    before = list(maps)
    after = sorted([*maps, *added], key=lambda m: (m.offset, m.name))
    versions = None
    if snapshots is not None:
        from .versioning import make_snapshot
        versions = [*snapshots, make_snapshot(image, 'Map pack import', maps=after)]
    image.commit_metadata(maps, before, after, label='Map pack import',
                          evidence={'pack_sha256': preview.pack_digest, 'maps': len(added)},
                          snapshots=snapshots, snapshots_after=versions)
    return added


def source_for_comparison(pack, image):
    """Exact source definitions only; relocation remains with version_compare."""
    if pack.sha256 != image.digest:
        raise ValueError('Source BIN SHA-256 differs from package')
    preview = preview_pack(pack, image, [])
    if preview.conflicts:
        raise ValueError('Conflicting source definitions')
    return [_validate_map(r, image.size) for r in preview.records]
