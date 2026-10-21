"""Release signing tool: never produces a release the installed apps would reject."""
import base64
import hashlib
from pathlib import Path
from ecu_studio.core import signing
from ecu_studio.tools import sign_release

SECRET = bytes(range(7, 39))


def _package(tmp_path):
    f = tmp_path / 'ECU-Studio-AI-9.9.0-windows-x64.zip'
    f.write_bytes(b'package bytes')
    return f


def test_no_key_anywhere_leaves_files_unsigned(tmp_path, monkeypatch):
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', tmp_path / 'none.pub')
    monkeypatch.delenv('UPDATE_SIGNING_KEY', raising=False)
    f = _package(tmp_path)
    assert sign_release.main(['sign', str(f)]) == 0 and not Path(str(f) + '.sig').exists()


def test_shipped_key_without_secret_fails(tmp_path, monkeypatch):
    pub = tmp_path / 'k.pub'; pub.write_text(signing.public_key(SECRET).hex(), encoding='ascii')
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', pub)
    monkeypatch.delenv('UPDATE_SIGNING_KEY', raising=False)
    assert sign_release.main(['sign', str(_package(tmp_path))]) == 1


def test_wrong_secret_fails_matching_secret_signs(tmp_path, monkeypatch):
    pub = tmp_path / 'k.pub'; pub.write_text(signing.public_key(SECRET).hex(), encoding='ascii')
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', pub)
    f = _package(tmp_path)
    monkeypatch.setenv('UPDATE_SIGNING_KEY', bytes(32).hex())
    assert sign_release.main(['sign', str(f)]) == 1
    monkeypatch.setenv('UPDATE_SIGNING_KEY', SECRET.hex())
    assert sign_release.main(['sign', str(f)]) == 0
    sig = base64.b64decode(Path(str(f) + '.sig').read_text())
    msg = signing.update_message(f.name, hashlib.sha256(f.read_bytes()).hexdigest())
    assert signing.verify(signing.trusted_key(), msg, sig)


def test_keygen_refuses_secret_inside_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', tmp_path / 'k.pub')
    inside = Path(sign_release.__file__).resolve().parents[3] / 'update_signing.key'
    assert sign_release.main(['keygen', '--secret-out', str(inside)]) == 2 and not inside.exists()
    outside = tmp_path / 'keys' / 'update_signing.key'
    assert sign_release.main(['keygen', '--secret-out', str(outside)]) == 0
    secret = bytes.fromhex(outside.read_text().strip())
    assert signing.trusted_key() == signing.public_key(secret)
    assert sign_release.main(['keygen', '--secret-out', str(outside)]) == 2      # never overwritten
