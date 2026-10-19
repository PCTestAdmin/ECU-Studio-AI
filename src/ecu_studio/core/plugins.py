"""Explicit in-process extension registry for trusted importer/check modules.

No automatic Python discovery/execution from projects or archives. Hosts register
trusted callables. A plugin result must retain its provenance and trust status.
"""
from dataclasses import dataclass
from typing import Callable
from .model import BinaryImage,MapDefinition


@dataclass(frozen=True)
class ImportResult:
    maps: tuple[MapDefinition,...]
    provenance: str
    warnings: tuple[str,...]=()


@dataclass(frozen=True)
class CheckResult:
    status: str  # unsupported / fail / pass (algorithm-specific only)
    profile: str
    evidence: str
    flash_approved: bool=False


class Plugins:
    def __init__(self):
        self.importers={}
        self.checks={}

    def register(self,kind,name,fn:Callable):
        if kind not in ('import','check') or not name.strip() or not callable(fn):
            raise ValueError('Ungültiges Plugin')
        registry=self.importers if kind=='import' else self.checks
        if name in registry:
            raise ValueError('Pluginname bereits registriert')
        registry[name]=fn

    def import_definitions(self,name,path,image):
        result=self.importers[name](path,image.size)
        if not isinstance(result,ImportResult) or not result.provenance.strip():
            raise ValueError('Importplugin muss Herkunft und Definitionen liefern')
        maps=[]
        from dataclasses import replace
        for m in result.maps:
            m.validate(image.size)
            maps.append(replace(m,verified=False,source='plugin:'+name))
        return ImportResult(tuple(maps),result.provenance,result.warnings)

    def check(self,name,image,profile):
        # Pass an immutable byte snapshot; external code cannot mutate the image.
        result=self.checks[name](image.materialize(),profile)
        if (not isinstance(result,CheckResult) or result.status not in ('unsupported','fail','pass')
                or not result.profile or not result.evidence or result.flash_approved):
            raise ValueError('Prüfplugin liefert keinen nachvollziehbaren, begrenzten Prüfstatus')
        return result
