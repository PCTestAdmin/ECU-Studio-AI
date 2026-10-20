"""Recognise files that must not be opened as a raw ECU image.

Opening a container as raw bytes would show the container's own structure as
"firmware" and invite edits that never reach an ECU. Recognised containers are
refused with a reason and, where possible, the supported route instead.
WinOLS projects (.ols) and mappacks (.kp) are proprietary and not imported.
"""
from __future__ import annotations
import re
from pathlib import Path

_HEX_LINE = re.compile(rb':[0-9A-Fa-f]{10,}\r?\n')
_SREC_LINE = re.compile(rb'S[0-9][0-9A-Fa-f]{6,}\r?\n')


def container_reason(head: bytes, name: str = '') -> str | None:
    """Why this file is not a raw ECU image, or None if nothing speaks against it.

    ``head`` is the start of the file (a few hundred bytes are enough).
    """
    suffix = Path(name).suffix.lower()
    if head[:4] == b'\x0b\x00\x00\x00' and head[4:15] == b'WinOLS File':
        return ('WinOLS-Projekt (.ols): proprietäres Containerformat, Import wird nicht unterstützt. '
                'In WinOLS die gewünschte Version als BIN exportieren und diese öffnen.')
    if suffix == '.kp':
        return ('WinOLS-Mappack (.kp): proprietäres, nicht dokumentiertes Format, Import wird nicht '
                'unterstützt. Kennfelder als XDF, A2L oder CSV exportieren.')
    if head[:4] == b'PK\x03\x04':
        return 'ZIP-Archiv: bitte zuerst entpacken und die enthaltene BIN öffnen.'
    if head[:4] == b'\x7fELF' or (head[:2] == b'MZ' and suffix in ('.exe', '.dll', '')):
        return 'Programmdatei (ELF/EXE), keine ECU-Rohdatei.'
    if _HEX_LINE.match(head):
        return 'Intel-HEX-Text: über „Speicherabbild importieren (HEX/S19)“ öffnen, damit Adressen erhalten bleiben.'
    if _SREC_LINE.match(head):
        return 'Motorola-S-Record-Text (S19/S28/S37): über „Speicherabbild importieren (HEX/S19)“ öffnen.'
    if suffix in ('.xdf', '.a2l', '.xml', '.csv', '.json'):
        return f'Definitionsdatei ({suffix}), keine Firmware: über den Definitionsimport laden.'
    return None


def check_raw_image(path: str | Path) -> None:
    """Raise ValueError if the file is a recognised non-raw container."""
    with open(path, 'rb') as f:
        head = f.read(512)
    reason = container_reason(head, str(path))
    if reason:
        raise ValueError(reason)
