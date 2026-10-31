"""Firmware guard: hooks and rules, exercised in throwaway git repositories with synthetic data only."""
import base64
import json
import os
import random
import shutil
import subprocess
import sys
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


def test_media_files_must_be_real_images(repo):
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16 + b'IEND\xaeB`\x82'
    write(repo, 'docs/ok.png', png)
    assert commit(repo, 'docs/ok.png').returncode == 0
    write(repo, 'docs/smuggle.png', png + synthetic(4096))
    result = commit(repo, 'docs/smuggle.png')
    assert result.returncode != 0 and 'appended after the image end' in result.stderr


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
