"""Update check and verified download via the GitHub Releases API (no Qt, testable).

Flow: latest *stable* release (``/releases/latest`` never returns drafts or
pre-releases) -> newer than the running version? -> the user decides -> the
ZIP is downloaded only from this repository's release URLs, its SHA-256 must
match the published ``.sha256`` asset AND GitHub's own asset digest when the
API provides one -> the separate updater (packaging/updater.ps1) installs it
after the app has closed, with backup and rollback. Nothing runs without the
user's consent and nothing unverified is ever executed.
"""
from __future__ import annotations
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
class Release:
    version: str
    notes: str
    page_url: str
    archive_name: str
    archive_url: str
    archive_size: int
    checksum_url: str
    api_digest: str | None      # 'sha256:<hex>' from the API, if GitHub provides it


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
    digest = archive.get('digest')
    return Release(text, str(payload.get('body') or '').strip(), str(payload.get('html_url') or ''),
                   name, archive['browser_download_url'], int(archive.get('size') or 0),
                   checksum['browser_download_url'],
                   digest if isinstance(digest, str) and digest.startswith('sha256:') else None)


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


def download(release: Release, target_dir: Path, opener=None, progress=None, cancelled=None) -> tuple[Path, str]:
    """Download and verify the package; returns (path, sha256). Deletes it on any mismatch."""
    if not (_official_download(release.archive_url) and _official_download(release.checksum_url)):
        raise UpdateError('Download-Adresse gehört nicht zu den offiziellen Releases.')
    if release.archive_size > MAX_ARCHIVE:
        raise UpdateError('Update-Paket ist unplausibel groß.')
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with _get(release.checksum_url, opener) as response:
            expected = _expected_sha256(response.read(4096).decode('ascii', 'replace'), release.archive_name)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f'Prüfsumme konnte nicht geladen werden: {exc}') from exc
    if release.api_digest and release.api_digest.split(':', 1)[1].lower() != expected:
        raise UpdateError('Prüfsummendatei und GitHub-Angabe widersprechen sich – Update abgebrochen.')
    path = target_dir / release.archive_name
    partial = path.with_suffix('.part')
    digest, received = hashlib.sha256(), 0
    try:
        with _get(release.archive_url, opener) as response, open(partial, 'wb') as out:
            final_url = getattr(response, 'geturl', lambda: release.archive_url)()
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
                if progress and release.archive_size:
                    progress(min(100, received * 100 // release.archive_size))
    except UpdateError:
        partial.unlink(missing_ok=True); raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f'Download fehlgeschlagen: {exc}') from exc
    actual = digest.hexdigest()
    if actual != expected or (release.archive_size and received != release.archive_size):
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
