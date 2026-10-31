"""Firmware guard: keeps ECU firmware and private reference data out of git.

Runs as a git hook (``.githooks/pre-commit`` and ``.githooks/pre-push``) and as a command:

    python src/ecu_studio/tools/firmware_guard.py staged        :: check the index (what the next commit contains)
    python src/ecu_studio/tools/firmware_guard.py push REMOTE   :: check outgoing commits (ref lines on stdin)
    python src/ecu_studio/tools/firmware_guard.py tree [REV]    :: check every tracked file of a revision
    python src/ecu_studio/tools/firmware_guard.py history       :: check every blob reachable from any ref
    python src/ecu_studio/tools/firmware_guard.py allow PATH..  :: add staged public files to the allowlist
    python src/ecu_studio/tools/firmware_guard.py install       :: activate the hooks (core.hooksPath)

The script uses only the standard library and does not import ecu_studio, so the hooks work without an
installed package. It reads blobs from git (index or commits), never the working tree, so selective staging
is checked exactly as it will be committed. Reports name path, rule and size only, never file content.

A scanner is not a guarantee: data can be hidden in ways no rule matches (encryption, custom encodings,
small fragments). The rules are documented in docs/FIRMWARE_PROTECTION.md, together with the residual risks
and the manual review that is still required before every push.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CONFIG = '.firmware-guard.json'
ZERO = '0' * 40
EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'

# Firmware images, memory dumps, calibration definitions, tuning containers, archives and databases.
BLOCKED_EXTENSIONS = frozenset('''
    bin ori mod frf sgo odx pdx cbf hex ihex s19 s28 s37 srec mot sx a2l dam damos xdf xdfx kp ols ecu
    eep eeprom dump dmp fls flash rom img bdm full read zip 7z rar gz tgz tar xz bz2 sqlite sqlite3 db
'''.split())
# Directory names that hold local firmware or private references (see docs/FIRMWARE_PROTECTION.md).
PRIVATE_DIRS = frozenset({
    '.qa', 'firmware', 'references', 'private-reports', 'ecu-studio-local', 'mappacks', 'damos', 'a2l',
    'originals', 'modified', 'dumps', 'reads',
})
MEDIA_MAGIC = {
    'png': (b'\x89PNG\r\n\x1a\n',),
    'gif': (b'GIF87a', b'GIF89a'),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'ico': (b'\x00\x00\x01\x00',),
    'webp': (b'RIFF',),
}
# Byte strings that mark ECU images; only reported for binary content, to explain a block.
ECU_SIGNATURES = (
    b'EDC15', b'EDC16', b'EDC17', b'MED17', b'MED9', b'ME7.', b'ME9.', b'MG1', b'MD1', b'MSD80', b'MSD81',
    b'MSD85', b'MSV70', b'MSV80', b'MS43', b'MS42', b'SIMOS', b'SID80', b'PCR2', b'BOSCH', b'Bosch', b'SIEMENS',
    b'Continental', b'DELPHI', b'Delphi', b'DENSO', b'MAGNETI', b'0261', b'1037', b'1039', b'TC17', b'TC27',
)
MAX_SIZE = 1 << 20
MAX_HEX_RUN = 1024        # decoded bytes in one hex payload (pieces joined across lines)
MAX_HEX_TOTAL = 2048      # decoded bytes from all hex runs in one file
MAX_BASE64 = 768          # decoded bytes in one base64 block
MIN_RECORD_LINES = 8      # Intel HEX / S-record lines
HASH_LENGTHS = {32, 40, 64, 128}

HEX_RUN = re.compile(rb'(?<![0-9A-Za-z])[0-9A-Fa-f]{32,}(?![0-9A-Za-z])')
HEX_ESCAPES = re.compile(rb'(?:\\x[0-9A-Fa-f]{2}){8,}')
HEX_TOKENS = re.compile(rb'(?:0[xX][0-9A-Fa-f]{2}(?![0-9A-Za-z])\s*,?\s*){16,}')
HEX_SPACED = re.compile(rb'(?:(?<![0-9A-Za-z])[0-9A-Fa-f]{2}(?![0-9A-Za-z])[ \t]*){16,}')
B64_PIECE = re.compile(rb'[A-Za-z0-9+/]{40,}={0,2}')
# What may separate the pieces of one payload: quotes, whitespace, commas, string concatenation, b/r prefixes.
GAP = re.compile(rb'(?:[\s"\',+()\[\]bBrR]|\\n){0,24}')
RECORD_LINE = re.compile(rb'^(?::[0-9A-Fa-f]{10,}|S[0-9][0-9A-Fa-f]{8,})\r?$', re.M)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    detail: str
    where: str = ''

    def line(self) -> str:
        at = f' [{self.where}]' if self.where else ''
        return f'  {self.path}{at}: {self.rule} - {self.detail}'


@dataclass
class Config:
    allow: dict[str, str]
    max_size: int = MAX_SIZE
    local_roots: tuple[str, ...] = ()
    reviewed: frozenset = frozenset()
    reviewed: frozenset = frozenset()

    @staticmethod
    def load(text: str | None, local_roots=()) -> 'Config':
        raw = json.loads(text) if text else {}
        return Config(allow={str(k): str(v).lower() for k, v in raw.get('allow', {}).items()},
                      max_size=int(raw.get('max_size', MAX_SIZE)), local_roots=tuple(local_roots),
                      reviewed=frozenset(raw.get('reviewed_history', {})))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_binary(data: bytes) -> bool:
    head = data[:65536]
    if b'\x00' in head:
        return True
    try:
        head.decode('utf-8')
        return False
    except UnicodeDecodeError as error:
        # A multi-byte character cut at the window end is still text.
        if error.start >= len(head) - 3 and len(data) > len(head):
            return False
    control = sum(1 for b in head if b < 9 or 13 < b < 32 or b == 127)
    return control > len(head) // 50 or sum(1 for b in head if b > 127) > len(head) * 3 // 10


def signatures(data: bytes) -> list[str]:
    return sorted({s.decode() for s in ECU_SIGNATURES if s in data})


MAX_METADATA = 64 * 1024   # text/comment/EXIF bytes an image may carry besides its pixels
PNG_CHUNKS = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'gAMA', b'cHRM', b'sRGB', b'iCCP', b'sBIT', b'pHYs',
              b'bKGD', b'tIME', b'tEXt', b'zTXt', b'iTXt', b'hIST', b'sPLT', b'eXIf'}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _png_problem(data: bytes) -> str:
    """Walk all chunks: CRCs, known types only, bounded metadata, pixel data exactly as large as IHDR says."""
    import zlib
    pos, idat, meta, header, ended = 8, [], 0, None, False
    while pos + 12 <= len(data):
        size, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + size]
        if len(body) != size or pos + 12 + size > len(data):
            return 'PNG chunk runs past the end of the file'
        if zlib.crc32(kind + body) != struct.unpack('>I', data[pos + 8 + size:pos + 12 + size])[0]:
            return f'PNG chunk {kind!r} has a wrong checksum'
        if kind not in PNG_CHUNKS:
            return f'unknown PNG chunk {kind.decode("latin-1")!r} (can carry any data)'
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body[:13])
        elif kind == b'IDAT':
            idat.append(body)
        elif kind != b'PLTE':
            meta += size
        pos += 12 + size
        if kind == b'IEND':
            ended = True
            break
    if not ended or header is None:
        return 'PNG structure incomplete'
    if len(data) - pos > 16:
        return f'{len(data) - pos} bytes appended after the image end'
    if meta > MAX_METADATA:
        return f'{meta} bytes of PNG metadata'
    width, height, depth, color, _, _, interlace = header
    try:
        pixels = zlib.decompress(b''.join(idat))
    except zlib.error:
        return 'PNG pixel data is not valid'
    if not interlace and color in PNG_CHANNELS:
        expected = height * (1 + (width * PNG_CHANNELS[color] * depth + 7) // 8)
        if len(pixels) != expected:
            return f'PNG pixel data is {len(pixels)} bytes, the header needs {expected}'
    return ''


def _gif_problem(data: bytes) -> str:
    """Walk header, color tables and blocks up to the trailer, which must be the last byte."""
    if len(data) < 13:
        return 'GIF structure incomplete'
    flags = data[10]
    pos = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    meta = 0

    def blocks(p):
        total = 0
        while p < len(data) and data[p]:
            total += data[p]
            p += 1 + data[p]
        return p + 1, total
    while pos < len(data):
        tag = data[pos]
        if tag == 0x3B:
            return '' if pos == len(data) - 1 else f'{len(data) - pos - 1} bytes appended after the image end'
        if tag == 0x21 and pos + 1 < len(data):
            label = data[pos + 1]
            pos, size = blocks(pos + 2)
            if label != 0xF9:                       # comment, application and plain-text blocks
                meta += size
        elif tag == 0x2C and pos + 10 <= len(data):
            local = data[pos + 9]
            pos += 10 + (3 * 2 ** ((local & 7) + 1) if local & 0x80 else 0) + 1    # + LZW minimum code size
            pos, _ = blocks(pos)
        else:
            return 'GIF block structure broken'
        if meta > MAX_METADATA:
            return f'{meta} bytes of GIF comments/extensions'
    return 'GIF without trailer'


def _jpeg_problem(data: bytes) -> str:
    """Walk segments up to the scan; APPn/COM metadata bounded; EOI must end the file."""
    pos, meta = 2, 0
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xDA:
            end = data.rfind(b'\xff\xd9')
            if end < pos:
                return 'JPEG without end marker'
            tail = len(data) - end - 2
            return f'{tail} bytes appended after the image end' if tail > 16 else ''
        size = struct.unpack('>H', data[pos + 2:pos + 4])[0]
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            meta += size
            if meta > MAX_METADATA:
                return f'{meta} bytes of JPEG metadata'
        pos += 2 + size
    return 'JPEG segment structure broken'


def _ico_problem(data: bytes) -> str:
    """Every entry inside the file, entries cover it without gaps; each one a valid PNG or a DIB of exact size."""
    count = struct.unpack('<H', data[4:6])[0]
    spans = []
    for i in range(count):
        entry = data[6 + 16 * i:22 + 16 * i]
        if len(entry) < 16:
            return 'ICO directory runs past the end of the file'
        width, height, _, _, _, bits, size, offset = struct.unpack('<BBBBHHII', entry)
        image = data[offset:offset + size]
        if len(image) != size:
            return 'ICO entry runs past the end of the file'
        if image.startswith(b'\x89PNG\r\n\x1a\n'):
            problem = _png_problem(image)
            if problem:
                return f'ICO entry {i}: {problem}'
        else:
            w, h = width or 256, height or 256
            header, dib_bits = struct.unpack('<I', image[:4])[0], struct.unpack('<H', image[14:16])[0]
            colors = 2 ** dib_bits if dib_bits <= 8 else 0
            expected = header + 4 * colors + h * (((w * dib_bits + 31) // 32) * 4 + ((w + 31) // 32) * 4)
            if header != 40 or size != expected:
                return f'ICO entry {i} is neither PNG nor a DIB of the expected size'
        spans.append((offset, offset + size))
    pos = 6 + 16 * count
    for start, end in sorted(spans):
        if start != pos:
            return 'ICO has data between or overlapping its images'
        pos = end
    return '' if pos == len(data) else f'{len(data) - pos} bytes appended after the last ICO image'


def _webp_problem(data: bytes) -> str:
    if data[8:12] != b'WEBP' or struct.unpack('<I', data[4:8])[0] + 8 != len(data):
        return 'RIFF length does not match the file (renamed or appended data?)'
    pos, meta = 12, 0
    while pos + 8 <= len(data):
        kind, size = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        if kind not in (b'VP8 ', b'VP8L', b'VP8X', b'ALPH', b'ANIM', b'ANMF', b'ICCP', b'EXIF', b'XMP '):
            return f'unknown WEBP chunk {kind!r}'
        if kind in (b'EXIF', b'XMP ', b'ICCP'):
            meta += size
        pos += 8 + size + (size & 1)
    if meta > MAX_METADATA:
        return f'{meta} bytes of WEBP metadata'
    return '' if pos == len(data) else 'WEBP chunk structure broken'


def _media_problem(ext: str, data: bytes) -> str:
    """Structural check of an image: a valid header alone does not make a file an image."""
    if not data.startswith(MEDIA_MAGIC[ext]):
        return f'content is not a {ext.upper()} file (renamed?)'
    check = {'png': _png_problem, 'gif': _gif_problem, 'jpg': _jpeg_problem, 'jpeg': _jpeg_problem,
             'ico': _ico_problem, 'webp': _webp_problem}[ext]
    try:
        return check(data)
    except (struct.error, IndexError, ValueError) as error:
        return f'{ext.upper()} structure broken ({error})'


def _groups(pattern, data: bytes):
    """Matches of pattern, joined when only a GAP separates them (payloads split over lines or strings)."""
    group, last = [], -1
    for match in pattern.finditer(data):
        if group and GAP.fullmatch(data, last, match.start()):
            group.append(match)
        else:
            if group:
                yield group
            group = [match]
        last = match.end()
    if group:
        yield group


def _hex_size(pattern, text: bytes) -> int:
    if pattern is HEX_RUN:
        return len(text) // 2
    if pattern is HEX_ESCAPES:
        return text.count(b'\\x')
    if pattern is HEX_TOKENS:
        return len(re.findall(rb'0[xX][0-9A-Fa-f]{2}', text))
    return len(re.findall(rb'[0-9A-Fa-f]{2}', text))


def payloads(data: bytes) -> list[str]:
    """Embedded binary payloads in text: long hex, byte lists, escapes, base64, Intel HEX / S-records."""
    found, total = [], 0
    for pattern in (HEX_RUN, HEX_ESCAPES, HEX_TOKENS, HEX_SPACED):
        for group in _groups(pattern, data):
            if pattern is HEX_RUN and len(group) == 1 and len(group[0].group(0)) in HASH_LENGTHS:
                continue  # a single digest, not data
            size = sum(_hex_size(pattern, m.group(0)) for m in group)
            total += size
            if size >= MAX_HEX_RUN:
                found.append(f'hex payload of {size} bytes at offset {group[0].start()}')
    if total >= MAX_HEX_TOTAL and not found:
        found.append(f'{total} bytes of hex payload in total')
    records = len(RECORD_LINE.findall(data))
    if records >= MIN_RECORD_LINES:
        found.append(f'{records} Intel HEX / S-record lines (memory image)')
    found.extend(_base64_blocks(data))
    return found


def _base64_blocks(data: bytes) -> list[str]:
    found = []
    for group in _groups(B64_PIECE, data):
        blob = b''.join(m.group(0).rstrip(b'=') for m in group)
        if re.fullmatch(rb'[0-9A-Fa-f]+', blob) or len(blob) * 3 // 4 < MAX_BASE64:
            continue  # pure hex is handled above
        try:
            decoded = base64.b64decode(blob + b'=' * (-len(blob) % 4))
        except (binascii.Error, ValueError):
            continue
        if len(decoded) >= MAX_BASE64 and is_binary(decoded):
            marks = signatures(decoded)
            extra = f', ECU markers {", ".join(marks)}' if marks else ''
            found.append(f'base64 payload of {len(decoded)} bytes at offset {group[0].start()}{extra}')
    return found


def scan_blob(path: str, data: bytes, config: Config) -> list[Finding]:
    """All rules for one file as it would be committed."""
    pure = PurePosixPath(path)
    digest = sha256(data)
    allowed = config.allow.get(path)
    if allowed is not None:
        if allowed == digest:
            return []
        allowed_note = ' (allowlisted path, but content changed)'
    else:
        allowed_note = ''
    findings = []
    parts = [p.lower() for p in pure.parts[:-1]]
    private = sorted(set(parts) & PRIVATE_DIRS)
    if private:
        findings.append(Finding(path, 'private-dir', f'inside a local data folder ({", ".join(private)})'))
    ext = pure.suffix.lower().lstrip('.')
    if ext in BLOCKED_EXTENSIONS:
        findings.append(Finding(path, 'extension', f'.{ext} files hold firmware or definitions{allowed_note}'))
    if len(data) > config.max_size:
        findings.append(Finding(path, 'size', f'{len(data)} bytes > {config.max_size}{allowed_note}'))
    if is_binary(data):
        if ext in MEDIA_MAGIC:
            problem = _media_problem(ext, data)
            if problem:
                findings.append(Finding(path, 'media', problem))
        else:
            marks = signatures(data)
            detail = f'binary content ({len(data)} bytes)' + (f', ECU markers {", ".join(marks)}' if marks else '')
            findings.append(Finding(path, 'binary', detail + allowed_note))
    else:
        findings.extend(Finding(path, 'payload', item) for item in payloads(data))
        for root in config.local_roots:
            if root and root.encode('utf-8').lower() in data.lower():
                findings.append(Finding(path, 'local-path', 'names the local firmware folder'))
    return findings


def scan_message(where: str, text: str, config: Config) -> list[Finding]:
    data = text.encode('utf-8', 'replace')
    found = [Finding('(commit message)', 'payload', item, where) for item in payloads(data)]
    for root in config.local_roots:
        if root and root.lower() in text.lower():
            found.append(Finding('(commit message)', 'local-path', 'names the local firmware folder', where))
    return found


# --------------------------------------------------------------------------------------------- git access


class Git:
    def __init__(self, root: str | Path):
        self.root = str(root)
        self._batch = None

    def run(self, *args: str, data: bytes | None = None) -> bytes:
        result = subprocess.run(['git', '-C', self.root, *args], input=data, capture_output=True)
        if result.returncode:
            raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.decode(errors="replace").strip()}')
        return result.stdout

    def blob(self, sha: str) -> bytes:
        if self._batch is None:
            self._batch = subprocess.Popen(['git', '-C', self.root, 'cat-file', '--batch'],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self._batch.stdin.write(sha.encode() + b'\n')
        self._batch.stdin.flush()
        header = self._batch.stdout.readline().split()
        if len(header) < 3 or header[1] != b'blob':
            raise RuntimeError(f'object {sha} is not a blob')
        data = self._batch.stdout.read(int(header[2]))
        self._batch.stdout.read(1)
        return data

    def close(self):
        if self._batch is not None:
            self._batch.stdin.close()
            self._batch.wait()
            self._batch = None

    def config(self, rev: str | None) -> Config:
        try:
            text = self.run('show', f'{rev}:{CONFIG}' if rev else f':{CONFIG}').decode('utf-8')
        except RuntimeError:
            text = None
        return Config.load(text, local_roots(self))

    def changed(self, base: str, rev: str | None) -> list[tuple[str, str]]:
        """(path, blob sha) for added, copied, modified, renamed and type-changed files."""
        args = ['diff-index', '--cached', '-z', '--no-renames', base] if rev is None else \
            ['diff-tree', '-r', '-m', '-z', '--no-renames', '--root', '--no-commit-id', rev]
        raw = self.run(*args).split(b'\0')
        out, i = [], 0
        while i < len(raw) - 1:
            meta = raw[i].decode().split()
            path = raw[i + 1].decode('utf-8', 'surrogateescape')
            i += 2
            if not meta:
                continue
            status, mode, sha = meta[4][:1], meta[1], meta[3]
            if status != 'D' and mode != '160000' and sha != ZERO:
                out.append((path, sha))
        return out

    def tree(self, rev: str) -> list[tuple[str, str]]:
        out = []
        for entry in self.run('ls-tree', '-r', '-z', '--full-tree', rev).split(b'\0'):
            if not entry:
                continue
            meta, path = entry.split(b'\t', 1)
            mode, kind, sha = meta.decode().split()
            if kind == 'blob':
                out.append((path.decode('utf-8', 'surrogateescape'), sha))
        return out


def local_roots(git: Git | None = None) -> list[str]:
    """Configured local data folders: ECU_STUDIO_LOCAL_DATA (os.pathsep-separated) and git config."""
    roots = [p for p in os.environ.get('ECU_STUDIO_LOCAL_DATA', '').split(os.pathsep) if p.strip()]
    if git is not None:
        try:
            roots += git.run('config', '--get-all', 'ecu-studio.localdata').decode().split('\n')
        except RuntimeError:
            pass
    clean = []
    for root in roots:
        root = root.strip().rstrip('/\\')
        if root:
            clean += [root, root.replace('\\', '/'), root.replace('/', '\\')]
    return sorted(set(clean))


def _root_inside_repo(git: Git) -> list[Finding]:
    repo = Path(git.root).resolve()
    found = []
    for root in {r.replace('\\', '/') for r in local_roots(git)}:
        try:
            Path(root).resolve().relative_to(repo)
        except ValueError:
            continue
        found.append(Finding(root, 'local-path', 'the local firmware folder lies inside the repository'))
    return found


def _scan(git: Git, entries, config: Config, where: str = '', seen=None) -> list[Finding]:
    found = []
    for path, sha in entries:
        if seen is not None:
            if (path, sha) in seen:
                continue
            seen.add((path, sha))
        found += [Finding(f.path, f.rule, f.detail, where) for f in scan_blob(path, git.blob(sha), config)]
    return found


def check_staged(git: Git) -> list[Finding]:
    try:
        base = git.run('rev-parse', '--verify', '-q', 'HEAD').decode().strip()
    except RuntimeError:
        base = EMPTY_TREE
    return _root_inside_repo(git) + _scan(git, git.changed(base, None), git.config(None))


def outgoing(git: Git, lines) -> list[tuple[str, str]]:
    """(tip, range spec) for every pushed ref, from pre-push stdin lines."""
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue
        local, remote = parts[1], parts[3]
        exclude = ['--not', '--remotes'] if remote == ZERO or not _exists(git, remote) else [f'^{remote}']
        out.append((local, exclude))
    return out


def _exists(git: Git, sha: str) -> bool:
    try:
        git.run('cat-file', '-e', f'{sha}^{{commit}}')
        return True
    except RuntimeError:
        return False


def check_push(git: Git, lines) -> list[Finding]:
    found, seen = _root_inside_repo(git), set()
    for tip, exclude in outgoing(git, lines):
        config = git.config(tip)
        commits = git.run('rev-list', tip, *exclude).decode().split()
        for commit in commits:
            where = commit[:12]
            found += _scan(git, git.changed('', commit), config, where, seen)
            found += scan_message(where, git.run('log', '-1', '--format=%B', commit).decode('utf-8', 'replace'), config)
        # The whole tip tree as well: catches files that were tracked before the guard existed.
        found += _scan(git, git.tree(tip), config, tip[:12], seen)
    return found


def check_tree(git: Git, rev: str) -> list[Finding]:
    return _root_inside_repo(git) + _scan(git, git.tree(rev), git.config(rev), rev)


def check_history(git: Git) -> list[Finding]:
    config, found, seen = git.config(None), [], set()
    listing = [line.partition(' ') for line in
               git.run('rev-list', '--objects', '--all').decode('utf-8', 'surrogateescape').splitlines()]
    named = [(sha, path) for sha, _, path in listing if path]
    kinds = git.run('cat-file', '--batch-check=%(objecttype)',
                    data=''.join(f'{sha}\n' for sha, _ in named).encode()).decode().split()
    for (sha, path), kind in zip(named, kinds):
        if kind != 'blob' or (path, sha) in seen or sha in config.reviewed:
            continue
        seen.add((path, sha))
        found += [Finding(f.path, f.rule, f.detail, sha[:12]) for f in scan_blob(path, git.blob(sha), config)]
    return found


def allow(git: Git, paths) -> None:
    root = Path(git.root)
    cfg_path = root / CONFIG
    raw = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}
    entries = raw.setdefault('allow', {})
    for path in paths:
        rel = Path(path).resolve().relative_to(root.resolve()).as_posix()
        sha = git.run('ls-files', '-s', '--', rel).decode().split()
        if len(sha) < 2:
            raise SystemExit(f'{rel} is not staged; stage the public file first (git add -f {rel})')
        entries[rel] = sha256(git.blob(sha[1]))
    raw['allow'] = dict(sorted(entries.items()))
    cfg_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def report(found: list[Finding], what: str) -> int:
    if not found:
        print(f'firmware guard: {what} OK')
        return 0
    print(f'firmware guard: {what} BLOCKED - {len(found)} finding(s):', file=sys.stderr)
    for finding in found[:200]:
        print(finding.line(), file=sys.stderr)
    if len(found) > 200:
        print(f'  … and {len(found) - 200} more', file=sys.stderr)
    return 1


PUSH_HELP = '''
The data is part of the commit history. Do NOT fix this with a commit that deletes the file: the
earlier commit still contains it and would be published. Remove it from the unpublished commits
(e.g. reset the branch to before them and re-commit without the file), verify with
"firmware_guard.py push" again and only then push. If it was already pushed, treat it as published.
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('staged')
    push = sub.add_parser('push')
    push.add_argument('remote', nargs='?')
    push.add_argument('url', nargs='?')
    push.add_argument('--range', help='check REV range like origin/main..HEAD instead of reading stdin')
    tree = sub.add_parser('tree')
    tree.add_argument('rev', nargs='?', default='HEAD')
    sub.add_parser('history')
    allow_cmd = sub.add_parser('allow')
    allow_cmd.add_argument('paths', nargs='+')
    sub.add_parser('install')
    args = parser.parse_args(argv)
    git = Git(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True,
                             text=True).stdout.strip() or '.')
    try:
        if args.cmd == 'staged':
            return report(check_staged(git), 'staged changes')
        if args.cmd == 'push':
            if args.range:
                base, _, tip = args.range.partition('..')
                lines = [f'refs/x {git.run("rev-parse", tip or "HEAD").decode().strip()} refs/y '
                         f'{git.run("rev-parse", base).decode().strip()}']
            else:
                lines = sys.stdin.read().splitlines()
            code = report(check_push(git, lines), 'outgoing commits')
            if code:
                print(PUSH_HELP, file=sys.stderr)
            return code
        if args.cmd == 'tree':
            return report(check_tree(git, args.rev), f'tree {args.rev}')
        if args.cmd == 'history':
            return report(check_history(git), 'all reachable blobs')
        if args.cmd == 'allow':
            allow(git, args.paths)
            print(f'firmware guard: allowlisted {len(args.paths)} file(s) in {CONFIG}; commit it with the files')
            return 0
        git.run('config', 'core.hooksPath', '.githooks')
        print('firmware guard: hooks active (core.hooksPath = .githooks)')
        return 0
    except RuntimeError as error:
        print(f'firmware guard: {error} - blocked to be safe', file=sys.stderr)
        return 2
    finally:
        git.close()


if __name__ == '__main__':
    sys.exit(main())
