"""Write policy for every byte transaction (quality phase 6, synthetic images only).

``BinaryImage.write_policy`` (core/edit_guard.WritePolicy) checks each commit right before the bytes are applied,
whatever produced it (cell, area, batch, recipe, transfer, version restore, checksum correction, hex edit, script):

- without an approval only bytes outside every table and stored axis may change;
- an approval names positions, revision and confirmed conflicts; anything else is stale and refused;
- a shared axis of unknown identity is refused with or without approval; only a technical clearance that matches
  the file (range, points, width, users, origin) lifts it, and it is dropped when firmware or layout change.
No test touches private firmware.
"""
import hashlib
import struct

import pytest

from ecu_studio.core import axis_refs as R
from ecu_studio.core.edit_guard import CLEARED, EditRefused, guarded, make_clearance
from ecu_studio.core.editing import plan_recipe, plan_surface_edit
from ecu_studio.core.model import BinaryImage, MapDefinition
from ecu_studio.core.versioning import apply_restore, make_snapshot, plan_restore
from ecu_studio.core.workflows import apply_batch

AXIS = [0, 500, 1000, 2000]
X = 0x900          # stored axis (4 points, 16 bit)


def image_with(*axes):
    data = bytearray(range(256)) * 16
    for at, values in axes:
        data[at:at + 2 * len(values)] = struct.pack(f'<{len(values)}H', *values)
    return BinaryImage(bytes(data))


def table(name, offset, x=None, source='heuristic', **kw):
    return MapDefinition(name=name, offset=offset, rows=4, cols=4, dtype='u8', source=source,
                         axis_x_offset=x, axes_x=list(AXIS), **kw)


def axis_table(name='Achse', at=X, source='heuristic'):
    return MapDefinition(name=name, offset=at, rows=1, cols=4, dtype='u16', source=source)


def setup(identity='unknown', extra=()):
    """Image with two tables reading the stored axis at X plus the axis object itself as an editable table."""
    if identity == 'unknown':          # a value-equal copy elsewhere: identity unknown
        image = image_with((X, AXIS), (0xA00, AXIS))
        maps = [table('A', 0x100, X), table('B', 0x200, X), table('C', 0x300, 0xA00)]
    elif identity == 'plausible':
        image = image_with((X, AXIS))
        maps = [table('A', 0x100, X), table('B', 0x200, X)]
    else:                              # 'sure': both users come from a definition
        image = image_with((X, AXIS))
        maps = [table('A', 0x100, X, 'a2l'), table('B', 0x200, X, 'a2l')]
    maps += [axis_table()] + list(extra)
    policy = guarded(image, lambda: maps)
    return image, maps, policy


def axis_bytes(image, value=777):
    return {X + 2: (image.byte(X + 2), value & 0xFF), X + 3: (image.byte(X + 3), value >> 8)}


def changes_of(edits):
    return [(p, b, a) for p, (b, a) in sorted(edits.items())]


def test_unknown_shared_axis_is_refused_and_a_second_confirmation_does_not_help():
    image, maps, policy = setup('unknown')
    edits = axis_bytes(image)
    approval, found = policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: True)
    assert approval is None and any(c.refused for c in found)
    with pytest.raises(EditRefused):
        image.commit(changes_of(edits))
    assert image.dirty_bytes == 0 and image.read(X, 8) == image.original[X:X + 8]


def test_plausible_shared_axis_needs_confirmation_and_writes_once_for_all_users():
    image, maps, policy = setup('plausible')
    edits = axis_bytes(image)
    assert policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: False)[0] is None
    with pytest.raises(EditRefused):
        image.commit(changes_of(edits))               # no approval: the axis belongs to two tables
    approval, found = policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: True)
    assert approval and [c.identity for c in found if c.kind == 'Achse'] == [R.PLAUSIBLE]
    assert image.commit(changes_of(edits), approval=approval)
    assert struct.unpack('<H', image.read(X + 2, 2))[0] == 777
    # the physical axis changed for every user; nothing was copied to other addresses
    assert image.dirty_bytes == 2


def test_definition_shared_axis_shows_physical_effect_on_all_users():
    from ecu_studio.core.edit_guard import confirmation_text
    image, maps, policy = setup('sure')
    seen = []
    approval, found = policy.approve(image, [maps[-1]], set(axis_bytes(image)), confirm=lambda f: seen.append(f) or True)
    text = confirmation_text(seen[0])
    assert approval and R.SURE in text and 'A' in text and 'B' in text
    assert 'physischer Speicherbereich' in text and 'nichts auf andere Adressen kopiert' in text


def test_axes_with_identical_raw_values_stay_two_objects_and_both_are_guarded():
    image, maps, policy = setup('unknown')
    objs = {o.offset: o for o in R.objects(maps, data=image.materialize())}
    assert objs[X].identity == R.UNKNOWN and objs[0xA00].identity == R.VALUE_EQUAL
    # editing the single-user copy needs a confirmation (it is a stored axis) but is not refused
    approval, found = policy.approve(image, [], {0xA02}, confirm=lambda f: True)
    assert approval and not any(c.refused for c in found)


def test_overlapping_tables_need_confirmation_and_unapproved_writes_are_refused():
    image, maps, policy = setup('plausible', extra=[table('Überlapp', 0x108)])
    pos = {0x10A}
    with pytest.raises(EditRefused):
        image.write(0x10A, b'\x55')                   # hex-editor path without approval
    approval, found = policy.approve(image, [maps[0]], pos, confirm=lambda f: True)
    assert approval and [c.tables for c in found] == [('Überlapp',)]
    image.write(0x10A, b'\x55', approval=approval)
    assert image.byte(0x10A) == 0x55


def test_free_bytes_outside_every_object_need_no_approval():
    image, maps, policy = setup('plausible')
    image.write(0xF00, b'\x01')
    assert image.byte(0xF00) == 1


def test_manipulated_axis_reference_after_approval_is_stale():
    image, maps, policy = setup('plausible')
    edits = axis_bytes(image)
    approval, _ = policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: True)
    maps.append(table('Neu', 0x400, X))               # a new user appears between preview and write
    with pytest.raises(EditRefused):
        image.commit(changes_of(edits), approval=approval)
    maps.pop()
    maps[0].axis_x_offset = 0xA00                     # or a reference is redirected
    with pytest.raises(EditRefused):
        image.commit(changes_of(edits), approval=approval)
    assert image.dirty_bytes == 0


def test_wrong_width_and_out_of_range_values_are_rejected_before_writing():
    image, maps, policy = setup('plausible')
    approval, _ = policy.approve(image, [maps[0]], {0x100}, confirm=lambda f: True)
    with pytest.raises(ValueError):
        image.write_physical(maps[0], 0, 0, 300, approval=approval)     # u8 cannot hold 300
    with pytest.raises(ValueError):
        image.write_physical(maps[0], 0, 0, float('nan'), approval=approval)
    assert image.dirty_bytes == 0


def test_writes_outside_the_image_and_partly_invalid_transactions_change_nothing():
    image, maps, policy = setup('plausible')
    with pytest.raises(ValueError):
        image.write(image.size - 1, b'\x00\x00')
    approval, _ = policy.approve(image, [maps[0]], {0x100, 0x101}, confirm=lambda f: True)
    with pytest.raises(ValueError):
        image.commit([(0x100, image.byte(0x100), 9), (image.size, 0, 1)], approval=approval)
    with pytest.raises(ValueError):                   # a stale 'before' byte in one entry
        image.commit([(0x100, image.byte(0x100), 9), (0x101, image.byte(0x101) ^ 1, 9)], approval=approval)
    assert image.dirty_bytes == 0


def test_transaction_with_one_refused_part_writes_nothing():
    image, maps, policy = setup('unknown')
    own = {0x100, 0x101}
    approval, _ = policy.approve(image, [maps[0]], own, confirm=lambda f: True)
    mixed = [(0x100, image.byte(0x100), 1), (X + 2, image.byte(X + 2), 1)]
    with pytest.raises(EditRefused):
        image.commit(mixed, approval=approval)        # the axis byte is not covered and is refused anyway
    assert image.dirty_bytes == 0


def test_stale_approval_after_another_edit_or_for_other_positions():
    image, maps, policy = setup('plausible')
    approval, _ = policy.approve(image, [maps[0]], {0x100}, confirm=lambda f: True)
    image.write_physical(maps[0], 0, 0, 5, approval=approval)
    with pytest.raises(EditRefused):                  # revision moved on: approval used up
        image.write_physical(maps[0], 0, 0, 6, approval=approval)
    fresh, _ = policy.approve(image, [maps[0]], {0x100}, confirm=lambda f: True)
    with pytest.raises(EditRefused):                  # approval for A, bytes of B
        image.write_physical(maps[1], 0, 0, 6, approval=fresh)
    assert image.byte(0x100) == 5 and image.byte(0x200) == image.original[0x200]


def test_cancelled_confirmation_and_errors_leave_a_working_history():
    image, maps, policy = setup('plausible')
    assert policy.approve(image, [maps[-1]], set(axis_bytes(image)), confirm=lambda f: False)[0] is None
    with pytest.raises(EditRefused):
        image.commit(changes_of(axis_bytes(image)))
    ok, _ = policy.approve(image, [maps[0]], {0x100}, confirm=lambda f: True)
    image.write_physical(maps[0], 0, 0, 42, approval=ok)
    assert image.undo() and image.byte(0x100) == image.original[0x100]
    assert image.redo() and image.byte(0x100) == 42
    assert image.original[0x100] == 0


def test_undo_redo_of_an_approved_shared_axis_edit_is_exact():
    image, maps, policy = setup('plausible')
    edits = axis_bytes(image, 1234)
    approval, _ = policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: True)
    image.commit(changes_of(edits), approval=approval)
    after = image.materialize()
    assert image.undo() and image.materialize() == image.original and image.dirty_bytes == 0
    assert image.redo() and image.materialize() == after
    assert hashlib.sha256(image.original).hexdigest() == image.digest


def test_batch_restore_and_unapproved_alternative_paths_are_refused():
    image, maps, policy = setup('plausible')
    maps[0].verified = True
    preview = plan_surface_edit(image, maps[0], 'set', cells=[[0, 0]], amount=7)
    with pytest.raises(EditRefused):
        apply_batch(image, preview)                   # batch / area path without approval
    approval, _ = policy.approve(image, [maps[0]], {0x100}, confirm=lambda f: True)
    apply_batch(image, preview, approval=approval)
    snap = make_snapshot(image, 'nach Bearbeitung')
    image.undo()
    restore = plan_restore(image, snap, maps[0])
    with pytest.raises(EditRefused):
        apply_restore(image, restore)                 # version restore without approval
    ok, _ = policy.approve(image, [maps[0]], {p for p, _, _ in restore.changes}, confirm=lambda f: True)
    assert apply_restore(image, restore, approval=ok) and image.byte(0x100) == 7


def test_recipe_with_contradictory_steps_is_refused():
    image, maps, policy = setup('plausible')
    maps[0].verified = True
    recipe = {'schema': 1, 'source_sha256': image.digest, 'operations': [
        {'map': 'A', 'mode': 'set', 'cells': [[0, 0]], 'amount': 10},
        {'map': 'A', 'mode': 'set', 'cells': [[0, 0]], 'amount': 20}]}
    with pytest.raises(ValueError, match='widersprüchlich'):
        plan_recipe(image, maps, recipe)


def test_faulty_definitions_and_project_patches_are_rejected():
    image, maps, policy = setup('plausible')
    with pytest.raises(ValueError):
        MapDefinition(name='zu groß', offset=image.size - 2, rows=4, cols=4, dtype='u16').validate(image.size)
    with pytest.raises(ValueError):
        image.restore_patches([[image.size + 1, 1]])
    with pytest.raises(ValueError):
        image.restore_patches([[0, 300]])
    assert image.dirty_bytes == 0


def test_clearance_needs_matching_statements_and_lifts_only_the_refusal():
    image, maps, policy = setup('unknown')
    common = dict(offset=X, points=4, width=2, tables=['A', 'B', 'Achse'][:2])
    origin = 'Adress- und Layoutprüfung im Programmcode: beide Aufrufe laden dieselbe Achse'
    for bad in (dict(common, points=5), dict(common, width=3), dict(common, tables=['A']),
                dict(common, offset=X + 2), dict(common, origin='ok')):
        bad.setdefault('origin', origin)
        with pytest.raises(ValueError):
            policy.add_clearance(image, **bad)
    assert policy.clearances == []
    policy.add_clearance(image, **common, origin=origin)
    edits = axis_bytes(image)
    assert policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: False)[0] is None   # still confirmed
    approval, found = policy.approve(image, [maps[-1]], set(edits), confirm=lambda f: True)
    assert approval and any(c.identity == CLEARED for c in found)
    image.commit(changes_of(edits), approval=approval)
    # an edit of the axis keeps the clearance; a changed layout of its users drops it
    assert policy.conflicts(image, [maps[-1]], set(edits)) and policy.clearances
    image.undo()                                      # the value-equal copy exists again: identity unknown
    maps[1].rows = 2
    found = policy.conflicts(image, [maps[-1]], {X + 4})
    assert policy.clearances == [] and any(c.refused for c in found)


def test_clearance_is_bound_to_the_firmware():
    image, maps, policy = setup('unknown')
    clearance = make_clearance(maps, image.materialize(), image.digest, offset=X, points=4, width=2,
                               tables=['A', 'B'], origin='geprüfte A2L desselben Softwarestands, AXIS_PTS')
    other = BinaryImage(image.original[:-1] + b'\x00')
    assert clearance.holds(image.digest, maps) and not clearance.holds(other.digest, maps)
