"""Update check and verified download via the GitHub Releases API (no Qt, testable).

Flow: latest *stable* release (``/releases/latest`` never returns drafts or
pre-releases) -> newer than the running version? -> the user decides -> the
ZIP is downloaded only from this repository's release URLs, its SHA-256 must
match the published ``.sha256`` asset AND GitHub's own asset digest when the
API provides one -> the separate updater (packaging/updater.ps1) installs it
after the app has closed, with backup and rollback. Nothing runs without the
user's consent and nothing unverified is ever executed.

Installations made with the installer (unins000.exe + Inno uninstall entry for
exactly this folder) are updated with the release's verified setup.exe instead
of the ZIP (from 1.20.1): the uninstall log, the uninstaller and the version in
"Apps & Features" then stay correct (finding A5 of 1.20.0). Portable copies keep
the ZIP route.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = 'PCTestAdmin/ECU-Studio-AI'
API_LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET_PATTERN = re.compile(r'^ECU-Studio-AI-(\d+\.\d+\.\d+)-windows-x64\.zip$')
CHECK_INTERVAL = 24 * 3600          # at most once a day
TIMEOUT = 8
MAX_ARCHIVE = 800 * 1024 * 1024
ALLOWED_DOWNLOAD_HOSTS = ('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')


class UpdateError(Exception):
    """A check or download that must not continue; the message is user-facing (German)."""


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'v1.15.0' / '1.15.0' -> (1, 15, 0); anything else (incl. pre-release suffixes) -> None."""
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', (text or '').strip())
    return tuple(int(x) for x in match.groups()) if match else None


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


@dataclass(frozen=True)
class Asset:
    """One verifiable download of a release: file, its '.sha256' asset and optional '.sig'."""
    name: str
    url: str
    size: int
    checksum_url: str
    api_digest: str | None
    signature_url: str | None = None


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    page_url: str
    archive_name: str
    archive_url: str
    archive_size: int
    checksum_url: str
    api_digest: str | None      # 'sha256:<hex>' from the API, if GitHub provides it
    signature_url: str | None = None   # '<archive>.sig': Ed25519 signature (core/signing.py)
    installer: Asset | None = None     # 'ECU-Studio-AI-<v>-setup.exe' with its '.sha256' (optional)

    @property
    def archive(self) -> Asset:
        return Asset(self.archive_name, self.archive_url, self.archive_size, self.checksum_url,
                     self.api_digest, self.signature_url)


def _official_download(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.hostname == 'github.com'
            and parsed.path.lower().startswith(f'/{REPOSITORY.lower()}/releases/download/'))


def parse_release(payload: dict) -> Release | None:
    """The installable Windows package of a release, or None if it has none / is not stable."""
    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease'):
        return None
    version = parse_version(payload.get('tag_name', ''))
    if version is None:
        return None
    text = '.'.join(map(str, version))
    assets = {a.get('name'): a for a in payload.get('assets', []) if isinstance(a, dict)}
    name = f'ECU-Studio-AI-{text}-windows-x64.zip'
    archive, checksum = assets.get(name), assets.get(name + '.sha256')
    if not archive or not checksum:
        return None
    for asset in (archive, checksum):
        if not _official_download(asset.get('browser_download_url', '')):
            return None
    signature = assets.get(name + '.sig')
    signature_url = signature.get('browser_download_url', '') if signature else None
    if signature_url is not None and not _official_download(signature_url):
        return None
    digest = archive.get('digest')
    # The generic installation footer (after '---') belongs on the release page, not in the update dialog.
    notes = str(payload.get('body') or '').split('\n---\n', 1)[0].strip()
    return Release(text, notes, str(payload.get('html_url') or ''),
                   name, archive['browser_download_url'], int(archive.get('size') or 0),
                   checksum['browser_download_url'],
                   _sha256_digest(digest), signature_url, _installer_asset(assets, text))


def _sha256_digest(value) -> str | None:
    return value if isinstance(value, str) and value.startswith('sha256:') else None


def _installer_asset(assets: dict, version: str) -> Asset | None:
    """The setup.exe of the release, only with its .sha256 and only from official release URLs."""
    name = f'ECU-Studio-AI-{version}-setup.exe'
    setup, checksum, signature = assets.get(name), assets.get(name + '.sha256'), assets.get(name + '.sig')
    if not setup or not checksum:
        return None
    urls = [setup.get('browser_download_url', ''), checksum.get('browser_download_url', '')]
    if signature:
        urls.append(signature.get('browser_download_url', ''))
    if not all(_official_download(url) for url in urls):
        return None
    return Asset(name, setup['browser_download_url'], int(setup.get('size') or 0), checksum['browser_download_url'],
                 _sha256_digest(setup.get('digest')), signature['browser_download_url'] if signature else None)


def _get(url: str, opener=None, accept: str = 'application/octet-stream'):
    request = urllib.request.Request(url, headers={'User-Agent': 'ECU-Studio-AI-Updater', 'Accept': accept})
    return (opener or urllib.request.urlopen)(request, timeout=TIMEOUT)


def fetch_latest(opener=None) -> Release | None:
    """Latest stable release with a Windows package, or None. Network errors raise UpdateError."""
    try:
        with _get(API_LATEST, opener, 'application/vnd.github+json') as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode('utf-8'))
    except UpdateError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 404:           # repository has no published stable release yet
            return None
        raise UpdateError(f'Update-Prüfung nicht möglich: GitHub antwortet {exc.code}') from exc
    except Exception as exc:          # offline, DNS, rate limit, invalid JSON: never fatal
        raise UpdateError(f'Update-Prüfung nicht möglich: {exc}') from exc
    return parse_release(payload)


def check_due(last_check: float | None, now: float | None = None, interval: float = CHECK_INTERVAL) -> bool:
    now = time.time() if now is None else now
    return last_check is None or now - float(last_check) >= interval or now < float(last_check)


def update_available(current: str, release: Release | None, skipped: str | None = None) -> bool:
    return bool(release and is_newer(release.version, current) and release.version != (skipped or ''))


def _expected_sha256(text: str, name: str) -> str:
    """'<64 hex>  <name>' (sha256sum format) -> hex; the name must match when given."""
    for line in text.splitlines():
        parts = line.strip().split()
        if parts and re.fullmatch(r'[0-9a-fA-F]{64}', parts[0]):
            if len(parts) == 1 or parts[-1].lstrip('*') == name:
                return parts[0].lower()
    raise UpdateError('Prüfsummendatei des Updates ist ungültig.')


def _check_signature(asset: Asset, sha256_hex: str, opener=None) -> None:
    from .signing import trusted_key, update_message, verify
    key = trusted_key()
    if key is None:
        return
    if not asset.signature_url:
        raise UpdateError('Update ist nicht signiert – abgebrochen (diese Version verlangt eine Signatur).')
    try:
        with _get(asset.signature_url, opener) as response:
            signature = base64.b64decode(response.read(256).strip(), validate=True)
    except Exception as exc:
        raise UpdateError(f'Signatur konnte nicht geladen werden: {exc}') from exc
    if not verify(key, update_message(asset.name, sha256_hex), signature):
        raise UpdateError('Signatur des Updates ist ungültig – abgebrochen, nichts wurde geladen.')


def download(release: Release, target_dir: Path, opener=None, progress=None, cancelled=None,
             installer: bool = False) -> tuple[Path, str]:
    """Download and verify the package (or with installer=True the setup.exe); returns (path, sha256).
    Deletes it on any mismatch."""
    asset = release.installer if installer else release.archive
    if asset is None:
        raise UpdateError('Dieses Release enthält keinen Installer.')
    if not (_official_download(asset.url) and _official_download(asset.checksum_url)):
        raise UpdateError('Download-Adresse gehört nicht zu den offiziellen Releases.')
    if asset.size > MAX_ARCHIVE:
        raise UpdateError('Update-Paket ist unplausibel groß.')
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with _get(asset.checksum_url, opener) as response:
            expected = _expected_sha256(response.read(4096).decode('ascii', 'replace'), asset.name)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f'Prüfsumme konnte nicht geladen werden: {exc}') from exc
    if asset.api_digest and asset.api_digest.split(':', 1)[1].lower() != expected:
        raise UpdateError('Prüfsummendatei und GitHub-Angabe widersprechen sich – Update abgebrochen.')
    # With a maintainer key shipped in the app, the expected SHA-256 must carry its signature,
    # checked BEFORE the package is fetched (a forged .sha256 file is not enough).
    _check_signature(asset, expected, opener)
    path = target_dir / asset.name
    partial = path.with_suffix('.part')
    digest, received = hashlib.sha256(), 0
    try:
        with _get(asset.url, opener) as response, open(partial, 'wb') as out:
            final_url = getattr(response, 'geturl', lambda: asset.url)()
            if urlparse(final_url).hostname not in ALLOWED_DOWNLOAD_HOSTS:
                raise UpdateError('Download wurde auf einen fremden Server umgeleitet.')
            while True:
                if cancelled and cancelled():
                    raise UpdateError('Download abgebrochen.')
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_ARCHIVE:
                    raise UpdateError('Update-Paket ist unplausibel groß.')
                digest.update(chunk); out.write(chunk)
                if progress and asset.size:
                    progress(min(100, received * 100 // asset.size))
    except UpdateError:
        partial.unlink(missing_ok=True); raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f'Download fehlgeschlagen: {exc}') from exc
    actual = digest.hexdigest()
    if actual != expected or (asset.size and received != asset.size):
        partial.unlink(missing_ok=True)
        raise UpdateError('Prüfsumme des heruntergeladenen Updates stimmt nicht – nichts wurde installiert.')
    partial.replace(path)
    return path, actual


def install_root(executable: str) -> Path | None:
    """Folder of an installed/portable package (contains ECU-Studio-AI.exe), or None when run from source."""
    exe = Path(executable).resolve()
    # Portable layout: <root>/_internal/python/pythonw.exe and <root>/ECU-Studio-AI.exe
    if exe.parent.name.lower() == 'python' and exe.parent.parent.name.lower() == '_internal':
        root = exe.parent.parent.parent
        if (root / 'ECU-Studio-AI.exe').is_file() and (root / '_internal' / 'updater.ps1').is_file():
            return root
    return None


# ---- installations made with the installer (Inno Setup, per user) ---------------------------------
# AppId of packaging/installer.iss; Inno writes its uninstall entry under '{<AppId>}_is1'.
APP_GUID = 'F8CD5330-FC90-4891-BFDA-58E6668C93A5'
UNINSTALL_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + '{' + APP_GUID + '}_is1'


def _same_folder(a: str, b: Path) -> bool:
    try:
        return Path(str(a).rstrip('\\/')).resolve().as_posix().lower() == Path(b).resolve().as_posix().lower()
    except (OSError, ValueError):
        return False


def _read_uninstall_entry() -> dict | None:
    try:
        import winreg
    except ImportError:          # not Windows
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            values = {}
            for name in ('InstallLocation', 'DisplayVersion', 'DisplayName'):
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    values[name] = None
            return values
    except OSError:
        return None


def _write_uninstall_entry(values: dict) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def installer_registration(root: Path, read=_read_uninstall_entry) -> dict | None:
    """The installer's uninstall entry if it belongs to exactly this folder (else None: portable copy,
    another installation, or not Windows)."""
    entry = read()
    if not entry or not entry.get('InstallLocation') or not _same_folder(entry['InstallLocation'], root):
        return None
    return entry


def update_route(root: Path | None, release: Release, read=_read_uninstall_entry) -> str:
    """'installer' for an installation made with the installer when the release ships a setup.exe,
    otherwise 'archive' (portable copy: folder swap from the ZIP)."""
    if (root is not None and release.installer is not None and (Path(root) / 'unins000.exe').is_file()
            and installer_registration(Path(root), read) is not None):
        return 'installer'
    return 'archive'


def sync_uninstall_entry(root: Path, version: str, read=_read_uninstall_entry, write=_write_uninstall_entry) -> bool:
    """Show the running version in "Apps & Features" when the entry belongs to this folder but names
    another version (in-app updates up to 1.20.0 replaced the files without touching it). True if changed."""
    entry = installer_registration(root, read)
    if entry is None or parse_version(version) is None or entry.get('DisplayVersion') == version:
        return False
    write({'DisplayVersion': version, 'DisplayName': f'ECU Studio AI {version}'})
    return True
