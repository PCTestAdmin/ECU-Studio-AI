"""Version numbers of ECU Studio AI: stable releases and release candidates (no Qt, stdlib only).

One textual form is used everywhere a person or a file name sees the version: ``__version__``, the tag without
``v``, ``VERSION.txt``, ``RUNTIME_INVENTORY.json``, the ZIP and setup file names, the release title and
"Apps & Features":

    stable              1.21.0          tag v1.21.0
    release candidate   1.21.0-rc1      tag v1.21.0-rc1      (rc1 ... rc99, no leading zero)

Anything else (``1.21.0rc1``, ``1.21.0-beta``, ``1.21.0-rc01``, ``1.21``) is rejected. Ordering:
``1.20.1 < 1.21.0-rc1 < 1.21.0-rc2 < 1.21.0 < 1.21.1-rc1``.

Two other formats are derived, never written by hand:

- PEP 440 (Python packaging metadata): ``1.21.0rc1``. ``pyproject.toml`` keeps the textual form, which PEP 440
  accepts and normalises to the same value.
- Windows numeric version (version resource of the starter EXE and of setup.exe, four numbers 0..65535):
  stable ``1.21.0.0``, rcN ``1.21.0.N``. It is unique per version but NOT ordered across a stable release and its
  candidates (rc1 = .1 > stable = .0); nothing compares it: the installer copies every file with
  ``ignoreversion`` and the program compares the textual form only. The text fields of the version resource
  (ProductVersion, AssemblyInformationalVersion) carry the textual form.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

_PATTERN = re.compile(r'v?(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})(?:-rc([1-9]\d?))?')


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    rc: int | None = None          # None = stable release

    @property
    def prerelease(self) -> bool:
        return self.rc is not None

    @property
    def base(self) -> str:
        """'1.21.0' for 1.21.0 and for 1.21.0-rc1: the stable version a candidate leads to."""
        return f'{self.major}.{self.minor}.{self.patch}'

    @property
    def text(self) -> str:
        return self.base + (f'-rc{self.rc}' if self.rc is not None else '')

    @property
    def tag(self) -> str:
        return 'v' + self.text

    @property
    def pep440(self) -> str:
        return self.base + (f'rc{self.rc}' if self.rc is not None else '')

    @property
    def windows(self) -> str:
        """Four numbers for Windows version resources (see the module docstring for why .N is not an order)."""
        return f'{self.base}.{self.rc or 0}'

    @property
    def key(self) -> tuple[int, int, int, int, int]:
        """Sort key: a candidate sorts before its stable release, candidates by number."""
        return (self.major, self.minor, self.patch, 0 if self.rc is not None else 1, self.rc or 0)

    def __lt__(self, other: 'Version') -> bool:
        return self.key < other.key

    def __le__(self, other: 'Version') -> bool:
        return self.key <= other.key

    def __gt__(self, other: 'Version') -> bool:
        return self.key > other.key

    def __ge__(self, other: 'Version') -> bool:
        return self.key >= other.key

    def __str__(self) -> str:
        return self.text


def parse(text) -> Version | None:
    """'v1.21.0' / '1.21.0' / '1.21.0-rc1' -> Version; anything else -> None."""
    if not isinstance(text, str):
        return None
    match = _PATTERN.fullmatch(text.strip())
    if not match:
        return None
    major, minor, patch, rc = match.groups()
    return Version(int(major), int(minor), int(patch), int(rc) if rc else None)


def parse_tag(tag) -> Version | None:
    """Only the exact tag form with a leading 'v' ('v1.21.0', 'v1.21.0-rc1')."""
    if not isinstance(tag, str) or not tag.startswith('v') or tag != tag.strip():
        return None
    return parse(tag)


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse(candidate), parse(current)
    return bool(a and b and a > b)


def windows_version(text: str) -> str:
    version = parse(text)
    if version is None:
        raise ValueError(f'keine gültige Version: {text!r}')
    return version.windows


FORMS = ('text', 'tag', 'pep440', 'windows', 'channel')


def main(argv=None) -> int:
    """python -m ecu_studio.core.app_version <version> [text|tag|pep440|windows|channel]: print one derived form."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or len(args) > 2:
        print('usage: python -m ecu_studio.core.app_version <version> [' + '|'.join(FORMS) + ']', file=sys.stderr)
        return 2
    version = parse(args[0])
    if version is None:
        print(f'FEHLER: {args[0]!r} ist keine gültige Version (1.2.3 oder 1.2.3-rcN)', file=sys.stderr)
        return 1
    form = args[1] if len(args) == 2 else 'text'
    values = {'text': version.text, 'tag': version.tag, 'pep440': version.pep440, 'windows': version.windows,
              'channel': 'prerelease' if version.prerelease else 'stable'}
    if form not in values:
        print(f'FEHLER: unbekannte Form {form!r}', file=sys.stderr)
        return 2
    print(values[form])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
