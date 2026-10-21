"""Signed updates: with a shipped maintainer key, a valid Ed25519 signature is required."""
import base64
import hashlib
import io
import pytest
from ecu_studio.core import updates, signing

BASE = 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v9.9.0/'
NAME = 'ECU-Studio-AI-9.9.0-windows-x64.zip'
PACKAGE = b'PK\x03\x04 test package'
SHA = hashlib.sha256(PACKAGE).hexdigest()
SECRET = bytes(range(1, 33))


class _Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data); self.url = url
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self.close()


def _release(signature: bytes | None, sig_url=BASE + NAME + '.sig'):
    assets = [{'name': NAME, 'browser_download_url': BASE + NAME, 'size': len(PACKAGE)},
              {'name': NAME + '.sha256', 'browser_download_url': BASE + NAME + '.sha256', 'size': 90}]
    if signature is not None:
        assets.append({'name': NAME + '.sig', 'browser_download_url': sig_url, 'size': 90})
    payload = {'tag_name': 'v9.9.0', 'draft': False, 'prerelease': False, 'body': '', 'html_url': '', 'assets': assets}
    files = {BASE + NAME: PACKAGE, BASE + NAME + '.sha256': f'{SHA}  {NAME}\n'.encode()}
    if signature is not None:
        files[sig_url] = base64.b64encode(signature)

    def opener(request, timeout=None):
        if request.full_url not in files:
            raise OSError('offline')
        return _Response(files[request.full_url], request.full_url)
    return updates.parse_release(payload), opener


@pytest.fixture
def maintainer_key(tmp_path, monkeypatch):
    key = tmp_path / 'update_signing_key.pub'
    key.write_text(signing.public_key(SECRET).hex(), encoding='ascii')
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', key)


def test_valid_signature_is_accepted(maintainer_key, tmp_path):
    release, opener = _release(signing.sign(SECRET, signing.update_message(NAME, SHA)))
    path, digest = updates.download(release, tmp_path / 'dl', opener)
    assert digest == SHA and path.read_bytes() == PACKAGE


@pytest.mark.parametrize('signature', [None, b'\x00' * 64])
def test_missing_or_wrong_signature_stops_before_download(maintainer_key, tmp_path, signature):
    release, opener = _release(signature)
    with pytest.raises(updates.UpdateError, match='signiert|ungültig'):
        updates.download(release, tmp_path / 'dl', opener)
    assert not (tmp_path / 'dl' / NAME).exists()


def test_signature_for_another_file_is_rejected(maintainer_key, tmp_path):
    other = signing.sign(SECRET, signing.update_message('ECU-Studio-AI-9.8.0-windows-x64.zip', SHA))
    release, opener = _release(other)
    with pytest.raises(updates.UpdateError, match='ungültig'):
        updates.download(release, tmp_path / 'dl', opener)


def test_foreign_signature_url_invalidates_the_release():
    release, _ = _release(b'x' * 64, sig_url='https://evil.example/x.sig')
    assert release is None


def test_without_shipped_key_signatures_are_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(signing, 'PUBLIC_KEY_FILE', tmp_path / 'missing.pub')
    release, opener = _release(None)
    assert updates.download(release, tmp_path / 'dl', opener)[1] == SHA
