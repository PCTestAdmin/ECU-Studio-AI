"""Firmware guard: hooks and rules, exercised in throwaway git repositories with synthetic data only."""
import base64
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from ecu_studio.tools import firmware_guard as guard

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which('git')
pytestmark = pytest.mark.skipif(GIT is None, reason='git not installed')


def synthetic(size, seed=1, marker=b''):
    """Random bytes standing in for a firmware image (never real firmware)."""
    data = bytearray(random.Random(seed).randbytes(size))
    data[0x100:0x100 + len(marker)] = marker
    return bytes(data)


def run(repo, *args, check=True, stdin=None):
    env = dict(os.environ, ECU_STUDIO_GUARD_PYTHON=sys.executable, GIT_TERMINAL_PROMPT='0')
    env.pop('ECU_STUDIO_LOCAL_DATA', None)
    result = subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                             '-c', 'core.autocrlf=false', '-c', 'init.defaultBranch=main', *args],
                            cwd=repo, capture_output=True, text=True, env=env, input=stdin)
    if check and result.returncode:
        raise AssertionError(f'git {args} failed:\n{result.stdout}\n{result.stderr}')
    return result


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / 'repo'
    tools = repo / 'src' / 'ecu_studio' / 'tools'
    tools.mkdir(parents=True)
    shutil.copy(ROOT / 'src' / 'ecu_studio' / 'tools' / 'firmware_guard.py', tools)
    shutil.copytree(ROOT / '.githooks', repo / '.githooks')
    (repo / 'README.md').write_text('demo\n')
    run(repo, 'init', '-q')
    run(repo, 'config', 'core.hooksPath', '.githooks')
    run(repo, 'add', '.')
    run(repo, 'commit', '-q', '-m', 'init')
    return repo


def write(repo, rel, data):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def commit(repo, *paths, message='change', force=False):
    run(repo, 'add', *(['-f'] if force else []), *paths)
    return run(repo, 'commit', '-q', '-m', message, check=False)


# ----------------------------------------------------------------------------------------- pre-commit hook


def test_firmware_file_name_is_blocked(repo):
    write(repo, 'dump/ecu.bin', synthetic(4096))
    result = commit(repo, 'dump/ecu.bin', force=True)
    assert result.returncode != 0
    assert 'extension' in result.stderr and 'ecu.bin' in result.stderr
    assert run(repo, 'rev-list', '--count', 'HEAD').stdout.strip() == '1'


@pytest.mark.parametrize('name', ['notes.txt', 'data.json', 'logo.png', 'test_maps.py'])
def test_renamed_firmware_is_detected_by_content(repo, name):
    write(repo, name, synthetic(65536, marker=b'EDC17C64 1037'))
    result = commit(repo, name)
    assert result.returncode != 0
    assert 'binary content' in result.stderr or 'not a PNG' in result.stderr


def test_public_source_commits_normally(repo):
    write(repo, 'src/app.py', 'def add(a, b):\n    return a + b\n')
    write(repo, 'docs/guide.md', '# Guide\nSHA-256 ' + 'ab' * 32 + '\n')
    result = commit(repo, 'src/app.py', 'docs/guide.md')
    assert result.returncode == 0, result.stderr
    assert 'staged changes OK' in result.stdout + result.stderr


def test_embedded_hex_payload_in_a_test_file_is_blocked(repo):
    payload = synthetic(4096).hex()
    lines = '\n'.join(f'    "{payload[i:i + 64]}"' for i in range(0, len(payload), 64))
    write(repo, 'tests/test_dump.py', f'IMAGE = bytes.fromhex(\n{lines}\n)\n')
    result = commit(repo, 'tests/test_dump.py')
    assert result.returncode != 0 and 'payload' in result.stderr


def test_embedded_base64_and_byte_lists_are_blocked(repo):
    b64 = base64.b64encode(synthetic(2048)).decode()
    write(repo, 'data/blob.json', json.dumps({'image': b64}))
    write(repo, 'src/table.c', 'const unsigned char t[] = {' + ', '.join(f'0x{b:02X}' for b in synthetic(1500)) + '};\n')
    result = commit(repo, 'data/blob.json', 'src/table.c')
    assert result.returncode != 0
    assert 'base64 payload' in result.stderr and 'hex payload' in result.stderr


def test_memory_image_records_in_text_are_blocked(repo):
    data = synthetic(256)
    lines = [f':10{i * 16:04X}00{data[i * 16:i * 16 + 16].hex().upper()}00' for i in range(16)]
    write(repo, 'notes/flash.txt', '\n'.join(lines) + '\n')
    result = commit(repo, 'notes/flash.txt')
    assert result.returncode != 0 and 'Intel HEX' in result.stderr


def test_large_files_are_blocked(repo):
    write(repo, 'docs/huge.md', 'line of text\n' * 100_000)
    result = commit(repo, 'docs/huge.md')
    assert result.returncode != 0 and 'size' in result.stderr


def test_private_folder_is_blocked_even_for_text(repo):
    write(repo, 'references/a2l/notes.md', 'calibration notes\n')
    result = commit(repo, 'references/a2l/notes.md', force=True)
    assert result.returncode != 0 and 'private-dir' in result.stderr


def test_selective_staging_checks_the_index_not_the_working_tree(repo):
    path = write(repo, 'src/mod.py', 'X = 1\n')
    commit(repo, 'src/mod.py')
    # Clean content staged, firmware-like bytes only in the working tree: commit allowed.
    write(repo, 'src/mod.py', 'X = 2\n')
    run(repo, 'add', 'src/mod.py')
    path.write_bytes(synthetic(8192))
    assert run(repo, 'commit', '-q', '-m', 'ok', check=False).returncode == 0
    # Payload staged via the object database (as selective staging tools do), clean working tree: blocked.
    sha = run(repo, 'hash-object', '-w', '--stdin', stdin=f'X = "{synthetic(2048).hex()}"\n').stdout.strip()
    run(repo, 'update-index', '--cacheinfo', f'100644,{sha},src/mod.py')
    path.write_text('X = 3\n')
    result = run(repo, 'commit', '-q', '-m', 'bad', check=False)
    assert result.returncode != 0 and 'payload' in result.stderr


def test_allowlist_is_bound_to_path_and_content(repo):
    write(repo, 'examples/demo.bin', synthetic(512, seed=7))
    run(repo, 'add', '-f', 'examples/demo.bin')
    subprocess.run([sys.executable, '-I', str(repo / 'src/ecu_studio/tools/firmware_guard.py'), 'allow',
                    str(repo / 'examples/demo.bin')], cwd=repo, check=True, capture_output=True)
    run(repo, 'config', 'core.hooksPath', '.githooks')
    assert commit(repo, '.firmware-guard.json', 'examples/demo.bin', force=True).returncode == 0
    # Same file under a new name (rename) is no longer covered.
    run(repo, 'mv', 'examples/demo.bin', 'examples/other.bin')
    result = run(repo, 'commit', '-q', '-m', 'rename', check=False)
    assert result.returncode != 0 and 'other.bin' in result.stderr
    run(repo, 'mv', 'examples/other.bin', 'examples/demo.bin')
    # Same path with different bytes is not covered either.
    write(repo, 'examples/demo.bin', synthetic(512, seed=8))
    result = commit(repo, 'examples/demo.bin', force=True)
    assert result.returncode != 0 and 'content changed' in result.stderr


def _ids(value):
    return value if isinstance(value, str) and '.' in value else ''


def _chunk(kind, body):
    import zlib
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def _png(width=4, height=4, extra=(), pixels=None):
    """Minimal valid RGBA PNG (filter byte 0 per row), optional extra chunks before IEND."""
    import zlib
    raw = pixels if pixels is not None else b''.join(b'\x00' + b'\x10\x80\xff\xff' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + b''.join(extra) + _chunk(b'IDAT', zlib.compress(raw)) + _chunk(b'IEND', b''))


def _ico(*images):
    head = struct.pack('<HHH', 0, 1, len(images))
    offset, entries = 6 + 16 * len(images), b''
    for image in images:
        if image.startswith(b'\x89PNG'):                              # the directory lists each image's size
            width, height = struct.unpack('>II', image[16:24])
        else:
            width, double_height = struct.unpack('<ii', image[4:12])
            height = double_height // 2
        entries += struct.pack('<BBBBHHII', width % 256, height % 256, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
    return head + entries + b''.join(images)


def test_media_files_must_be_real_images(repo):
    write(repo, 'docs/ok.png', _png())
    write(repo, 'docs/icon.ico', _ico(_png()))
    assert commit(repo, 'docs/ok.png', 'docs/icon.ico').returncode == 0
    write(repo, 'docs/smuggle.png', _png() + synthetic(4096))
    result = commit(repo, 'docs/smuggle.png')
    assert result.returncode != 0 and 'appended after the image end' in result.stderr


GIF_OK = b'GIF89a\x01\x00\x01\x00\x00\x00\x00' + b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00' + b';'


@pytest.mark.parametrize('name, data, reason', [
    ('header-only.ico', b'\x00\x00\x01\x00' + synthetic(8192), 'ICO'),
    ('padded.ico', _ico(_png()) + synthetic(4096), 'appended after the last ICO image'),
    ('gap.ico', _ico(_png())[:22] + synthetic(2048) + _png(), 'ICO'),
    ('private-chunk.png', _png(extra=[_chunk(b'fwDt', synthetic(4096))]), 'unknown PNG chunk'),
    ('big-text.png', _png(extra=[_chunk(b'tEXt', b'k\x00' + b'x' * 70000)]), 'PNG metadata'),
    ('extra-pixels.png', _png(pixels=b''.join(b'\x00' + b'\x10\x80\xff\xff' * 4 for _ in range(4)) + synthetic(4096)),
     'header needs'),
    ('bad-crc.png', _png()[:-4] + b'\x00\x00\x00\x00', 'checksum'),
    ('ends-with-semicolon.gif', GIF_OK[:-1] + synthetic(4096) + b';', 'GIF'),
    ('riff.webp', b'RIFF' + struct.pack('<I', 4) + b'WEBP' + synthetic(4096), 'RIFF length'),
], ids=_ids)
def test_payloads_disguised_as_images_are_blocked(name, data, reason):
    findings = guard.scan_blob(f'docs/{name}', data, guard.Config.load(None))
    assert findings and findings[0].rule == 'media' and reason in findings[0].detail, findings


def test_real_images_pass_the_structural_check():
    assert guard.scan_blob('a.png', _png(), guard.Config.load(None)) == []
    assert guard.scan_blob('a.gif', GIF_OK, guard.Config.load(None)) == []
    assert guard.scan_blob('a.ico', _ico(_png(), _png(8, 8)), guard.Config.load(None)) == []


def test_local_data_root_must_not_be_named_or_inside_the_repo(repo, monkeypatch):
    write(repo, 'docs/howto.md', 'Run the benchmark on D:/ECU-Studio-Local/firmware/ecu\n')
    run(repo, 'add', 'docs/howto.md')
    git = guard.Git(repo)
    try:
        monkeypatch.setenv('ECU_STUDIO_LOCAL_DATA', r'D:\ECU-Studio-Local')
        assert any(f.rule == 'local-path' for f in guard.check_staged(git))
        monkeypatch.setenv('ECU_STUDIO_LOCAL_DATA', str(repo / 'local'))
        assert any('inside the repository' in f.detail for f in guard.check_staged(git))
    finally:
        git.close()


# ------------------------------------------------------------------------------- already tracked files, push


def bare_remote(repo):
    remote = repo.parent / 'remote.git'
    run(repo.parent, 'init', '-q', '--bare', str(remote))
    run(repo, 'remote', 'add', 'origin', str(remote))
    return remote


def test_already_tracked_firmware_is_found_by_the_tree_check(repo):
    # Simulates a file committed before the guard existed (hook bypassed on purpose in this test repo).
    write(repo, 'old/cal.dat', synthetic(4096, marker=b'MED17'))
    run(repo, 'add', 'old/cal.dat')
    run(repo, 'commit', '-q', '--no-verify', '-m', 'legacy')
    git = guard.Git(repo)
    try:
        findings = guard.check_tree(git, 'HEAD')
    finally:
        git.close()
    assert [f.path for f in findings] == ['old/cal.dat']
    assert 'MED17' in findings[0].detail


def test_push_is_blocked_even_after_a_deletion_commit(repo):
    bare_remote(repo)
    run(repo, 'push', '-q', 'origin', 'main')
    write(repo, 'tmp/read.ori', synthetic(4096))
    run(repo, 'add', '-f', 'tmp/read.ori')
    run(repo, 'commit', '-q', '--no-verify', '-m', 'oops')
    run(repo, 'rm', '-q', 'tmp/read.ori')
    run(repo, 'commit', '-q', '-m', 'remove it again')
    result = run(repo, 'push', 'origin', 'main', check=False)
    assert result.returncode != 0
    assert 'read.ori' in result.stderr and 'Do NOT fix this with a commit that deletes' in result.stderr
    assert run(repo, 'ls-remote', 'origin', 'main').stdout.split()[0] != run(repo, 'rev-parse', 'HEAD').stdout.strip()


def test_push_checks_tracked_files_and_commit_messages(repo):
    bare_remote(repo)
    write(repo, 'legacy.dat', synthetic(2048))
    run(repo, 'add', 'legacy.dat')
    run(repo, 'commit', '-q', '--no-verify', '-m', 'legacy')
    run(repo, 'push', '-q', '--no-verify', 'origin', 'main')
    # New commit does not touch legacy.dat, but the pushed tree still contains it.
    write(repo, 'src/a.py', 'A = 1\n')
    commit(repo, 'src/a.py')
    result = run(repo, 'push', 'origin', 'main', check=False)
    assert result.returncode != 0 and 'legacy.dat' in result.stderr
    run(repo, 'rm', '-q', 'legacy.dat')
    run(repo, 'commit', '-q', '-m', 'drop legacy file')
    run(repo, 'commit', '-q', '--allow-empty', '--no-verify', '-m',
        'notes\n\n' + base64.b64encode(synthetic(1200)).decode())
    result = run(repo, 'push', 'origin', 'main', check=False)
    assert result.returncode != 0 and '(commit message)' in result.stderr


def test_clean_push_goes_through_and_new_branches_are_checked(repo):
    bare_remote(repo)
    run(repo, 'push', '-q', 'origin', 'main')
    write(repo, 'src/b.py', 'B = 2\n')
    commit(repo, 'src/b.py')
    result = run(repo, 'push', 'origin', 'main', check=False)
    assert result.returncode == 0, result.stderr
    assert 'outgoing commits OK' in result.stdout + result.stderr
    run(repo, 'switch', '-q', '-c', 'topic')
    write(repo, 'x/img.bin', synthetic(1024))
    run(repo, 'add', '-f', 'x/img.bin')
    run(repo, 'commit', '-q', '--no-verify', '-m', 'binary')
    assert run(repo, 'push', 'origin', 'topic', check=False).returncode != 0


# ------------------------------------------------------------------------------------------- unit checks


def test_scan_blob_keeps_hashes_and_ordinary_code_clean():
    config = guard.Config.load(None)
    text = ('digest = "' + 'f' * 64 + '"\nsha1 = "' + 'a' * 40 + '"\n' + 'value = 0x1234\n' * 50).encode()
    assert guard.scan_blob('src/x.py', text, config) == []
    assert guard.scan_blob('docs/a.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', config) == []


def test_reports_never_contain_file_content(repo):
    secret = 'ZZSECRETZZ' * 300
    write(repo, 'leak.bin', secret.encode())
    result = commit(repo, 'leak.bin', force=True)
    assert result.returncode != 0 and 'ZZSECRETZZ' not in result.stderr + result.stdout


def test_this_repository_tree_passes():
    if not (ROOT / '.git').exists():
        pytest.skip('not a git checkout')
    git = guard.Git(ROOT)
    try:
        if subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', f'HEAD:{guard.CONFIG}'],
                          capture_output=True).returncode:
            pytest.skip('guard config not committed in HEAD yet')
        assert guard.check_tree(git, 'HEAD') == []
    finally:
        git.close()


@pytest.mark.parametrize('style', ['escapes', 'hexdump', 'tokens'])
def test_payloads_split_over_many_short_lines_are_joined(style):
    data = synthetic(1600)
    rows = [data[i:i + 16] for i in range(0, len(data), 16)]
    if style == 'escapes':
        text = 'IMG = (\n' + '\n'.join('    b"' + ''.join(f'\\x{b:02x}' for b in row) + '"' for row in rows) + '\n)\n'
    elif style == 'hexdump':
        text = '\n'.join(' '.join(f'{b:02x}' for b in row) for row in rows) + '\n'
    else:
        text = '[\n' + '\n'.join('  ' + ', '.join(f'0x{b:02X}' for b in row) + ',' for row in rows) + '\n]\n'
    assert guard.payloads(text.encode()), style


# ------------------------------------------------------------------------------- image structure in depth
# Everything here is synthetic: images built byte by byte or by Qt, payloads from synthetic().


def _png_raw(raw, width=4, height=4, depth=8, color=6, interlace=0, before=(), after=(), idat=None, split=1):
    """PNG around a given filtered pixel stream; chunks before and after the image data; IDAT split in parts."""
    stream = idat if idat is not None else zlib.compress(raw)
    step = -(-len(stream) // split)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, interlace))
            + b''.join(before) + b''.join(_chunk(b'IDAT', stream[i:i + step]) for i in range(0, len(stream), step))
            + b''.join(after) + _chunk(b'IEND', b''))


RGBA_4x4 = b''.join(b'\x00' + b'\x10\x80\xff\xff' * 4 for _ in range(4))
STREAM_4x4 = zlib.compress(RGBA_4x4)


def _media(name, data):
    findings = guard.scan_blob(f'docs/{name}', data, guard.Config.load(None))
    assert all(f.rule == 'media' for f in findings), findings
    return findings[0].detail if findings else ''


def test_png_bytes_after_the_zlib_stream_are_rejected():
    """Regression: zlib.decompress() ignored bytes after the end of the stream, so 5000 extra bytes in a correctly
    CRC'd IDAT chunk passed on 1.18.1 (reproduced before the fix)."""
    data = _png_raw(None, idat=STREAM_4x4 + synthetic(5000))
    assert '5000 bytes after the end of the compressed stream' in guard._png_problem(data)
    assert _media('a.png', data)


@pytest.mark.parametrize('name, data', [
    ('palette.png', _png_raw(b'\x00\x01\x23' * 4, depth=4, color=3, before=[_chunk(b'PLTE', bytes(range(48))),
                                                                          _chunk(b'tRNS', b'\x00\x80')])),
    ('gray16.png', _png_raw(b'\x00' + b'\x12\x34' * 4 + b'\x02' + b'\x00\x01' * 4, height=2, depth=16, color=0)),
    ('gray1.png', _png_raw(b'\x00\xa0' * 4, depth=1, color=0)),
    ('interlaced.png', _png_raw(bytes(5 + 5 + 9 + 9 * 2 + 17 * 2 + 17 * 4 + 33 * 4), width=8, height=8,
                                interlace=1)),
    ('split-idat.png', _png_raw(RGBA_4x4, split=4)),
    ('stored.png', _png_raw(None, idat=zlib.compress(RGBA_4x4, 0))),
    ('metadata.png', _png_raw(RGBA_4x4, before=[
        _chunk(b'gAMA', struct.pack('>I', 45455)), _chunk(b'sRGB', b'\x00'), _chunk(b'pHYs', bytes(9)),
        _chunk(b'eXIf', b'MM\x00*' + bytes(60))], after=[
        _chunk(b'tEXt', b'Software\x00ECU Studio AI'), _chunk(b'zTXt', b'Comment\x00\x00' + zlib.compress(b'map view ' * 50)),
        _chunk(b'iTXt', b'Title\x00\x00\x00de\x00Titel\x00Kennfeld \xc3\xbcbersicht'), _chunk(b'tIME', bytes(7))])),
], ids=_ids)
def test_valid_png_variants_pass(name, data):
    assert _media(name, data) == ''


IDAT_SPLIT_BY_TEXT = (_png_raw(RGBA_4x4)[:33] + _chunk(b'IDAT', STREAM_4x4[:6]) + _chunk(b'tEXt', b'k\x00v')
                      + _chunk(b'IDAT', STREAM_4x4[6:]) + _chunk(b'IEND', b''))


@pytest.mark.parametrize('name, data, reason', [
    ('stream-tail.png', _png_raw(None, idat=STREAM_4x4 + b'\x00' * 7), 'after the end of the compressed'),
    ('stream-cut.png', _png_raw(None, idat=STREAM_4x4[:-6]), 'before the compressed stream is complete'),
    ('not-zlib.png', _png_raw(None, idat=synthetic(64)), 'not valid zlib'),
    ('short-pixels.png', _png_raw(RGBA_4x4[:-17]), 'the header needs 68'),
    ('bad-filter.png', _png_raw(b'\x07' + RGBA_4x4[1:]), 'row filter'),
    ('wider.png', _png_raw(RGBA_4x4, width=5), 'the header needs'),
    ('zero-width.png', _png_raw(RGBA_4x4, width=0), 'header is invalid'),
    ('huge-height.png', _png_raw(RGBA_4x4, height=0x80000000), 'header is invalid'),
    ('depth-3.png', _png_raw(RGBA_4x4, depth=3), 'header is invalid'),
    ('rgb-1bit.png', _png_raw(RGBA_4x4, depth=1, color=2), 'header is invalid'),
    ('no-palette.png', _png_raw(b'\x00\x00' * 4, width=1, color=3), 'incomplete'),
    ('idat-split-by-text.png', IDAT_SPLIT_BY_TEXT, 'out of order'),
    ('plte-after-idat.png', _png_raw(RGBA_4x4, after=[_chunk(b'PLTE', bytes(6))]), 'out of order'),
    ('gama-after-idat.png', _png_raw(RGBA_4x4, after=[_chunk(b'gAMA', bytes(4))]), 'out of order'),
    ('two-ihdr.png', _png_raw(RGBA_4x4, before=[_chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 6, 0, 0, 0))]),
     'out of order'),
    ('two-time.png', _png_raw(RGBA_4x4, after=[_chunk(b'tIME', bytes(7))] * 2), 'out of order'),
    ('big-gama.png', _png_raw(RGBA_4x4, before=[_chunk(b'gAMA', synthetic(4000))]), 'wrong size'),
    ('after-iend.png', _png_raw(RGBA_4x4) + b'\x00', 'appended after the image end'),
    ('ztxt-binary.png', _png_raw(RGBA_4x4, after=[_chunk(b'zTXt', b'k\x00\x00' + zlib.compress(synthetic(30000)))]),
     'binary data in a text field'),
    ('ztxt-tail.png', _png_raw(RGBA_4x4, after=[_chunk(b'zTXt', b'k\x00\x00' + zlib.compress(b'note') + synthetic(900))]),
     'after the end of the compressed'),
    ('text-base64.png', _png_raw(RGBA_4x4, after=[_chunk(b'tEXt', b'k\x00' + base64.b64encode(synthetic(3000)))]),
     'base64 payload'),
    ('text-hex.png', _png_raw(RGBA_4x4, after=[_chunk(b'iTXt', b'k\x00\x00\x00\x00\x00' + synthetic(2000).hex().encode())]),
     'hex payload'),
    ('big-exif.png', _png_raw(RGBA_4x4, after=[_chunk(b'eXIf', b'MM\x00*' + synthetic(20000))]), 'binary PNG metadata'),
    ('fake-exif.png', _png_raw(RGBA_4x4, after=[_chunk(b'eXIf', synthetic(500))]), 'not EXIF'),
    ('fake-icc.png', _png_raw(RGBA_4x4, before=[_chunk(b'iCCP', b'icc\x00\x00' + zlib.compress(synthetic(900)))]),
     'not an ICC color profile'),
    ('many-texts.png', _png_raw(RGBA_4x4, after=[_chunk(b'tEXt', b'k\x00' + b'note ' * 3000)] * 5), 'PNG metadata'),
], ids=_ids)
def test_manipulated_pngs_are_rejected(name, data, reason):
    assert reason in _media(name, data)


def test_png_decompression_bombs_stay_cheap():
    import time
    import tracemalloc
    bomb = zlib.compress(b'\x00' * 200_000_000, 9)              # 200 MB of output from about 200 KB
    cases = [(_png_raw(None, idat=bomb), 'more than 68 bytes'),
             (_png_raw(None, idat=bomb, width=4000, height=4000), 'more than 64004000 bytes'),
             (_png_raw(None, idat=bomb, width=50000, height=50000), 'too large to verify')]
    for data, reason in cases:
        tracemalloc.start()
        started = time.perf_counter()
        problem = guard._png_problem(data)
        seconds, peak = time.perf_counter() - started, tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert reason in problem
        assert peak < 2 * len(data) + 4 * guard.INFLATE_STEP + (1 << 20), peak     # input + a few output steps
        assert seconds < 10


@pytest.mark.parametrize('kind', ['png', 'gif', 'ico', 'jpg', 'webp'])
def test_truncated_and_mutated_images_never_crash(kind):
    sample = {'png': _png_raw(RGBA_4x4, after=[_chunk(b'zTXt', b'k\x00\x00' + zlib.compress(b'text'))]),
              'gif': _gif([(3, 2, [1, 2, 3, 4, 5, 6])], extensions=LOOP), 'ico': _ico(_png()), 'jpg': _jpeg(),
              'webp': _webp(b'\x2f' + bytes(8))}[kind]
    for cut in range(len(sample)):
        assert _media(f'cut.{kind}', sample[:cut])                       # every truncation is reported
    rng = random.Random(5)
    for _ in range(400):                                                   # random corruption: a verdict, never a crash
        data = bytearray(sample)
        for _ in range(rng.randint(1, 4)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        assert isinstance(guard._media_problem(kind, bytes(data)), str)


def test_text_file_named_like_an_image_is_rejected():
    assert 'not a PNG' in _media('notes.png', b'just some text\n' * 100)
    assert 'not a GIF' in _media('notes.gif', b'just some text\n' * 100)


# GIF frames are LZW-encoded here with literal codes only, plus a clear code before the code size would grow.
def _lzw(pixels, min_size=8):
    clear, size = 1 << min_size, min_size + 1
    codes = [clear]
    for i, pixel in enumerate(pixels):
        if i and i % ((1 << size) - clear - 3) == 0:
            codes.append(clear)
        codes.append(pixel)
    codes.append(clear + 1)
    out, acc, bits = bytearray(), 0, 0
    for code in codes:
        acc |= code << bits
        bits += size
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8
    return bytes(out) + (bytes([acc]) if bits else b'')


def _sub_blocks(data):
    return b''.join(bytes([len(data[i:i + 255])]) + data[i:i + 255] for i in range(0, len(data), 255)) + b'\x00'


def _gif(frames, extensions=b'', lzw_tail=b''):
    width, height = max(f[0] for f in frames), max(f[1] for f in frames)
    out = b'GIF89a' + struct.pack('<HHBBB', width, height, 0xF7, 0, 0) + bytes(range(256)) * 3 + extensions
    for w, h, pixels in frames:
        out += (b'\x21\xf9\x04\x00\x0a\x00\x00\x00' + b'\x2c' + struct.pack('<HHHHB', 0, 0, w, h, 0) + b'\x08'
                + _sub_blocks(_lzw(pixels) + lzw_tail))
    return out + b';'


LOOP = b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'


def test_valid_gifs_pass():
    pixels = [i * 7 % 256 for i in range(40 * 30)]
    assert _media('a.gif', _gif([(40, 30, pixels), (10, 10, pixels[:100])], extensions=LOOP)) == ''
    assert _media('b.gif', _gif([(2, 2, [0, 1, 2, 3])], extensions=b'\x21\xfe' + _sub_blocks(b'made by a test'))) == ''
    assert _media('c.gif', GIF_OK) == ''


@pytest.mark.parametrize('name, data, reason', [
    ('after-end-code.gif', _gif([(4, 4, list(range(16)))], lzw_tail=synthetic(5000)), 'after the LZW end code'),
    ('short-frame.gif', _gif([(4, 4, list(range(15)))]), '15 of 16 pixels'),
    ('more-pixels.gif', _gif([(4, 4, list(range(40)))]), 'more than the 16 pixels'),
    ('unknown-extension.gif', _gif([(1, 1, [0])], extensions=b'\x21\x42' + _sub_blocks(synthetic(3000))),
     'unknown GIF extension'),
    ('binary-comment.gif', _gif([(1, 1, [0])], extensions=b'\x21\xfe' + _sub_blocks(synthetic(3000))), 'binary data'),
    ('base64-comment.gif', _gif([(1, 1, [0])], extensions=b'\x21\xfe' + _sub_blocks(base64.b64encode(synthetic(3000)))),
     'base64 payload'),
    ('app-data.gif', _gif([(1, 1, [0])], extensions=b'\x21\xff\x0bXMP DataXMP' + _sub_blocks(synthetic(20000))),
     'binary GIF application data'),
    ('loop-padding.gif', _gif([(1, 1, [0])], extensions=b'\x21\xff\x0bNETSCAPE2.0' + _sub_blocks(synthetic(900))),
     'loop block'),
    ('after-trailer.gif', _gif([(1, 1, [0])]) + b'\x00', 'appended after the image end'),
], ids=_ids)
def test_manipulated_gifs_are_rejected(name, data, reason):
    assert reason in _media(name, data)


# JPEG and WEBP are walked structurally, but their pixel streams are not decoded: even a clean file needs review.
def _jpeg(scan=b'\x12\x34', after_scan=b'', tail=b'', head=b''):
    sof = b'\xff\xc0' + struct.pack('>HBHHB', 11, 8, 1, 1, 1) + b'\x01\x11\x00'
    sos = b'\xff\xda' + struct.pack('>HB', 8, 1) + b'\x01\x00\x00\x3f\x00'
    return b'\xff\xd8' + head + sof + sos + scan + after_scan + b'\xff\xd9' + tail


def _webp(payload, extra=b''):
    body = b'WEBP' + b'VP8L' + struct.pack('<I', len(payload)) + payload + b'\x00' * (len(payload) & 1) + extra
    return b'RIFF' + struct.pack('<I', len(body)) + body


@pytest.mark.parametrize('name, data, reason', [
    ('clean.jpg', _jpeg(), 'not decoded by the guard'),
    ('hidden-in-scan.jpg', _jpeg(scan=b'\x12\x34' + synthetic(5000).replace(b'\xff', b'\xff\x00')),
     'not decoded by the guard'),
    ('after-eoi.jpg', _jpeg(tail=b'\x00' * 3), 'appended after the image end'),
    ('app-after-scan.jpg', _jpeg(after_scan=(b'\xff\xe5' + struct.pack('>H', 40002) + synthetic(40000)) * 2),
     'JPEG metadata'),
    ('binary-comment.jpg', _jpeg(head=b'\xff\xfe' + struct.pack('>H', 3002) + synthetic(3000)), 'binary data'),
    ('odd-marker.jpg', _jpeg(head=b'\xff\xf3' + struct.pack('>H', 4) + b'ab'), 'unexpected JPEG marker'),
    ('overrun.jpg', _jpeg(head=b'\xff\xe1' + struct.pack('>H', 60000) + b'Exif'), 'runs past the end'),
    ('no-eoi.jpg', _jpeg()[:-2], 'without end marker'),
    ('clean.webp', _webp(b'\x2f' + bytes(8)), 'not decoded by the guard'),
    ('vp8l-tail.webp', _webp(b'\x2f' + bytes(8) + synthetic(5000)), 'not decoded by the guard'),
    ('exif.webp', _webp(b'\x2f' + bytes(8), extra=b'EXIF' + struct.pack('<I', 20000) + synthetic(20000)),
     'WEBP metadata'),
    ('private.webp', _webp(b'\x2f' + bytes(8), extra=b'FWDT' + struct.pack('<I', 64) + synthetic(64)),
     'unknown WEBP chunk'),
], ids=_ids)
def test_jpeg_and_webp_need_review(name, data, reason):
    assert reason in _media(name, data)


def test_reviewed_jpeg_and_webp_can_be_allowlisted():
    for name, data in (('docs/photo.jpg', _jpeg()), ('docs/photo.webp', _webp(b'\x2f' + bytes(8)))):
        assert guard.scan_blob(name, data, guard.Config.load(None))
        config = guard.Config.load(json.dumps({'allow': {name: guard.sha256(data)}}))
        assert guard.scan_blob(name, data, config) == []


# ICO: PNG entries get the full PNG check and must match the directory; DIB entries must match their header.
def _dib(w=4, h=4, bits=32):
    header = struct.pack('<IiiHHIIiiII', 40, w, 2 * h, 1, bits, 0, 0, 0, 0, 0, 0)
    return header + bytes(h * (((w * bits + 31) // 32) * 4 + ((w + 31) // 32) * 4))


ICO_4x4_ENTRY = b'\x00\x00\x01\x00\x01\x00\x04\x04'       # ICO header and a directory entry that claims 4x4


@pytest.mark.parametrize('name, data, reason', [
    ('dib.ico', _ico(_dib()), ''),
    ('png-and-dib.ico', _ico(_png(), _dib()), ''),
    ('png-tail.ico', _ico(_png_raw(None, idat=STREAM_4x4 + synthetic(800))), 'after the end of the compressed'),
    ('png-size.ico', ICO_4x4_ENTRY + _ico(_png(8, 8))[8:], 'differs from the directory'),
    ('dib-padded.ico', _ico(_dib() + synthetic(700)), 'DIB of the expected size'),
    ('dib-height.ico', ICO_4x4_ENTRY + _ico(_dib(4, 40))[8:], 'DIB of the expected size'),
    ('cursor.ico', b'\x00\x00\x02\x00' + _ico(_png())[4:], 'not a ICO'),
    ('empty.ico', b'\x00\x00\x01\x00\x00\x00', 'ICO header is invalid'),
], ids=_ids)
def test_ico_entries(name, data, reason):
    problem = _media(name, data)
    assert (reason in problem) if reason else problem == ''


def test_images_written_by_qt_pass_and_doctored_ones_that_still_display_do_not():
    """Real encoder output passes. Doctored files that a viewer still shows normally, so a reviewer would not notice,
    are rejected (PNG, GIF) or sent to review (JPEG)."""
    pytest.importorskip('PySide6')
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    def encode(image, fmt):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        assert image.save(buffer, fmt)
        buffer.close()
        return bytes(data)

    base = QImage(37, 23, QImage.Format_ARGB32)
    base.fill(QColor(20, 120, 200, 180))
    base.setText('Software', 'ECU Studio AI test')
    for fmt in (QImage.Format_ARGB32, QImage.Format_RGB888, QImage.Format_Grayscale8, QImage.Format_Grayscale16,
                QImage.Format_Indexed8, QImage.Format_Mono):
        assert _media('qt.png', encode(base.convertToFormat(fmt), 'PNG')) == '', fmt

    png = encode(base, 'PNG')
    start = png.index(b'IDAT') - 4
    size = struct.unpack('>I', png[start:start + 4])[0]
    doctored = png[:start] + _chunk(b'IDAT', png[start + 8:start + 8 + size] + synthetic(5000)) + png[start + 12 + size:]
    assert not QImage.fromData(doctored).isNull()
    assert 'after the end of the compressed stream' in _media('qt.png', doctored)

    gif = _gif([(4, 4, list(range(16)))], lzw_tail=synthetic(3000))
    assert not QImage.fromData(gif).isNull()
    assert 'after the LZW end code' in _media('qt.gif', gif)

    jpeg = encode(base.convertToFormat(QImage.Format_RGB888), 'JPG')
    hidden = jpeg[:-2] + synthetic(4000).replace(b'\xff', b'\xff\x00') + b'\xff\xd9'
    assert not QImage.fromData(hidden).isNull()
    assert 'not decoded by the guard' in _media('qt.jpg', jpeg)
    assert 'not decoded by the guard' in _media('qt.jpg', hidden)
