"""Synthetic package tests; no proprietary firmware or OEM validity claims."""
import copy
import json
from dataclasses import replace
import pytest

from ecu_studio.core.model import BinaryImage, MapDefinition, load_project, save_project, read_project_snapshots
from ecu_studio.core.map_pack import (MAX_MAPS, make_pack, read_pack, write_pack, parse_pack, preview_pack,
                                     apply_pack, source_for_comparison)
from ecu_studio.core.storage import canonical_digest


def fixture():
    raw = bytearray(8192)
    raw[16:25] = b'EDC17C69 '
    raw[40:50] = b'0281031428'
    raw[55:65] = b'1037552744'
    image = BinaryImage(raw)
    maps = [MapDefinition('Boost', 512, 4, 4, 'u16', 'big', factor=.1, bias=3, unit='kPa',
                          source='a2l', verified=True, axes_x=[1000, 2000, 3000, 4000], axes_y=[10, 20, 30, 40],
                          axis_x_offset=128, axis_x_ref='RPM'),
            MapDefinition('Torque', 1024, 4, 4, 's16', 'little', source='xdf',
                          axis_x_offset=128, axis_x_ref='RPM')]
    return image, maps


def changed(pack, fn):
    obj = copy.deepcopy(pack.document); fn(obj)
    obj['integrity_sha256'] = canonical_digest(obj)
    return obj


@pytest.mark.parametrize('dtype', ['u8', 's8', 'u16', 's16', 'u32', 's32', 'f32'])
@pytest.mark.parametrize('endian', ['big', 'little'])
def test_roundtrip_fields_axes_and_no_promoted_trust(tmp_path, dtype, endian):
    image, maps = fixture(); maps[0] = replace(maps[0], dtype=dtype, endian=endian)
    pack = make_pack(image, maps)
    path = tmp_path / 'test.ecupack.json'; write_pack(path, pack)
    loaded = read_pack(path)
    assert loaded.document == pack.document
    assert len(loaded.document['axis_groups']) == 1
    target = []; versions = []
    preview = preview_pack(loaded, image, target)
    assert not preview.conflicts
    with pytest.raises(ValueError): apply_pack(image, target, preview)
    apply_pack(image, target, preview, confirmed=True, snapshots=versions)
    assert not any(m.verified for m in target) and target[0].dtype == dtype
    assert target[0].factor == .1 and target[0].bias == 3
    assert target[0].axis_x_offset == target[1].axis_x_offset == 128
    assert versions and not image.dirty_bytes
    assert image.undo() and target == [] and versions == []
    assert image.redo() and len(target) == 2 and len(versions) == 1


def test_legacy_v1_and_future_fields(tmp_path):
    image, maps = fixture()
    legacy = {'format': 'ecu-studio-map-pack', 'version': 1, 'source_size': image.size,
              'source_sha256': image.digest, 'maps': [m.asdict() for m in maps]}
    assert not preview_pack(parse_pack(legacy), image, []).conflicts
    pack = make_pack(image, maps)
    future = parse_pack(changed(pack, lambda p: p['maps'][0].update(future_axis={'mode': 'test'})))
    assert future.unknown_fields == ('maps.future_axis',)
    path = tmp_path / 'future.json'; write_pack(path, future)
    assert read_pack(path).document == future.document
    with pytest.raises(ValueError, match='Unknown'): preview_pack(future, image, [])
    for version in (True, 3, '2'):
        with pytest.raises(ValueError): parse_pack(changed(pack, lambda p: p.update(version=version)))


@pytest.mark.parametrize('edit', [
    lambda p: p['maps'][0].update(offset=-1),
    lambda p: p['maps'][0].update(offset=8191),
    lambda p: p['maps'][0].update(rows=True),
    lambda p: p['maps'][0].update(verified='false'),
    lambda p: p['maps'][0].update(axes_x=[1, 2]),
    lambda p: p['maps'][0].update(axis_x_offset=8190),
    lambda p: p.update(source_size='8192'),
    lambda p: p.update(axis_groups=[]),
    lambda p: p.update(maps=[]),
])
def test_invalid_geometry_and_metadata_rejected(edit):
    image, maps = fixture(); pack = make_pack(image, maps)
    with pytest.raises(ValueError): parse_pack(changed(pack, edit))


def test_wrong_ecu_software_and_hash_require_source_alignment():
    image, maps = fixture(); pack = make_pack(image, maps)
    for identity in ({'family': 'MS43'}, {'software': ['1037000000']}, {'hardware': ['other']}):
        bad = parse_pack(changed(pack, lambda p: p['identity'].update(identity)))
        with pytest.raises(ValueError): preview_pack(bad, image, [])
    other = BinaryImage(b'Z' + image.original[1:])
    with pytest.raises(ValueError, match='SHA-256'): preview_pack(pack, other, [])
    with pytest.raises(ValueError, match='SHA-256'): source_for_comparison(pack, other)
    assert all(not m.verified for m in source_for_comparison(pack, image))


def test_overlap_duplicate_stale_and_cancel_are_atomic():
    image, maps = fixture(); pack = make_pack(image, maps)
    for existing in ([maps[0]], [replace(maps[0], offset=513)]):
        preview = preview_pack(pack, image, existing)
        assert preview.conflicts
        before = [m.asdict() for m in existing]
        with pytest.raises(ValueError): apply_pack(image, existing, preview, confirmed=True)
        assert before == [m.asdict() for m in existing] and not image.journal
    duplicate = make_pack(image, [maps[0], maps[0]])
    assert preview_pack(duplicate, image, []).conflicts
    existing = []; preview = preview_pack(pack, image, existing)
    existing.append(replace(maps[0], offset=4096))
    with pytest.raises(ValueError): apply_pack(image, existing, preview, confirmed=True)
    assert len(existing) == 1 and not image.dirty_bytes


def test_no_firmware_paths_annotations_or_unknown_fields_exported(tmp_path):
    image, maps = fixture()
    maps[0].notes = 'private customer and bytes DEAD BEEF'
    maps[0].label_evidence = r'C:\private\customer.bin'
    pack = make_pack(image, maps, include_axes=False)
    data = json.dumps(pack.document)
    assert 'private' not in data and 'DEAD BEEF' not in data and pack.document['axis_groups'] == []
    assert not any(k in pack.document for k in ('original', 'patches', 'source_file'))
    maps[0]._unknown_fields = {'private_extension': 'do not publish'}
    with pytest.raises(ValueError): make_pack(image, maps)
    source = tmp_path / 'source.bin'; source.write_bytes(image.original)
    with pytest.raises(ValueError): write_pack(source, pack, protected=(source,))
    assert source.read_bytes() == image.original


def test_damaged_duplicate_keys_size_and_resources(tmp_path):
    image, maps = fixture(); pack = make_pack(image, maps)
    path = tmp_path / 'broken.json'
    for content in ('{', '[]', '{"version":2,"version":1}', '{"x":NaN}'):
        path.write_text(content)
        with pytest.raises(ValueError): read_pack(path)
    obj = copy.deepcopy(pack.document); obj['maps'][0]['name'] = 'tampered'
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match='integrity'): read_pack(path)
    with pytest.raises(ValueError): parse_pack(changed(pack, lambda p: p.update(maps=[p['maps'][0]] * (MAX_MAPS + 1))))


def test_import_byte_edit_undo_order_and_project_reopen(tmp_path):
    image, maps = fixture(); target = []; snapshots = []
    apply_pack(image, target, preview_pack(make_pack(image, maps), image, []), confirmed=True, snapshots=snapshots)
    image.write_physical(target[0], 0, 0, 4)
    assert image.undo() and not image.dirty_bytes and len(target) == 2
    assert image.undo() and target == [] and snapshots == []
    assert image.redo() and len(target) == 2
    path = tmp_path / 'project.ecustudio'
    save_project(path, image, target, [], 'package workflow', snapshots)
    reopened, definitions, _, _ = load_project(path)
    assert reopened.digest == image.digest and definitions[0].asdict() == target[0].asdict()
    assert len(read_project_snapshots(path, reopened)) == 1
    assert not reopened.dirty_bytes


def test_metadata_undo_refuses_later_untracked_edits():
    image, maps = fixture(); target = []
    apply_pack(image, target, preview_pack(make_pack(image, maps), image, []), confirmed=True)
    target[0].name = 'later edit'
    with pytest.raises(ValueError): image.undo()
    assert target[0].name == 'later edit' and len(image._undo) == 1


def test_large_pack_and_limit(tmp_path):
    image = BinaryImage(bytes(128 * MAX_MAPS))
    maps = [MapDefinition(f'M{i}', i * 128, 4, 4, 'u16') for i in range(MAX_MAPS)]
    pack = make_pack(image, maps)
    path = tmp_path / 'large.json'; write_pack(path, pack)
    preview = preview_pack(read_pack(path), image, [])
    assert len(preview.records) == MAX_MAPS and not preview.conflicts
    path.write_bytes(b' ' * (16 * 1024**2 + 1))
    with pytest.raises(ValueError, match='16 MiB'): read_pack(path)


def test_explicit_annotations_and_unknown_text_preserved_only_on_request():
    image, maps = fixture()
    maps[0].notes = 'Public description'; maps[0].label_evidence = 'Reviewed against local definition'
    assert make_pack(image, maps).document['maps'][0]['notes'] == ''
    pack = make_pack(image, maps, include_annotations=True)
    assert pack.document['maps'][0]['notes'] == 'Public description'
    maps[0].name = r'C:\private\name'
    with pytest.raises(ValueError): make_pack(image, maps)
