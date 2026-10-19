"""Bounded ZIP import without filesystem extraction or path traversal."""
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZipFile
from ..core.model import BinaryImage


def archive_members(path):
    with ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>1000 or sum(i.file_size for i in members)>256*1024**2:
            raise ValueError('ZIP enthält zu viele/große Einträge')
        names=set()
        supported=[]
        for info in members:
            name=info.filename
            parts=PurePosixPath(name.replace('\\','/'))
            if (parts.is_absolute() or '..' in parts.parts or ':' in name or
                    stat.S_ISLNK(info.external_attr>>16) or name in names or
                    info.file_size>128*1024**2 or info.flag_bits&1):
                raise ValueError('Unsicherer, doppelter oder verschlüsselter ZIP-Eintrag')
            names.add(name)
            if Path(name).suffix.lower() in ('.bin','.ori') and not info.is_dir():
                supported.append(name)
        return supported


def read_archive_image(path, member):
    if member not in archive_members(path):
        raise ValueError('Kein unterstütztes BIN/ORI im ZIP')
    with ZipFile(path) as archive:
        data=archive.read(member)  # ZipFile verifies CRC; never execute/extract entries.
    if not data:
        raise ValueError('Leere Firmwaredatei')
    return BinaryImage(data)
