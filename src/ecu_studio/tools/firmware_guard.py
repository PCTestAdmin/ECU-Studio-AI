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
import zlib
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


# ---------------------------------------------------------------------------------------------------- images
# An image passes only when every byte is accounted for: structure, bounded metadata and exactly the pixel data a
# decoder reads. Bytes a decoder skips (after an end marker, after the end of a compressed stream, in unknown
# chunks) are where a payload would hide. Pixel values themselves can still carry data; see the residual risks in
# docs/FIRMWARE_PROTECTION.md.
MAX_METADATA = 64 * 1024          # text, comments, EXIF, ICC and application data of one image together
MAX_BINARY_METADATA = 16 * 1024   # the binary part of that (EXIF, ICC, application blocks); text is scanned instead
MAX_PIXEL_BYTES = 64 << 20        # decompressed pixel data the guard verifies at most (decompression bombs)
INFLATE_STEP = 1 << 16            # output per decompression step, so memory stays bounded
UNVERIFIED = '{} pixel data is not decoded by the guard, so hidden data cannot be ruled out (view it, then allowlist it)'

PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
PNG_BEFORE_PLTE = {b'cHRM', b'gAMA', b'iCCP', b'sBIT', b'sRGB'}
PNG_AFTER_PLTE = {b'tRNS', b'bKGD', b'hIST'}
PNG_BEFORE_IDAT = PNG_BEFORE_PLTE | PNG_AFTER_PLTE | {b'pHYs', b'sPLT'}
PNG_TEXT = {b'tEXt', b'zTXt', b'iTXt'}
PNG_BINARY = {b'iCCP', b'eXIf', b'sPLT'}
PNG_CHUNKS = PNG_BEFORE_IDAT | PNG_TEXT | {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tIME', b'eXIf'}
PNG_NOT_AFTER_IDAT = PNG_BEFORE_IDAT | {b'PLTE'}
PNG_ONCE = PNG_CHUNKS - PNG_TEXT - {b'IDAT', b'sPLT'}
PNG_SIZE = {b'IHDR': 13, b'IEND': 0, b'gAMA': 4, b'cHRM': 32, b'sRGB': 1, b'pHYs': 9, b'tIME': 7}

JPEG_FRAMES = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
JPEG_TABLES = {0xC4, 0xCC, 0xDB, 0xDC, 0xDD}           # DHT, DAC, DQT, DNL, DRI
GIF_LOOP_APPS = {b'NETSCAPE2.0', b'ANIMEXTS1.0'}
WEBP_CHUNKS = {b'VP8 ', b'VP8L', b'VP8X', b'ALPH', b'ANIM', b'ANMF', b'ICCP', b'EXIF', b'XMP '}


def _inflate(stream: bytes, limit: int, sink=None) -> tuple[int, str]:
    """Output size of one zlib stream, decompressed in steps and never beyond `limit` bytes.

    zlib.decompress() silently drops anything after the end of the stream; here every input byte must belong to
    it. `sink(offset, chunk)` sees the output piece by piece and may return a problem."""
    inflater = zlib.decompressobj()
    total, pending = 0, stream
    try:
        while not inflater.eof:
            out = inflater.decompress(pending, INFLATE_STEP)
            pending = inflater.unconsumed_tail
            if total + len(out) > limit:
                return total + len(out), f'decompresses to more than {limit} bytes'
            problem = sink(total, out) if sink and out else ''
            if problem:
                return total, problem
            total += len(out)
            if not out and not pending:
                break
    except zlib.error:
        return total, 'is not valid zlib data'
    if not inflater.eof:
        return total, 'ends before the compressed stream is complete'
    extra = len(inflater.unused_data) + len(inflater.unconsumed_tail)
    return total, f'has {extra} bytes after the end of the compressed stream' if extra else ''


def _text_problem(text: bytes) -> str:
    """Text metadata must be text, and is scanned for embedded payloads like any text file."""
    if is_binary(text):
        return 'binary data in a text field'
    found = payloads(text)
    return f'text field holds a {found[0]}' if found else ''


def _png_rows(width: int, height: int, bits: int, interlace: int) -> list[tuple[int, int, int]]:
    """(start, end, row length) of each run of equally long rows in the decompressed pixel stream."""
    rows, pos = [], 0
    for x0, y0, dx, dy in (PNG_ADAM7 if interlace else ((0, 0, 1, 1),)):
        w, h = (width - x0 + dx - 1) // dx, (height - y0 + dy - 1) // dy
        if w and h:
            length = 1 + (w * bits + 7) // 8
            rows.append((pos, pos + h * length, length))
            pos += h * length
    return rows


def _png_filters(rows):
    """Sink for _inflate: every row must start with a filter type 0..4."""
    def check(offset: int, out: bytes) -> str:
        end = offset + len(out)
        for start, stop, length in rows:
            first = start + -(-(max(offset, start) - start) // length) * length
            last = min(stop, end)
            if first < last and max(out[first - offset:last - offset:length]) > 4:
                return 'uses an invalid row filter'
        return ''
    return check


def _png_text(kind: bytes, body: bytes) -> str:
    keyword, sep, rest = body.partition(b'\x00')
    if not sep or not 1 <= len(keyword) <= 79:
        return 'PNG text chunk without a valid keyword'
    if kind == b'iTXt':
        flag, method = rest[:1], rest[1:2]
        language, sep1, rest = rest[2:].partition(b'\x00')
        translated, sep2, rest = rest.partition(b'\x00')
        if not (sep1 and sep2) or flag not in (b'\x00', b'\x01') or method != b'\x00':
            return 'PNG iTXt chunk is malformed'
        compressed = flag == b'\x01'
        rest = translated + b'\n' + rest if not compressed else rest
    else:
        compressed = kind == b'zTXt'
        if compressed:
            if rest[:1] != b'\x00':
                return 'PNG zTXt chunk uses an unknown compression'
            rest = rest[1:]
    if compressed:
        parts = []
        _, problem = _inflate(rest, MAX_METADATA, lambda _, out: parts.append(out) or '')
        if problem:
            return f'PNG compressed text {problem}'
        rest = b''.join(parts)
    problem = _text_problem(rest)
    return f'PNG {kind.decode()}: {problem}' if problem else ''


def _png_binary(kind: bytes, body: bytes) -> str:
    if kind == b'eXIf' and body[:4] not in (b'II*\x00', b'MM\x00*'):
        return 'PNG eXIf chunk is not EXIF data'
    if kind == b'iCCP':
        name, sep, rest = body.partition(b'\x00')
        head = []
        size, problem = _inflate(rest[1:], 4 << 20, lambda offset, out: '' if offset else head.append(out) or '')
        profile = b''.join(head)[:128]
        if not sep or not 1 <= len(name) <= 79 or rest[:1] != b'\x00' or problem:
            return f'PNG iCCP chunk is malformed{" (" + problem + ")" if problem else ""}'
        if len(profile) < 40 or profile[36:40] != b'acsp' or struct.unpack('>I', profile[:4])[0] != size:
            return 'PNG iCCP chunk is not an ICC color profile'
    return ''


def _png_problem(data: bytes) -> str:
    """Chunks known, CRC-checked and in a valid order; metadata bounded and checked; the pixel stream decompresses
    to exactly the size IHDR implies, with valid row filters and no byte after its end; nothing after IEND."""
    pos, seen, header, palette, stream, closed = 8, set(), None, 0, [], False
    meta = binary = 0
    while True:
        if pos + 12 > len(data):
            return 'PNG structure incomplete'
        size, kind = struct.unpack('>I4s', data[pos:pos + 8])
        if size > 0x7FFFFFFF or pos + 12 + size > len(data):
            return 'PNG chunk runs past the end of the file'
        body = data[pos + 8:pos + 8 + size]
        if zlib.crc32(kind + body) != struct.unpack('>I', data[pos + 8 + size:pos + 12 + size])[0]:
            return f'PNG chunk {kind!r} has a wrong checksum'
        pos += 12 + size
        name = kind.decode('latin-1')
        if kind not in PNG_CHUNKS:
            return f'unknown PNG chunk {name!r} (can carry any data)'
        if (header is None) != (kind == b'IHDR') or (kind in PNG_ONCE and kind in seen):
            return f'PNG chunk {name!r} out of order or repeated'
        if kind in PNG_SIZE and size != PNG_SIZE[kind]:
            return f'PNG chunk {name!r} has a wrong size'
        if stream and kind != b'IDAT':
            closed = True
        if (kind == b'IDAT' and closed or kind in PNG_NOT_AFTER_IDAT and stream
                or kind in PNG_BEFORE_PLTE and b'PLTE' in seen):
            return f'PNG chunk {name!r} out of order or repeated'
        seen.add(kind)
        if kind == b'IHDR':
            header = width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if (not 0 < width <= 0x7FFFFFFF or not 0 < height <= 0x7FFFFFFF or depth not in PNG_DEPTHS.get(color, ())
                    or compression or filtering or interlace > 1):
                return 'PNG header is invalid (size, color type or bit depth)'
        elif kind == b'PLTE':
            palette = size // 3
            if color in (0, 4) or size % 3 or not 1 <= palette <= (1 << depth if color == 3 else 256):
                return 'PNG palette is invalid'
        elif kind == b'IDAT':
            stream.append(body)
        elif kind == b'IEND':
            break
        elif kind == b'tRNS' and (color in (4, 6) or size != {0: 2, 2: 6}.get(color, size)
                                  or color == 3 and not 0 < size <= palette):
            return 'PNG transparency chunk is invalid'
        elif kind in PNG_AFTER_PLTE and color == 3 and b'PLTE' not in seen:
            return f'PNG chunk {name!r} out of order or repeated'
        if kind not in (b'IHDR', b'PLTE', b'IDAT'):
            meta += size
            binary += size if kind in PNG_BINARY else 0
            if meta > MAX_METADATA:
                return f'{meta} bytes of PNG metadata'
            if binary > MAX_BINARY_METADATA:
                return f'{binary} bytes of binary PNG metadata (EXIF, ICC profile)'
            problem = _png_text(kind, body) if kind in PNG_TEXT else _png_binary(kind, body)
            if problem:
                return problem
    if pos != len(data):
        return f'{len(data) - pos} bytes appended after the image end'
    if not stream or color == 3 and not palette:
        return 'PNG structure incomplete'
    rows = _png_rows(width, height, depth * PNG_CHANNELS[color], interlace)
    expected = rows[-1][1]
    if expected > MAX_PIXEL_BYTES:
        return f'PNG pixel data of {expected} bytes is too large to verify'
    size, problem = _inflate(b''.join(stream), expected, _png_filters(rows))
    if problem:
        return f'PNG pixel data {problem} (the header needs {expected})'
    if size != expected:
        return f'PNG pixel data is {size} bytes, the header needs {expected}'
    return ''


def _gif_blocks(data: bytes, pos: int):
    """Data sub-blocks from pos up to the terminator: (list of blocks, position after it), or (None, pos)."""
    blocks = []
    while pos < len(data):
        size = data[pos]
        if not size:
            return blocks, pos + 1
        if pos + 1 + size > len(data):
            break
        blocks.append(data[pos + 1:pos + 1 + size])
        pos += 1 + size
    return None, pos


def _lzw_problem(stream: bytes, min_size: int, pixels: int) -> str:
    """The frame's LZW codes must produce exactly `pixels` pixels and end with the end code at the end of the data.

    Only code lengths are tracked (not pixel values), which is enough to know where decoding stops."""
    if not 2 <= min_size <= 8:
        return f'invalid LZW code size {min_size}'
    clear, end = 1 << min_size, (1 << min_size) + 1
    lengths = [1] * clear + [0] * (4096 - clear)
    size, next_code, prev = min_size + 1, clear + 2, -1
    acc = bits = pos = produced = 0
    while True:
        while bits < size:
            if pos == len(stream):
                return '' if produced == pixels else f'LZW data ends after {produced} of {pixels} pixels'
            acc |= stream[pos] << bits
            pos += 1
            bits += 8
        code = acc & ((1 << size) - 1)
        acc >>= size
        bits -= size
        if code == clear:
            size, next_code, prev = min_size + 1, clear + 2, -1
            continue
        if code == end:
            break
        if prev < 0:
            if code > clear:
                return 'invalid LZW code'
            length = 1
        elif code < next_code:
            length = lengths[code]
        elif code == next_code:
            length = lengths[prev] + 1
        else:
            return 'invalid LZW code'
        if prev >= 0 and next_code < 4096:
            lengths[next_code] = lengths[prev] + 1
            next_code += 1
            if next_code == 1 << size and size < 12:
                size += 1
        produced += length
        prev = code
        if produced > pixels:
            return f'LZW data holds more than the {pixels} pixels of the frame'
    if produced != pixels:
        return f'LZW data holds {produced} of {pixels} pixels'
    return f'{len(stream) - pos} bytes after the LZW end code' if pos < len(stream) else ''


def _gif_problem(data: bytes) -> str:
    """Header, color tables and every block up to the trailer, which must be the last byte; every frame's LZW data
    decodes to exactly its pixel count; known extensions only, comments are scanned as text."""
    if len(data) < 13:
        return 'GIF structure incomplete'
    flags = data[10]
    pos = 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    meta = binary = frames = 0
    while pos < len(data):
        tag = data[pos]
        if tag == 0x3B:
            if pos != len(data) - 1:
                return f'{len(data) - pos - 1} bytes appended after the image end'
            return '' if frames else 'GIF without image'
        if tag == 0x21 and pos + 2 <= len(data):
            label = data[pos + 1]
            blocks, pos = _gif_blocks(data, pos + 2)
            if blocks is None:
                return 'GIF block runs past the end of the file'
            body = b''.join(blocks)
            if label == 0xF9:
                if [len(b) for b in blocks] != [4]:
                    return 'GIF graphic control block is invalid'
                continue
            if label not in (0xFE, 0x01, 0xFF):
                return f'unknown GIF extension 0x{label:02X}'
            meta += len(body)
            if label == 0xFF and blocks and blocks[0] in GIF_LOOP_APPS:
                if any((len(b), b[0]) not in ((3, 1), (5, 2)) for b in blocks[1:]):
                    return 'GIF loop block is invalid'
            elif label == 0xFF:
                binary += len(body)
            else:
                text = body if label == 0xFE else b''.join(blocks[1:])
                problem = _text_problem(text) if text else ''
                if problem or label == 0x01 and (not blocks or len(blocks[0]) != 12):
                    return f'GIF text block: {problem or "invalid header"}'
            if meta > MAX_METADATA:
                return f'{meta} bytes of GIF comments/extensions'
            if binary > MAX_BINARY_METADATA:
                return f'{binary} bytes of binary GIF application data'
        elif tag == 0x2C and pos + 11 <= len(data):
            _, _, width, height, local = struct.unpack('<HHHHB', data[pos + 1:pos + 10])
            pos += 10 + (3 << ((local & 7) + 1) if local & 0x80 else 0)
            if pos >= len(data):
                return 'GIF structure incomplete'
            min_size = data[pos]
            blocks, pos = _gif_blocks(data, pos + 1)
            if blocks is None:
                return 'GIF block runs past the end of the file'
            problem = _lzw_problem(b''.join(blocks), min_size, width * height)
            if problem:
                return f'GIF frame {frames}: {problem}'
            frames += 1
        else:
            return 'GIF block structure broken'
    return 'GIF without trailer'


def _jpeg_problem(data: bytes) -> str:
    """Every segment and entropy-coded scan up to EOI, which must end the file; metadata bounded everywhere.

    The scans are not decoded, so bytes after the last coded block of a scan look like image data. A JPEG that
    passes the walk is therefore still reported and needs a reviewed allowlist entry."""
    pos, meta, frame, scans = 2, 0, False, 0
    while pos + 2 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xFF:                                       # fill byte
            pos += 1
            continue
        if marker == 0xD9:
            tail = len(data) - pos - 2
            if tail:
                return f'{tail} bytes appended after the image end'
            return UNVERIFIED.format('JPEG') if scans else 'JPEG without image data'
        if not (marker in JPEG_FRAMES or marker in JPEG_TABLES or 0xE0 <= marker <= 0xEF or marker in (0xDA, 0xFE)):
            return f'unexpected JPEG marker 0x{marker:02X}'
        if pos + 4 > len(data):
            break
        size = struct.unpack('>H', data[pos + 2:pos + 4])[0]
        if size < 2 or pos + 2 + size > len(data):
            return 'JPEG segment runs past the end of the file'
        body = data[pos + 4:pos + 2 + size]
        pos += 2 + size
        if marker in JPEG_FRAMES:
            if frame:
                return 'JPEG with two frame headers'
            frame = True
        elif marker == 0xFE or marker >= 0xE0:
            meta += size
            if meta > MAX_METADATA:
                return f'{meta} bytes of JPEG metadata'
            problem = _text_problem(body) if marker == 0xFE and body else ''
            if problem:
                return f'JPEG comment: {problem}'
        elif marker == 0xDA:
            if not frame:
                return 'JPEG scan before the frame header'
            scans += 1
            while True:                                          # entropy-coded data up to the next real marker
                pos = data.find(b'\xff', pos)
                if pos < 0 or pos + 1 >= len(data):
                    return 'JPEG without end marker'
                follow = data[pos + 1]
                if follow and not 0xD0 <= follow <= 0xD7:       # not a stuffed 0xFF00 and not a restart marker
                    break
                pos += 2
    return 'JPEG segment structure broken'


def _ico_problem(data: bytes) -> str:
    """Every entry inside the file, entries cover it without gaps; each one a valid PNG of the listed size or a
    DIB whose header matches the entry and whose size is exactly what that header needs."""
    reserved, kind, count = struct.unpack('<HHH', data[:6])
    if reserved or kind != 1 or not count:
        return 'ICO header is invalid'
    spans = []
    for i in range(count):
        entry = data[6 + 16 * i:22 + 16 * i]
        if len(entry) < 16:
            return 'ICO directory runs past the end of the file'
        width, height, _, _, _, _, size, offset = struct.unpack('<BBBBHHII', entry)
        w, h = width or 256, height or 256
        image = data[offset:offset + size]
        if len(image) != size:
            return 'ICO entry runs past the end of the file'
        if image.startswith(b'\x89PNG\r\n\x1a\n'):
            problem = _png_problem(image)
            if problem:
                return f'ICO entry {i}: {problem}'
            if struct.unpack('>II', image[16:24]) != (w, h):
                return f'ICO entry {i}: PNG size differs from the directory ({w}x{h})'
        else:
            header, dw, dh, planes, bits, compression = struct.unpack('<IiiHHI', image[:20])
            used = struct.unpack('<I', image[32:36])[0]
            colors = (used or 1 << bits) if bits <= 8 else 0
            expected = header + 4 * colors + h * (((w * bits + 31) // 32) * 4 + ((w + 31) // 32) * 4)
            if (header != 40 or (dw, dh) != (w, 2 * h) or planes != 1 or bits not in (1, 4, 8, 24, 32)
                    or compression or used and (bits > 8 or used > 1 << bits) or size != expected):
                return f'ICO entry {i} is neither PNG nor a DIB of the expected size'
        spans.append((offset, offset + size))
    pos = 6 + 16 * count
    for start, end in sorted(spans):
        if start != pos:
            return 'ICO has data between or overlapping its images'
        pos = end
    return '' if pos == len(data) else f'{len(data) - pos} bytes appended after the last ICO image'


def _webp_problem(data: bytes) -> str:
    """RIFF length, known chunks, bounded metadata. The VP8/VP8L bitstreams are not decoded, so a WEBP that passes
    is still reported and needs a reviewed allowlist entry."""
    if data[8:12] != b'WEBP' or struct.unpack('<I', data[4:8])[0] + 8 != len(data):
        return 'RIFF length does not match the file (renamed or appended data?)'
    pos, meta = 12, 0
    while pos + 8 <= len(data):
        kind, size = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        if kind not in WEBP_CHUNKS:
            return f'unknown WEBP chunk {kind!r}'
        if pos == 12 and kind not in (b'VP8 ', b'VP8L', b'VP8X'):
            return 'WEBP does not start with an image chunk'
        if kind in (b'EXIF', b'XMP ', b'ICCP'):
            meta += size
        pos += 8 + size + (size & 1)
    if meta > MAX_BINARY_METADATA:
        return f'{meta} bytes of WEBP metadata'
    return UNVERIFIED.format('WEBP') if pos == len(data) and pos > 12 else 'WEBP chunk structure broken'


def _media_problem(ext: str, data: bytes) -> str:
    """Structural check of an image: a valid header alone does not make a file an image."""
    if not data.startswith(MEDIA_MAGIC[ext]):
        return f'content is not a {ext.upper()} file (renamed?)'
    check = {'png': _png_problem, 'gif': _gif_problem, 'jpg': _jpeg_problem, 'jpeg': _jpeg_problem,
             'ico': _ico_problem, 'webp': _webp_problem}[ext]
    try:
        return check(data)
    except (struct.error, IndexError, ValueError, OverflowError) as error:
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
    if ext in MEDIA_MAGIC:                    # an image name promises an image, text or not
        problem = _media_problem(ext, data)
        if problem:
            findings.append(Finding(path, 'media', problem + allowed_note))
    elif is_binary(data):
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
