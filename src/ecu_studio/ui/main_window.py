"""ECU Studio AI offline Windows desktop shell (Qt6 Widgets)."""
from __future__ import annotations
import csv
import hashlib
import numpy as np
import os
import json
import urllib.request
from pathlib import Path
from bisect import bisect_left

from PySide6.QtCore import Qt, QThread, Signal, QModelIndex, QSettings, QSize, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTableView,
    QFileDialog, QMessageBox, QFormLayout, QComboBox, QSpinBox, QApplication,
    QDoubleSpinBox, QPlainTextEdit, QInputDialog, QAbstractItemView, QGroupBox,
    QHeaderView, QMenu, QStatusBar, QDialog, QDialogButtonBox, QTextEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QDockWidget, QToolBar, QStyle, QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem, QProgressBar, QListView
)
from .theme import stylesheet, palette
from .. import __version__
from .icons import line_icon
from ..core.preflight import run_preflight
from ..formats.records import read_memory_file
from ..formats.sniff import check_raw_image
from ..formats.importer import convert_to_binary, read_import_segments
from ..core.model import BinaryImage, MapDefinition, TYPES, FORMATS, save_project, load_project, read_project_snapshots
from ..core.detection import discover_maps
from ..core.detection_extended import scan_u8
from ..core.detection_32 import scan_32
from ..core.detection_signed import scan_s16
from ..core.a2l import read_a2l
from ..core.xdf import read_xdf, recognize_ms43
from ..core.profiles import identify_profile, xdf_match_status, local_xdf_candidates
from ..core.definition_registry import remember_pair, lookup_pair, search_local_xdfs
from ..core.quality import audit_catalog, write_quality_csv
from ..core.scoped_scan import scan_calibration_candidates
from ..recognition.bundled_definitions import matching_source
from ..core.workflows import catalogue_check, export_map_pack, import_map_pack
from ..core.impact import measure_catalogue, uncovered_patches, export_impact_csv
from ..core.versioning import make_snapshot, plan_restore, apply_restore
from .tools_dialogs import A2LLinkDialog, BatchEditDialog, CommandPalette
from ..core.definitions import import_definitions, export_definitions, parse_offset
from ..core.search import hex_pattern_search, compare_reference, export_patch_csv
from ..core.compare_maps import compare_images, export_map_comparison_csv, export_cell_comparison_csv, delta_matrix
from ..core.axis_inference import suggest_adjacent_axes
from ..core.checksum_audit import (load_checksum_profile, audit_export, write_audit_json,
                                  plan_checksum_correction, apply_checksum_correction, correction_preview)
from ..core.map_groups import group_maps, export_groups_csv
from ..core.axis_groups import group_index, shared_axis_groups
from ..recognition.identity_registry import identify_vehicle, import_identity_manifest, identity_stats
from ..core.library import MapLibrary
from ..core.intelligence import LEXICON, export_detection_report, suggest_reference_shapes, label_from_metadata, enrich_with_exact_references
from ..core.report import export_html
from ..core.demo import generate_demo
from ..core.extended_demo import generate_extended_demo
from ..core.analysis import analyze_map, find_similar_maps
from .views import HexTableModel, MapTableModel, Map2DView, Map3DView, MemoryAtlasView, MapCurveView
from .raw_2d import Raw2DView
from ..recognition.catalog import DefinitionCatalog, default_catalog
from ..recognition.public_sources import source_rows, candidates as public_candidates, fetch_and_index, attach_ms43_preview
from ..recognition.transfer import match_verified
from ..recognition.ml import Model
from ..recognition.structure_model import ShapeModel, train_shape_model
from ..recognition.safe_classifier import train_safe
from ..recognition.families import FAMILIES
from ..recognition.source_registry import discovery_sources
from ..recognition.tcu_curves import scan_paired_u16_curves
from .next_dialogs import (SmartTransferDialog, LogAnalyzerDialog, MapEditorPane,
                          SurfaceEditDialog, AxisDialog, RowsModel, ModelToolsDialog)
from ..core.storage import atomic_write
from ..core.project_store import ProjectStore
from .catalogue import CatalogueModel


TIER_FILTERS=('Alle Konfidenzen','Gesichert (≥ 90 %)','Wahrscheinlich (60–90 %)','Vermutung (< 60 %)',
              'Geprüft / aus Definition')


def tier_matches(m,choice:str)->bool:
    """Catalogue filter by measured evidence tier (core/confidence.py)."""
    if choice==TIER_FILTERS[0]:return True
    if choice==TIER_FILTERS[4]:return m.verified or m.source not in ('heuristic','reference-shape','transfer-proposed','ml-proposed')
    return (m.evidence_tier or '').casefold()==choice.split(' (')[0].casefold()


class ScanWorker(QThread):
    complete = Signal(list)
    failed = Signal(str)
    progress = Signal(int)
    def __init__(self, image, signatures=None, include_u32=False):
        super().__init__()
        # snapshot as no writes should race with scanning
        materialized = image.materialize()
        self.source_digest = hashlib.sha256(materialized).digest()
        self.snapshot = BinaryImage(materialized)
        self.profile = identify_profile(self.snapshot)
        self.signatures = list(signatures or [])
        self.include_u32=include_u32
        self.report={}
    def run(self):
        try:
            candidates = scan_calibration_candidates(self.snapshot, cancelled=self.isInterruptionRequested,
                                                       progress=lambda p:self.progress.emit(p),include_u32=self.include_u32,
                                                       diagnostics=self.report)
            # Adjacent monotonic arrays are displayed as inspectable hints, NEVER as axes.
            for m in candidates[:90]:
                if m.source != 'heuristic':continue
                hints=suggest_adjacent_axes(self.snapshot,m)
                if hints:
                    details='; '.join(f'{x.axis}: 0x{x.offset:08X} ({x.dtype}, {x.endian}, Hinweiswert {x.score:.2f})' for x in hints)
                    m.notes += ' | Nachbarachsen-Kandidaten (UNGEPRÜFT): '+details
                    m.label_evidence += ' | Mögliche Achsen ohne Einheiten-/Funktionsnachweis: '+details
            # Exact reference matches take priority; weak shape matches are hints only.
            if self.signatures:
                reference_library = MapLibrary.__new__(MapLibrary)
                reference_library.signatures = self.signatures
                exact = reference_library.find(self.snapshot, max_hits=150)
                suggest_reference_shapes(self.snapshot, [m for m in candidates if m.source=='heuristic'], self.signatures)
                candidates = exact + candidates
            if not self.isInterruptionRequested():
                self.complete.emit(sorted(candidates, key=lambda x: (x.offset, x.source == 'heuristic')))
        except Exception as exc:
            self.failed.emit(str(exc))



class RecognitionWorker(QThread):
    """Run CPU-heavy firmware transfers/ML inference without freezing Qt."""
    complete = Signal(object)
    failed = Signal(str)
    def __init__(self, image, db_path, model_path, shape_path=None):
        super().__init__()
        payload = image.materialize()
        self.source_digest = hashlib.sha256(payload).digest()
        self.snapshot = BinaryImage(payload)
        self.db_path = db_path
        self.model_path = Path(model_path)
        self.shape_path = Path(shape_path) if shape_path else None

    def run(self):
        try:
            db = DefinitionCatalog(self.db_path)
            hits = match_verified(self.snapshot, db)
            if self.isInterruptionRequested():
                return
            cached_candidates=None
            def candidates_once():
                nonlocal cached_candidates
                if cached_candidates is None:
                    cached_candidates=scan_calibration_candidates(self.snapshot,cancelled=self.isInterruptionRequested)
                return cached_candidates
            proposals = []
            shape_hints = []
            profile = identify_profile(self.snapshot)
            if self.shape_path and self.shape_path.exists() and profile.identified:
                sm=ShapeModel.load(self.shape_path)
                if sm.family==profile.family and sm.software==(profile.software_version or profile.calibration_id):
                    for c in candidates_once()[:110]:
                        if self.isInterruptionRequested():return
                        if c.rows<3 or c.cols<3 or c.rows*c.cols>4096:continue
                        try:
                            values=[[self.snapshot.raw_value(c,r,x) for x in range(c.cols)] for r in range(c.rows)]
                            hit=sm.similar(values,family=profile.family,software=sm.software,max_matches=1)
                            if hit['status']=='shape-similar':
                                shape_hints.append({'offset':c.offset,'rows':c.rows,'cols':c.cols,
                                    'nearest':hit['candidates'][0]['source_name'],
                                    'distance':hit['distance'],'verified':False})
                        except (ValueError, IndexError):pass
            if self.model_path.exists():
                model = Model.load(self.model_path)
                if model.metrics.get('family')!=profile.family:
                    # Older unscoped and other-family models are NOT promoted to named maps.
                    candidates_for_model=[]
                else:
                    candidates_for_model=candidates_once()[:100]
                for candidate in candidates_for_model:
                    if self.isInterruptionRequested():return
                    try:
                        values = [[self.snapshot.raw_value(candidate,r,c)
                                   for c in range(candidate.cols)] for r in range(candidate.rows)]
                        pred = model.predict(values, family=profile.family)
                    except (ValueError, KeyError, IndexError):
                        continue
                    if pred['status'] == 'ml-proposed':
                        candidate.source = 'ml-proposed'
                        candidate.kind = pred['suggested_label']
                        candidate.name = f"ML-Vermutung: {candidate.kind} @ 0x{candidate.offset:X}"
                        candidate.label_origin = 'ML-Vorschlag – nicht fachlich geprüft'
                        candidate.label_evidence = (f"Modellscore: {pred['model_score']}; "
                            f"Alternativ: {pred['runner_up_score']}. {pred['note']}")
                        candidate.notes = candidate.label_evidence
                        candidate.verified = False
                        proposals.append(candidate)
            if not self.isInterruptionRequested():
                self.complete.emit({'transfer':hits, 'ml':proposals, 'shape':shape_hints})
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchDefinitionWorker(QThread):
    complete = Signal(object)
    failed = Signal(str)
    def __init__(self, manifest_path: str, db_path: str):
        super().__init__()
        self.manifest_path = manifest_path
        self.db_path = db_path
    def run(self):
        try:
            from types import SimpleNamespace
            from ..tools.recognition_v13 import execute
            result = execute(SimpleNamespace(catalog='batch',manifest=self.manifest_path,
                       db=self.db_path,bin=None,xdf=None,model=None))
            self.complete.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.image: BinaryImage | None = None
        self.maps: list[MapDefinition] = []
        self.bookmarks: list[dict] = []
        self.snapshots: list[dict] = []
        self.project_path: str | None = None
        self.selected: MapDefinition | None = None
        self.scanner: ScanWorker | None = None
        self.recognition_worker: RecognitionWorker | None = None
        self.batch_worker: BatchDefinitionWorker | None = None
        self.recognition_db = DefinitionCatalog()
        self.trained_model_path = Path.home()/'.ecu_studio_ai'/'trained-map-model.json'
        personal_shape=Path.home()/'.ecu_studio_ai'/'trained-shape-model.json'
        packaged_shape=Path(__file__).resolve().parents[1]/'recognition'/'data'/'ms43_430069_structure_model.json'
        self.shape_model_path = personal_shape if personal_shape.exists() else packaged_shape
        self.library = MapLibrary()
        self.saved_fingerprint = None
        self.checksum_profile = None
        self.map_editors = []
        self.project_store = ProjectStore()
        self.setWindowTitle(f"ECU Studio AI v{__version__}  |  Calibration Workbench")
        self.settings=QSettings("ECU Studio", "ECU Studio AI")
        self.theme=self.settings.value("ui/theme", "dark")
        if self.theme not in ("light","dark"): self.theme="light"
        self.actions={}
        self.theme_actions={}
        self.resize(1510,930)
        self.setMinimumSize(1100,680)
        self._build()
        self._actions()
        self._build_toolbar()
        self.set_theme(self.theme)
        try:
            geometry=self.settings.value("ui/geometry")
            state=self.settings.value("ui/state_v06")
            if geometry is not None:self.restoreGeometry(geometry)
            if state is not None:self.restoreState(state,1)
        except (TypeError,ValueError):pass
        self.statusBar().showMessage("Bereit · Originaldaten bleiben unverändert")
        self.updates.start()
        self.scan_progress=QProgressBar()
        self.scan_progress.setRange(0,100)
        self.scan_progress.setMaximumWidth(180)
        self.scan_progress.hide()
        self.statusBar().addPermanentWidget(self.scan_progress)
        self.cancel_scan=QPushButton('Analyse abbrechen')
        self.cancel_scan.clicked.connect(self.cancel_analysis)
        self.cancel_scan.hide()
        self.statusBar().addPermanentWidget(self.cancel_scan)
        self.autosave_timer=QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(120_000)

    def _build(self):
        """Native engineering workspace: persistent docks, restrained density."""
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks |
                            QMainWindow.DockOption.AllowTabbedDocks)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        # Central editor is the visual focus. Menus/toolbar sit in native Qt chrome.
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(10, 9, 10, 7)
        layout.setSpacing(7)
        titlebar=QHBoxLayout()
        self.workspace_title=QLabel('Kalibrier-Editor')
        self.workspace_title.setObjectName('workspaceTitle')
        titlebar.addWidget(self.workspace_title)
        titlebar.addStretch()
        self.source_label=QLabel('KEINE DATEI')
        self.source_label.setObjectName('fileBadge')
        titlebar.addWidget(self.source_label)
        layout.addLayout(titlebar)
        self.identity_banner=QFrame()
        self.identity_banner.setObjectName('identityBanner')
        banner=QHBoxLayout(self.identity_banner)
        banner.setContentsMargins(10,5,6,5)
        self.identity_banner_text=QLabel()
        self.identity_banner_text.setWordWrap(True)
        banner.addWidget(self.identity_banner_text,1)
        matrix_button=QPushButton('Unterstützte Steuergeräte …')
        matrix_button.clicked.connect(self.show_support_matrix)
        banner.addWidget(matrix_button)
        hide_button=QPushButton('Ausblenden')
        hide_button.clicked.connect(self.identity_banner.hide)
        banner.addWidget(hide_button)
        self.identity_banner.hide()
        layout.addWidget(self.identity_banner)
        self.tabs=QTabWidget()
        self.tabs.currentChanged.connect(self.sync_map_editor)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.hex_model=HexTableModel()
        self.hex_model.edited.connect(self.on_edited)
        self.hex_table=QTableView()
        self.hex_table.setModel(self.hex_model)
        self.hex_table.setFont(QFont('Consolas',10))
        self.hex_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hex_table.verticalHeader().setDefaultSectionSize(25)
        self.hex_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.hex_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.hex_table,'Hex-Editor')
        self.raw2d=Raw2DView(self.jump,self.define_raw_selection)
        self.tabs.addTab(self.raw2d,'2D-Rohdaten')
        self.map_model=MapTableModel()
        self.map_model.edited.connect(self.on_edited)
        self.map_table=QTableView()
        self.map_table.setModel(self.map_model)
        self.map_table.horizontalHeader().setDefaultSectionSize(86)
        self.map_table.verticalHeader().setDefaultSectionSize(29)
        self.map_table.setFont(QFont('Consolas',10))
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabs.addTab(self.map_table,'Kennfeldtabelle')
        self.curve_view=MapCurveView(self.map_model)
        self.curve_view.cellSelected.connect(self.focus_map_cell)
        self.tabs.addTab(self.curve_view,'2D-Kurven / ORI-MOD')
        self.view2d=Map2DView(self.map_model)
        self.view2d.cellSelected.connect(self.focus_map_cell)
        self.tabs.addTab(self.view2d,'Kennfeld-Heatmap')
        self.view3d=Map3DView(self.map_model)
        self.tabs.addTab(self.view3d,'3D-Ansicht')
        self.memory_atlas=MemoryAtlasView(self.jump)
        self.tabs.addTab(self.memory_atlas,'Speicheratlas')
        self.diff_view=QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont('Consolas',10))
        self.diff_view.setPlainText('Änderungsprotokoll – Noch keine Änderungen.\n'
                                    'Originaldatei wird nie direkt überschrieben.\n'
                                    'ECU-Checksummen werden nicht korrigiert.')
        self.tabs.addTab(self.diff_view,'Änderungen / Audit')
        layout.addWidget(self.tabs,1)
        self.warning_note=QLabel('Prüfstatus: Nicht flash-validiert · Prüfe Adresskopplung, Softwarestand und Checksummen.')
        self.warning_note.setObjectName('warningNote')
        layout.addWidget(self.warning_note)
        self.setCentralWidget(center)

        # Compact dock: file/map explorer with fast navigation and filters.
        left=QWidget()
        ll=QVBoxLayout(left)
        ll.setContentsMargins(9,9,9,9)
        ll.setSpacing(7)
        ll.addWidget(self._label('KENNFELDKATALOG'))
        self.filter=QLineEdit()
        self.filter.setClearButtonEnabled(True)
        self.filter.setPlaceholderText('Kennfeld, Typ oder Adresse suchen')
        self.filter.textChanged.connect(self.refresh_map_list)
        ll.addWidget(self.filter)
        filters=QHBoxLayout()
        filters.setSpacing(5)
        self.kind_filter=QComboBox()
        self.kind_filter.addItems(['Alle Typen','Mit Definition','Nur Suchkandidaten','Verifiziert','Geändert','Favoriten',*dict.fromkeys([*TYPES, *(x[0] for x in LEXICON)])])
        self.kind_filter.currentIndexChanged.connect(self.refresh_map_list)
        filters.addWidget(self.kind_filter,2)
        self.tier_filter=QComboBox()
        self.tier_filter.addItems(TIER_FILTERS)
        self.tier_filter.setToolTip('Nach gemessener Konfidenz der Beweisart filtern (Trefferquote auf Referenzdaten)')
        self.tier_filter.currentIndexChanged.connect(self.refresh_map_list)
        filters.addWidget(self.tier_filter,2)
        self.map_sort=QComboBox()
        self.map_sort.addItems(['Adresse','Name','Typ'])
        self.map_sort.setToolTip('Sortierung des Kennfeldkatalogs')
        self.map_sort.currentIndexChanged.connect(self.refresh_map_list)
        filters.addWidget(self.map_sort,1)
        ll.addLayout(filters)
        self.map_list=QListView()
        self.catalog_model=CatalogueModel(self)
        self.map_list.setModel(self.catalog_model)
        self.map_list.setUniformItemSizes(True)
        self.map_list.selectionModel().selectionChanged.connect(lambda *_:self.on_map_selection())
        self.map_list.doubleClicked.connect(lambda *_:self.open_map_tab())
        self.map_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.map_list.customContextMenuRequested.connect(self.map_context_menu)
        ll.addWidget(self.map_list,1)
        lr=QHBoxLayout()
        add=QPushButton('Neues Kennfeld')
        add.clicked.connect(self.add_map)
        lr.addWidget(add)
        remove=QPushButton('Entfernen')
        remove.clicked.connect(self.remove_map)
        lr.addWidget(remove)
        ll.addLayout(lr)
        ll.addWidget(self._label('NAVIGATION'))
        navigate=QHBoxLayout()
        self.goto=QLineEdit()
        self.goto.setPlaceholderText('Offset 0x…')
        self.goto.returnPressed.connect(self.goto_hex)
        navigate.addWidget(self.goto,2)
        jump=QPushButton('Gehe zu')
        jump.clicked.connect(self.goto_hex)
        navigate.addWidget(jump)
        ll.addLayout(navigate)
        ll.addWidget(self._label('LESEZEICHEN'))
        self.bookmark_list=QListWidget()
        self.bookmark_list.setMaximumHeight(125)
        self.bookmark_list.itemDoubleClicked.connect(self.bookmark_jump)
        ll.addWidget(self.bookmark_list)
        self.catalog_dock=QDockWidget('Kennfelder und Navigation',self)
        self.catalog_dock.setObjectName('dock_kennfelder')
        self.catalog_dock.setWidget(left)
        self.catalog_dock.setMinimumWidth(245)
        self.catalog_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                      QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                                      QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,self.catalog_dock)

        # Inspector: true engineering parameter form, scrollable in narrow layouts.
        self.right_content=QWidget()
        rr=QVBoxLayout(self.right_content)
        rr.setContentsMargins(11,11,11,11)
        rr.setSpacing(8)
        self.map_hint=QLabel('Kennfeld auswählen, um seine Definition zu bearbeiten.')
        self.map_hint.setWordWrap(True)
        self.map_hint.setObjectName('hint')
        rr.addWidget(self.map_hint)
        self.identification_label = QLabel('TYP: Nicht identifiziert')
        self.identification_label.setObjectName('identificationTitle')
        self.identification_label.setWordWrap(True)
        rr.addWidget(self.identification_label)
        self.identification_detail = QLabel('Erkennung aus A2L oder geprüften Referenzen möglich.')
        self.identification_detail.setObjectName('hint')
        self.identification_detail.setWordWrap(True)
        rr.addWidget(self.identification_detail)
        rr.addWidget(self._label('KENNFELDDEFINITION'))
        form=QFormLayout()
        form.setSpacing(7)
        self.name_edit=QLineEdit()
        form.addRow('Name',self.name_edit)
        self.type_edit=QComboBox()
        self.type_edit.setEditable(True)
        self.type_edit.addItems(list(dict.fromkeys([*TYPES, *(x[0] for x in LEXICON)])))
        form.addRow('Kategorie',self.type_edit)
        self.offset_edit=QLineEdit()
        form.addRow('Dateioffset',self.offset_edit)
        self.rows_edit=QSpinBox();self.rows_edit.setRange(1,512);self.rows_edit.setValue(16)
        form.addRow('Zeilen',self.rows_edit)
        self.cols_edit=QSpinBox();self.cols_edit.setRange(1,512);self.cols_edit.setValue(16)
        form.addRow('Spalten',self.cols_edit)
        self.dtype_edit=QComboBox();self.dtype_edit.addItems(list(FORMATS))
        form.addRow('Datentyp',self.dtype_edit)
        self.endian_edit=QComboBox();self.endian_edit.addItems(['big','little'])
        form.addRow('Bytefolge',self.endian_edit)
        self.factor_edit=QDoubleSpinBox();self.factor_edit.setDecimals(8);self.factor_edit.setRange(-1e9,1e9);self.factor_edit.setValue(1)
        form.addRow('Faktor',self.factor_edit)
        self.bias_edit=QDoubleSpinBox();self.bias_edit.setDecimals(6);self.bias_edit.setRange(-1e9,1e9)
        form.addRow('Phys. Offset',self.bias_edit)
        self.unit_edit=QLineEdit()
        self.unit_edit.setPlaceholderText('z. B. mbar, Nm, %')
        form.addRow('Einheit',self.unit_edit)
        self.verified_edit=QCheckBox('Manuell verifiziert')
        self.verified_edit.setToolTip('Erst nach fachlicher Prüfung bestätigen')
        form.addRow('Prüfung',self.verified_edit)
        rr.addLayout(form)
        apply=QPushButton('Definition übernehmen')
        apply.setObjectName('primary')
        apply.clicked.connect(self.apply_definition)
        rr.addWidget(apply)
        rerun=QPushButton('Metadaten neu klassifizieren')
        rerun.setToolTip('Bewertet Name/Beschreibung erneut; keine Klassifizierung nur anhand von Rohwerten.')
        rerun.clicked.connect(self.reclassify_maps)
        rr.addWidget(rerun)
        rr.addWidget(self._label('SCHNELLANALYSE'))
        row1=QHBoxLayout()
        for caption,fn in [('Kennfeld-Check',self.check_map),('Ähnliche suchen',self.find_twins)]:
            button=QPushButton(caption);button.clicked.connect(fn);row1.addWidget(button)
        rr.addLayout(row1)
        batch=QPushButton('Batchbearbeitung mit Vorschau')
        batch.clicked.connect(self.batch_transform)
        rr.addWidget(batch)
        self.remember_button=QPushButton('Geprüfte Referenz speichern')
        self.remember_button.clicked.connect(self.remember_signature)
        rr.addWidget(self.remember_button)
        export_values=QPushButton('Kennfeldwerte als CSV')
        export_values.clicked.connect(self.export_values)
        rr.addWidget(export_values)
        rr.addWidget(self._label('PROJEKTNOTIZEN'))
        self.notes=QPlainTextEdit()
        self.notes.setPlaceholderText('Befunde, ECU-Version, Prüfung, Aufgaben …')
        self.notes.setMinimumHeight(100)
        rr.addWidget(self.notes,1)
        rr.addWidget(self._label('DATEISTATUS'))
        self.file_info=QLabel('Keine Datei geöffnet')
        self.file_info.setWordWrap(True)
        self.file_info.setObjectName('hint')
        rr.addWidget(self.file_info)
        inspector_scroll=QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setWidget(self.right_content)
        self.inspector_dock=QDockWidget('Eigenschaften und Analyse',self)
        self.inspector_dock.setObjectName('dock_inspector')
        self.inspector_dock.setWidget(inspector_scroll)
        self.inspector_dock.setMinimumWidth(286)
        self.inspector_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                                        QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.inspector_dock)
        self.resizeDocks([self.catalog_dock,self.inspector_dock],[286,336],Qt.Orientation.Horizontal)
        self.setStatusBar(QStatusBar())
        self.stats_chip=QLabel('0 Kennfelder · 0 Änderungen')
        self.stats_chip.setObjectName('statusChip')
        self.statusBar().addPermanentWidget(self.stats_chip)
        self.checksum_chip=QLabel('CHECKSUMME: OFFEN')
        self.checksum_chip.setObjectName('statusChip')
        self.statusBar().addPermanentWidget(self.checksum_chip)

    @staticmethod
    def _label(text):
        label=QLabel(text)
        label.setObjectName('sectionTitle')
        return label

    def _build_toolbar(self):
        tool=QToolBar('Hauptwerkzeuge',self)
        tool.setObjectName('toolbar_main')
        tool.setMovable(True)
        tool.setFloatable(False)
        tool.setIconSize(QSize(18,18))
        tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea,tool)
        icons={
            'BIN öffnen …':'open',
            'Projekt speichern …':'save',
            'Gepatchte BIN exportieren …':'export',
            'Intelligente Kennfeldsuche (Struktur + Referenz)':'scan',
            'Rückgängig':'undo',
            'Wiederholen':'redo',
            'A2L / textuelles DAMOS koppeln …':'a2l',
            'TunerPro XDF mit BIN koppeln …':'xdf',
            'Schnellbefehle / Kommandopalette …':'commands',
            '2D-Rohdaten ab aktuellem Offset':'raw2d',
        }
        self.toolbar_icons={}
        groups=[
            [('BIN öffnen …','Öffnen'),('Projekt speichern …','Speichern'),('Gepatchte BIN exportieren …','Export')],
            [('A2L / textuelles DAMOS koppeln …','A2L / DAMOS'),('TunerPro XDF mit BIN koppeln …','XDF'),('Intelligente Kennfeldsuche (Struktur + Referenz)','Scan'),
             ('2D-Rohdaten ab aktuellem Offset','Roh-2D')],
            [('Rückgängig','Undo'),('Wiederholen','Redo')],
            [('Schnellbefehle / Kommandopalette …','Befehle')],
        ]
        for group_index,group in enumerate(groups):
            if group_index:tool.addSeparator()
            for title,text in group:
                act=self.actions[title]
                self.toolbar_icons[act]=icons[title]
                tool.addAction(act)
                widget=tool.widgetForAction(act)
                if widget:widget.setToolTip(title)
                act.setIconText(text)
        return tool

    def map_context_menu(self,pos):
        item=self.map_list.indexAt(pos)
        if not item.isValid():return
        self.map_list.setCurrentIndex(item)
        menu=QMenu(self)
        menu.addAction('Kennfeld öffnen',lambda:self.tabs.setCurrentWidget(self.map_table))
        menu.addAction('In eigenem Tab öffnen',self.open_map_tab)
        menu.addAction('Favorit umschalten',self.toggle_favorite)
        menu.addAction('Ordner / Gruppe festlegen …',self.set_map_folder)
        menu.addAction('Im Hex-Editor anzeigen',self.jump_selected_map)
        menu.addAction('In 2D-Rohdaten anzeigen',lambda:(self.raw2d.go_offset(self.selected.offset), self.tabs.setCurrentWidget(self.raw2d)) if self.selected else None)
        menu.addSeparator()
        menu.addAction('Kennfeld-Check',self.check_map)
        menu.addAction('Batchbearbeitung',self.batch_transform)
        menu.addAction('Offset als Lesezeichen',self.bookmark_selected_map)
        menu.exec(self.map_list.viewport().mapToGlobal(pos))

    def jump_selected_map(self):
        if self.selected:self.jump(self.selected.offset)
        self.tabs.setCurrentWidget(self.hex_table)

    def bookmark_selected_map(self):
        if self.selected:
            self.jump(self.selected.offset)
            self.bookmark()

    def set_theme(self,theme):
        if theme not in ('light','dark'):return
        self.theme=theme
        self.setStyleSheet(stylesheet(theme))
        colors=palette(theme)
        for act,name in getattr(self,'toolbar_icons',{}).items():
            # The scan is the primary action and carries the accent colour.
            act.setIcon(line_icon(name,colors['accent'] if name=='scan' else colors['text']))
        self.hex_model.dark=(theme=='dark')
        self.map_model.dark=(theme=='dark')
        for pane in self.map_editors:
            pane.model.dark=(theme=='dark')
            pane.refresh()
        self.hex_table.viewport().update()
        self.map_table.viewport().update()
        self.view2d.update()
        self.curve_view.canvas.update()
        self.raw2d.dark=(theme=='dark')
        self.raw2d.graph.update()
        self.view3d.update()
        self.memory_atlas.dark=(theme=='dark')
        self.memory_atlas.update()
        self.settings.setValue('ui/theme',theme)
        for name,act in self.theme_actions.items():act.setChecked(name==theme)

    def reset_workspace(self):
        self.catalog_dock.show();self.inspector_dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,self.catalog_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.inspector_dock)
        self.resizeDocks([self.catalog_dock,self.inspector_dock],[286,336],Qt.Orientation.Horizontal)
        self.tabs.setCurrentWidget(self.hex_table)
        self.statusBar().showMessage('Arbeitsbereich zurückgesetzt',4000)
    def _actions(self):
        menu=self.menuBar()
        file=menu.addMenu("Datei")
        tools=menu.addMenu("Werkzeuge")
        revisions=menu.addMenu("Versionen")
        view=menu.addMenu("Ansicht")
        def act(m,title,fn,shortcut=None):
            a=QAction(title,self)
            a.triggered.connect(fn)
            if shortcut: a.setShortcut(QKeySequence(shortcut))
            m.addAction(a)
            self.actions[title]=a
            return a
        act(file,"BIN öffnen …",self.open_bin,"Ctrl+O")
        act(file,"Intel HEX / Motorola S-Record importieren …",self.import_memory_records,"Ctrl+Shift+O")
        act(file,"Projekt öffnen …",self.open_project)
        act(file,"Projektdatenbank durchsuchen …",self.browse_projects,"Ctrl+Shift+D")
        act(file,"ZIP mit BIN / ORI importieren …",self.import_zip)
        act(file,"Projekt speichern …",self.save_project,"Ctrl+S")
        act(file,"Flash-Preflight prüfen …",self.flash_preflight,"Ctrl+Shift+F")
        act(file,"Gepatchte BIN exportieren …",self.export_bin,"Ctrl+Shift+S")
        act(file,"Kennfelddefinitionen importieren …",self.import_maps)
        act(file,"A2L / textuelles DAMOS koppeln …",self.import_a2l,"Ctrl+Shift+L")
        act(file,"TunerPro XDF mit BIN koppeln …",self.import_xdf,"Ctrl+Shift+X")
        act(file,"RomRaider XML mit BIN koppeln …",self.import_romraider)
        act(file,"Letzten XDF-Importbericht als CSV speichern …",self.export_xdf_audit)
        act(file,"Lokale XDF-Bibliothek durchsuchen …",self.browse_xdf_library)
        act(file,"MS43 430069-XDF aus MS4X herunterladen …",self.download_ms43_xdf)
        act(file,"Öffentliche ECU-Definitionsbibliothek …",self.public_library_dialog)
        act(file,"MS43-430069: Offline-Kennfeldvorschau (81) …",self.load_ms43_offline_preview)
        act(file,"Eigenes ECU-Map-Pack importieren …",self.open_map_pack)
        act(file,"Eigenes ECU-Map-Pack exportieren …",self.save_map_pack)
        act(file,"Kennfelddefinitionen exportieren …",self.export_maps)
        act(file,"Erkennungsbericht als CSV …",self.export_recognition)
        act(file,"Patch-Audit als CSV …",self.export_audit)
        act(file,"HTML-Änderungsbericht exportieren …",self.export_report)
        file.addSeparator()
        act(file,"Beenden",self.close)
        act(revisions,"Neuen Versionsstand festhalten …",self.create_snapshot,"Ctrl+Shift+N")
        act(revisions,"Versionsstände verwalten / Kennfeld übernehmen …",self.revisions_dialog,"Ctrl+Shift+V")
        act(tools,"Schnellbefehle / Kommandopalette …",self.command_palette,"Ctrl+Shift+P")
        act(tools,"AI Smart Map Transfer …",self.smart_transfer)
        act(tools,'Softwarestände vergleichen und Definitionen übernehmen …',self.compare_software_versions)
        act(tools,'Softwarestände: Kennfelder mathematisch abgleichen …',self.match_software_maps)
        act(tools,'Softwarestände: Namen aus Schwesterstand übernehmen …',self.transfer_sister_names)
        act(tools,"AI Log-to-Map Analyzer …",self.log_to_map)
        act(tools,"Kennfeld in eigenem Tab öffnen",self.open_map_tab,"Ctrl+Return")
        act(tools,"Ausgewählte Zellen bearbeiten …",self.edit_selected_cells)
        act(tools,"Achsen und Log-Eingangssignale …",self.edit_axes)
        act(tools,"Bearbeitungsrezept ausführen …",self.execute_recipe)
        act(tools,"Intelligente Kennfeldsuche (Struktur + Referenz)",self.scan_maps,"Ctrl+K")
        act(tools,"Funktionsgraph: zusammengehörige Kennfelder …",self.show_function_graph,"Ctrl+Shift+U")
        act(tools,"Signal-Tracing: Achseingänge aus dem Code …",self.show_signal_trace)
        self.scan32_action=act(tools,'Zusätzliche 32-Bit-Rohsuche (experimentell)',lambda checked:None)
        self.scan32_action.setCheckable(True)
        act(tools,'Letzten Erkennungsbericht als JSON speichern …',self.export_scan_report)
        act(tools,"TCU · 1D-Wortpaar-Kandidaten suchen (experimentell) …",self.scan_tcu_curves)
        tools.addSeparator()
        act(tools,"Erkennung 1/3 · Definitionen indexieren …",self.index_recognition_definitions)
        act(tools,"Erkennung 1/3 · Viele BIN/XDF-Paare importieren …",self.batch_index_definitions)
        act(tools,"Erkennung 1/3 · Ausgewähltes Kennfeld fachlich bestätigen …",self.verify_recognition_map)
        act(tools,"Erkennung 2/3 · Firmware-Transfer + Modellvorschläge …",self.run_recognition_pipeline,"Ctrl+Shift+K")
        act(tools,"Erkennung 3/3 · Lokales ML-Modell trainieren …",self.train_recognition_model)
        act(tools,"KI · Strukturmodell aus realer BIN trainieren …",self.train_structure_model_gui)
        act(tools,"KI · Modell- und Familienstatus …",self.show_learning_status)
        act(tools,"ECU · Quellen Audi / Mercedes / BMW / Opel / Lamborghini …",self.show_reference_sources)
        act(tools,"KI · Prüfqueue für unbekannte Kennfelder exportieren …",self.export_ai_review_queue)
        act(tools,"Erkennung · Datenbankstatistik",self.recognition_catalog_stats)
        act(tools,"Datenbank · Abdeckung nach Automarke …",self.show_source_coverage)
        tools.addSeparator()
        act(tools,"Exakte Referenz-Fingerprints finden",self.find_reference_maps)
        act(tools,"Unbekannte Kennfeldtypen aus Metadaten ableiten",self.reclassify_maps)
        act(tools,"Geprüftes Kennfeld in Bibliothek merken",self.remember_signature)
        act(tools,"Gehe zu Offset",self.prompt_goto,"Ctrl+G")
        act(tools,"2D-Rohdaten ab aktuellem Offset",self.show_raw2d,"Ctrl+Shift+2")
        act(tools,"Hex-Muster suchen",self.search_hex,"Ctrl+F")
        decimal=act(view,"Hex-Editor: Dezimalwerte",lambda checked:self.set_byte_radix(10 if checked else 16))
        decimal.setCheckable(True)
        act(tools,"ORI / MOD: Kennfeldvergleich mit CSV …",self.compare_file,"Ctrl+Shift+C")
        act(tools,"Fahrzeug / ECU: Fingerprint prüfen …",self.show_vehicle_identity)
        act(tools,"Fahrzeug / ECU: geprüfte Hash-Identitäten importieren …",self.import_vehicle_identities)
        act(tools,"Rückgängig",self.undo,"Ctrl+Z")
        act(tools,"Wiederholen",self.redo,"Ctrl+Y")
        act(tools,"Zum ersten geänderten Byte",self.goto_first_edit)
        act(tools,"Kennfeld-Check",self.check_map)
        act(tools,"Kennfelder automatisch gruppieren …",self.open_map_groups,"Ctrl+Shift+G")
        act(tools,"ECU-Checksummenprofil importieren …",self.load_checksum_manifest)
        act(tools,"Checksum- und Plausibilitätsprüfung …",self.open_checksum_audit,"Ctrl+Shift+Q")
        act(tools,"Checksummen korrigieren (mit Vorschau) …",self.correct_checksums)
        act(tools,"Prüfsummen-Tabellen der Datei prüfen / korrigieren …",self.correct_table_checksums)
        act(tools,"EDC17/MED17-Prüfsummenblöcke prüfen / korrigieren …",self.correct_edc17_blocks)
        act(tools,"EDC16-Prüfsummen prüfen / korrigieren …",self.correct_edc16_blocks)
        act(tools,"2D-ORI/MOD-Kurvenansicht",lambda:self.tabs.setCurrentWidget(self.curve_view))
        act(tools,"Kennfeldkatalog prüfen (Duplikate/Überlappungen)",self.inspect_catalogue)
        act(tools,"Kennfeldwerte und Achsen prüfen (CSV) …",self.audit_map_values)
        act(tools,"Speicheratlas öffnen",lambda:self.tabs.setCurrentWidget(self.memory_atlas),"Ctrl+Shift+M")
        act(tools,"Änderungs-Matrix / Impact-Explorer",self.impact_matrix,"Ctrl+Shift+I")
        act(tools,"Prüfbericht / Workflow-Check",self.workflow_check)
        act(tools,"Batchbearbeitung (Vorschau + Undo)",self.batch_transform,"Ctrl+Shift+B")
        act(tools,"Ähnliche Kennfelder",self.find_twins)
        act(tools,"Kennfeldwerte als CSV exportieren",self.export_values)
        view.addAction(self.catalog_dock.toggleViewAction())
        view.addAction(self.inspector_dock.toggleViewAction())
        view.addSeparator()
        for name,title in [("light","Hell · Präzisionslayout"),("dark","Dunkel · Werkstattlayout")]:
            theme_action=QAction(title,self)
            theme_action.setCheckable(True)
            theme_action.triggered.connect(lambda checked, t=name:self.set_theme(t))
            view.addAction(theme_action)
            self.theme_actions[name]=theme_action
        view.addSeparator()
        act(view,"Fensterlayout zurücksetzen",self.reset_workspace)
        settings_menu=menu.addMenu("Einstellungen")
        from .updates import UpdateController
        self.updates=UpdateController(self)
        auto=act(settings_menu,"Automatisch nach Updates suchen",lambda checked:self.updates.set_auto(checked))
        auto.setCheckable(True)
        auto.setChecked(self.updates.auto_enabled())
        act(settings_menu,"Jetzt nach Updates suchen",lambda:self.updates.check(manual=True))
        act(settings_menu,"Vorherige Version wiederherstellen …",self.updates.request_restore)
        settings_menu.addSeparator()
        language_menu=settings_menu.addMenu("Sprache / Language")
        from ..core import i18n
        current=self.settings.value('language','system')
        for code,label in (('system','Systemsprache / System language'),*i18n.LANGUAGES.items()):
            action=act(language_menu,label,lambda checked=False,c=code:self.set_language(c))
            action.setCheckable(True);action.setChecked(current==code)
        help_menu=menu.addMenu("Hilfe")
        act(help_menu,"Synthetische Demo-Datei erzeugen …",self.make_demo)
        act(help_menu,"A2L-Demo (14 verschiedene Kennfelder) erzeugen …",self.make_a2l_demo)
        act(help_menu,"Unterstützte Steuergeräte …",self.show_support_matrix)
        act(help_menu,"Über Erkennungsgrenzen",self.show_help)
        act(help_menu,"Definitionsquellen und Lizenzen",self.show_definition_licenses)

    def set_language(self, code: str) -> None:
        """Store the interface language; it applies after a restart (all windows are built once)."""
        self.settings.setValue('language', code)
        for action in self.findChildren(QAction):
            if action.isCheckable() and action.parent() is not None and action.text() in (
                    'Systemsprache / System language', 'Deutsch', 'English'):
                action.setChecked({'system': 'Systemsprache / System language', 'de': 'Deutsch', 'en': 'English'}[code] == action.text())
        QMessageBox.information(self, 'Sprache / Language',
                                'Die Sprache wird beim nächsten Start übernommen.\n'
                                'The language is applied the next time the program starts.')

    def require_image(self) -> bool:
        if self.image is None:
            QMessageBox.information(self,"BIN fehlt","Bitte zuerst eine BIN-Datei laden.")
            return False
        return True

    def warning(self,title,message):
        QMessageBox.warning(self,title,str(message))

    def open_bin(self):
        if not self.ok_to_replace():return
        p,_=QFileDialog.getOpenFileName(self,"ECU-Datei öffnen","","Binärdateien (*.bin *.ori *.mod *.dat);;Alle Dateien (*)")
        if not p: return
        try:
            check_raw_image(p)
            image=BinaryImage.from_file(p)
        except Exception as exc:
            self.warning("Import fehlgeschlagen",exc);return
        maps = []
        companion = Path(p).with_suffix(".maps.csv")
        if companion.is_file():
            try:
                maps = import_definitions(str(companion), image.size)
            except Exception as exc:
                self.warning("Begleitende CSV nicht importiert", exc)
        try:
            new = self.library.find(image)
            maps.extend(m for m in new if not any(self._overlaps(m, x) for x in maps))
        except Exception as exc:
            self.warning("Referenzsuche fehlgeschlagen", exc)
        # Local catalog only restores metadata indexed for the byte-identical
        # original. The user must explicitly accept the unverified pairing.
        try:
            indexed = self.recognition_db.firmware_maps(image)
        except Exception as exc:
            indexed = []
            self.statusBar().showMessage(f'Lokale Definitionsdatenbank nicht verfügbar: {exc}',6000)
        if indexed and QMessageBox.question(self,'Byteidentische Definition gefunden',
           f'{len(indexed)} indexierte Kennfelder gehören zu exakt diesem BIN-SHA-256.\n'
           'Die gespeicherte Zuordnung beweist nicht die richtige Firmware-Variante.\n'
           'Die Definitionen aus der lokalen Datenbank laden?',
           QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
           QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            existing={(m.offset,m.name,m.rows,m.cols) for m in maps}
            for m in indexed:
                if (m.offset,m.name,m.rows,m.cols) not in existing:
                    maps.append(m)
        self.load_state(image,maps,[],"",None)
        # Exact repeat of a previously user-approved BIN/XDF pairing.
        # This is deterministic reuse, not a firmware match or independent validation.
        try:
            existing_pair=lookup_pair(image)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            existing_pair=None
            self.statusBar().showMessage(f'Definitionsregister nicht verfügbar: {exc}',6000)
        if existing_pair and not maps:
            self._import_xdf_path(str(existing_pair.path), approved_reuse=True)
            return
        if not maps:
            # Only conventional local companion/library names. Parse against
            # exact in-file identity, not ECU/vehicle names or file names.
            from ..core.romraider import read_romraider
            xmls=[Path(p).with_suffix('.xml'),Path(p).parent/'ecu_defs.xml',
                  Path.home()/'.ecu_studio_ai'/'external_definitions'/'ecu_defs.xml']
            for xml in dict.fromkeys(xmls):
                if not xml.is_file():continue
                try:rr=read_romraider(xml,image)
                except Exception:continue
                if rr.maps:
                    self._import_romraider_path(str(xml));return
        # Fast local-only definition discovery: explicit opt-in, never guess
        # map labels just because a signature happened to match.
        candidates = local_xdf_candidates(
            image, Path(p).parent, Path.home()/'.ecu_studio_ai'/'external_definitions')
        if candidates and not maps:
            source = candidates[0]
            reply=QMessageBox.question(self,'Passende lokale Kennfelddefinition gefunden',
                f'Diese Datei wurde anhand von Softwarekennung und Größe als möglicher '
                f'XDF-Treffer erkannt:\n\n{source}\n\n'
                'Das ist noch KEIN Nachweis für dieselbe Firmware-/Patchvariante.\n'
                'Möchtest du die Definition jetzt VOR dem Import prüfen?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if reply==QMessageBox.StandardButton.Yes:
                self._import_xdf_path(str(source))
                return
        if maps:
            self.statusBar().showMessage(f"{len(maps)} Kennfelder aus CSV/Referenzbibliothek geladen",8000)
        elif matching_source(image):
            # Worker validates the actual linked axes before proposing tables.
            # No network/download/pairing approval or training side effects.
            self.scan_maps()
        else:
            profile=recognize_ms43(image)
            if profile.get('version'):
                QMessageBox.information(self, 'MS43 erkannt · passende XDF erforderlich',
                    f'MS43 mit Softwarestand {profile["version"]} erkannt.\n\n'
                    'Die bisherige Tabellen-Heuristik kann Kennfeldtypen nicht zuverlässig benennen.\n'
                    'Bitte Datei → TunerPro XDF mit BIN koppeln öffnen und eine passende\n'
                    'XDF desselben Softwarestands und derselben Dateigröße auswählen.\n\n'
                    'Quelle: https://github.com/ms4x-net/ms43/tree/main/definitions\n'
                    'Die Software lädt keine fremden Definitionen automatisch herunter.')
            else:
                gs20 = identify_profile(image)
                if gs20.family == 'Siemens GS20':
                    QMessageBox.information(
                        self, 'GS20-Getriebesteuerung erkannt',
                        f'Siemens GS20 · {gs20.controller}\n'
                        f'Kalibrierkennung: {gs20.calibration_id}\n'
                        f'Kalibrierdatensatz: {gs20.calibration_number or "unbekannt"}\n'
                        f'Projekt: {gs20.project_id}\n\n'
                        'Diese 64-KiB-Datei ist ein Teilabbild einer Getriebesteuerung.\n'
                        'Kennfeldnamen benötigen eine exakt passende XDF/A2L.\n'
                        'Die veröffentlichte G10C9000-XDF ist keine bestätigte\n'
                        'Definition für diese GADC9010-Kalibrierung.\n\n'
                        'Heuristische Treffer bleiben ausdrücklich unbekannt.')

    def import_memory_records(self):
        """Convert verified sparse records to a new BIN with a mapping sidecar."""
        if not self.ok_to_replace():return
        source,_=QFileDialog.getOpenFileName(self,'Intel HEX / Motorola S-Record laden','',
            'Adressdatensätze (*.hex *.ihex *.s19 *.s28 *.s37 *.srec *.mot);;Alle Dateien (*)')
        if not source:return
        try:
            memory=read_memory_file(source)
        except Exception as exc:
            self.warning('Adressdatei konnte nicht gelesen werden',exc)
            return
        summary=(f'Format: {memory.format}\n'
                 f'ECU-Adressfenster: 0x{memory.start:X} bis 0x{memory.end-1:X}\n'
                 f'Vorhandene Nutzdaten: {memory.payload_bytes:,} Byte\n'
                 f'Adresslücken: {memory.gap_bytes:,} Byte\n'
                 f'Zusammenhängende Segmente: {len(memory.segments):,}\n\n'
                 'Die BIN enthält ein zusammenhängendes Fenster ab der Basisadresse. '
                 'Die Datei .memory.json protokolliert die echten Segmente. '
                 'Gefüllte Lücken sind KEINE ECU-Originaldaten.\n\n'
                 'Fortfahren?')
        choice=QMessageBox.question(self,'Adressdaten importieren · Vorschau',summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if choice!=QMessageBox.StandardButton.Yes:return
        filler=None
        if memory.gap_bytes:
            value,ok=QInputDialog.getText(self,'Speicherlücken ausdrücklich füllen',
                f'{memory.gap_bytes:,} Byte ohne Daten. Füllbyte als 2-stelliger Hexwert (z. B. FF):',text='FF')
            if not ok:return
            candidate=value.strip().removeprefix('0x').removeprefix('0X')
            if len(candidate)!=2 or any(ch not in '0123456789ABCDEFabcdef' for ch in candidate):
                self.warning('Import abgebrochen','Exakt ein Hex-Füllbyte erwartet (00–FF).')
                return
            filler=int(candidate,16)
        suggested=str(Path(source).with_name(Path(source).stem+'_converted.bin'))
        target,_=self.save_destination(self,'Konvertierte BIN als neue Datei speichern',suggested,
            'BIN-Dateien (*.bin)')
        if not target:return
        try:
            imported=convert_to_binary(source,target,fill=filler)
            image=BinaryImage.from_file(str(imported.destination))
        except Exception as exc:
            self.warning('Speicherimport fehlgeschlagen',exc)
            return
        self.load_state(image,[],[],
            'Speicherabbild importiert von '+Path(source).name+f'\nECU-Basis: 0x{imported.base_address:X}\n'
            'Speichersegmente und künstlich gefüllte Lücken: '+imported.manifest.name,None)
        QMessageBox.information(self,'Import abgeschlossen',
            f'{imported.size:,} Byte geladen.\nImportierte ECU-Basisadresse: 0x{imported.base_address:X}\n'
            f'Segmentprotokoll: {imported.manifest.name}\n\n'
            'Für A2L-Kopplung passende Speichersegmente ausdrücklich prüfen. '
            'Die Datei wurde nicht auf ECU-Checksummen oder Flashbarkeit geprüft.')

    def load_state(self,image,maps,bookmarks,notes,project_path):
        self.last_scan_report=None
        QTimer.singleShot(0,self.update_identity_banner)
        for pane in self.map_editors:
            self.tabs.removeTab(self.tabs.indexOf(pane))
            pane.deleteLater()
        self.map_editors=[]
        self.image=image
        self.maps=maps
        self.bookmarks=bookmarks
        self.snapshots=[]
        self.project_path=project_path
        self.selected=None
        self.checksum_profile=None
        self.map_hint.setText("Kennfeld links auswählen, um Definition und Hinweise zu sehen.")
        self.notes.setPlainText(notes)
        self.hex_model.set_image(image)
        self.raw2d.set_image(image)
        self.map_model.set_map(None,None)
        self.memory_atlas.set_context(image,maps)
        self.refresh_map_list()
        self.refresh_bookmarks()
        self.update_status()
        self.diff_view.setPlainText("Noch keine Änderungen in dieser Sitzung.\nTipps: Kennfeldscan mit Strg+K, Offset-Sprung mit Strg+G, Hex-Suche mit Strg+F.")
        self.saved_fingerprint = self.project_state()
        self.statusBar().showMessage("Datei geladen · Original unverändert",5000)

    def update_status(self):
        if not self.image: return
        img=self.image
        profile = identify_profile(img)
        source_name = Path(img.path).name if img.path else 'Unbenannt'
        vehicle=identify_vehicle(img,self.recognition_db)
        label=(f'{vehicle.brand} {vehicle.model} · {vehicle.ecu}' if vehicle.level=='hash-reviewed'
               else f'{vehicle.family} (Text-Hinweis) · {source_name}' if vehicle.level=='text-hint'
               else f'{profile.family} · {source_name}' if profile.identified else source_name)
        if img.dirty_bytes and vehicle.level=='hash-reviewed':
            label+=' (Original-Fingerprint; Änderungen nicht geprüft)'
        self.source_label.setText(label[:100])
        identity = (f'\n\nSTEUERGERÄT: {profile.family}\n'
                    f'Software: {profile.software_version or "unbekannt"}\n'
                    f'Kalibrierung: {profile.calibration_id or "nicht verifiziert"}\n'
                    f'Datensatznummer: {profile.calibration_number or "nicht bekannt"}\n'
                    f'Projekt: {profile.project_id or "nicht bekannt"}\n'
                    f'{profile.advice}' if profile.identified else '\n\nSteuergerät nicht identifiziert')
        self.file_info.setText(f'Größe: {img.size:,} Bytes\nÄnderungen: {img.dirty_bytes:,} Bytes\n'
                               f'Katalogeinträge: {len(self.maps)}\nSHA-256:\n{img.digest[:16]}…'
                               + identity + chr(10) + chr(10) + self.identity_text() + f'\n\nFahrzeug-Fingerprint: {vehicle.level} · {vehicle.brand or "Marke ungeprüft"} {vehicle.model}\n{vehicle.notes}' + ('\nAchtung: Hash-Identität gilt für die ORIGINALE BIN, nicht für die Änderungen.' if img.dirty_bytes else '') + '\n\nExport: nicht auf Checksummen validiert')
        guesses=sum(m.source in ('heuristic','reference-shape','transfer-proposed','ml-proposed') for m in self.maps)
        self.stats_chip.setText(f"{len(self.maps):,} Einträge · {guesses} Suchvorschläge · {img.dirty_bytes:,} Byte geändert")
        self.statusBar().showMessage(f"{img.size:,} Bytes · {img.dirty_bytes:,} veränderte Bytes · {guesses} ungeprüfte Suchvorschläge")

    def refresh_map_list(self,*args):
        previous=self.selected
        self.map_list.selectionModel().blockSignals(True)
        query=self.filter.text().lower()
        current_categories={self.kind_filter.itemText(i) for i in range(self.kind_filter.count())}
        self.kind_filter.blockSignals(True)
        for kind in sorted({m.kind for m in self.maps} - current_categories):
            self.kind_filter.addItem(kind)
        self.kind_filter.blockSignals(False)
        category=self.kind_filter.currentText()
        tier=self.tier_filter.currentText()
        indices=list(range(len(self.maps)))
        sortby=self.map_sort.currentText()
        if sortby=='Name':indices.sort(key=lambda i:(self.maps[i].name.casefold(),self.maps[i].offset))
        elif sortby=='Typ':indices.sort(key=lambda i:(self.maps[i].kind.casefold(),self.maps[i].offset))
        else:indices.sort(key=lambda i:self.maps[i].offset)
        patch_offsets=sorted(self.image._patches) if self.image else []
        visible=[]
        for i in indices:
            m=self.maps[i]
            if query and query not in f"{m.name} {m.kind} {m.offset:x} 0x{m.offset:x} {m.offset} {m.folder}".lower():continue
            if category=="Verifiziert" and not m.verified:continue
            if category=="Mit Definition" and m.source in ('heuristic','reference-shape','transfer-proposed','ml-proposed'):continue
            if category=="Nur Suchkandidaten" and m.source not in ('heuristic','reference-shape','transfer-proposed','ml-proposed'):continue
            changed=bool(patch_offsets and (index:=bisect_left(patch_offsets,m.offset))<len(patch_offsets) and patch_offsets[index]<m.offset+m.length)
            if category=="Geändert":
                if not changed:continue
            elif category=="Favoriten":
                if not m.favorite:continue
            elif category not in ("Alle Typen", "Mit Definition", "Nur Suchkandidaten", "Verifiziert") and m.kind!=category:continue
            if not tier_matches(m,tier):continue
            visible.append(i)
        self.axis_group_index=group_index(shared_axis_groups(self.maps))
        self.catalog_model.set_context(self.maps,visible,patch_offsets,self.axis_group_index)
        for row,i in enumerate(visible):
            if self.maps[i] is previous:
                self.map_list.setCurrentIndex(self.catalog_model.index(row,0))
                break
        self.map_list.selectionModel().blockSignals(False)
        self.memory_atlas.set_context(self.image,self.maps)
        self.raw2d.set_maps(self.maps)

    def on_map_selection(self, *, show_table=True):
        item=self.map_list.currentIndex()
        if not item.isValid() or not self.image:return
        m=self.maps[item.data(Qt.ItemDataRole.UserRole)]
        self.selected=m
        self.map_model.set_map(self.image,m)
        self.raw2d.go_offset(m.offset)
        self.name_edit.setText(m.name)
        self.type_edit.setCurrentText(m.kind)
        self.offset_edit.setText(f"0x{m.offset:X}")
        self.rows_edit.setValue(m.rows)
        self.cols_edit.setValue(m.cols)
        self.dtype_edit.setCurrentText(m.dtype)
        self.endian_edit.setCurrentText(m.endian)
        self.factor_edit.setValue(m.factor)
        self.bias_edit.setValue(m.bias)
        self.factor_edit.setEnabled(not bool(m.equation))
        self.bias_edit.setEnabled(not bool(m.equation))
        self.factor_edit.setToolTip('XDF-Originalformel schreibgeschützt: ' + m.equation if m.equation else '')
        self.unit_edit.setText(m.unit)
        self.verified_edit.setChecked(m.verified)
        self.identification_label.setText(f"KENNFELDTYP: {m.kind}")
        status = ('Schreibgeschützt: nichtlineare XDF-Formel' if m.equation else 'Manuell verifiziert' if m.verified else
                  'UNGEPRÜFTER HINWEIS – fachlich bestätigen')
        alt = ('\nWeitere Möglichkeiten: ' + ', '.join(m.type_alternatives)) if m.type_alternatives else ''
        strength = (f"\nRegelstärke / Referenzwert: {m.type_score:.2f} (KEINE Wahrscheinlichkeit)"
                    if m.type_score else "")
        self.identification_detail.setText(
            f"{status} · {m.label_origin or m.source}\n{m.label_evidence or m.notes}{strength}{alt}")
        evidence="Verifiziert (manuell)" if m.verified else "NICHT verifiziert"
        extra = (f"\nECU-Adresse: 0x{m.ecu_address:X}" if m.ecu_address is not None else "")
        axes = (f"\nAchsenbeschreibung: {m.axes_info}" if m.axes_info else "")
        axes += self._shared_axis_text(m)
        math_info=(f'\nXDF-Umrechnung: {m.equation} (schreibgeschützt)' if m.equation else '')
        self.map_hint.setText(f"{evidence} · Quelle: {m.source}{extra}{axes}{math_info}\n"
            f"Struktur-Score: {m.confidence:.2f} (keine Wahrscheinlichkeit)\n{m.notes}")
        if show_table:
            self.tabs.setCurrentWidget(self.map_table)
        self.view2d.update();self.view3d.update();self.curve_view.canvas.update()

    def _shared_axis_text(self, m) -> str:
        """Shared stored axes of the selected map and its partner maps (first five)."""
        index=next((i for i,x in enumerate(self.maps) if x is m),None)
        lines=[]
        for g in getattr(self,'axis_group_index',{}).get(index,()):
            partners=[self.maps[i].name for i in g.indices if i!=index]
            more=f' (+{len(partners)-5})' if len(partners)>5 else ''
            lines.append(f'\n{g.describe()}\nTeilt die Achse mit: '+', '.join(partners[:5])+more)
        return ''.join(lines)

    def show_raw2d(self):
        """Open a raw BIN trace at the current hex cursor or selected map."""
        if not self.require_image():return
        idx=self.hex_table.currentIndex()
        if self.tabs.currentWidget() is self.hex_table and idx.isValid():
            offset=idx.row()*16+idx.column()
        else:
            offset=self.selected.offset if self.selected else self.raw2d.start
        self.raw2d.go_offset(offset)
        self.tabs.setCurrentWidget(self.raw2d)

    def define_raw_selection(self,begin,end,dtype,endian):
        """Only an explicit user-confirmed map definition; never identify map kind."""
        if not self.require_image():return
        width=FORMATS[dtype][1]
        length=(end-begin)//width
        if length <= 1:
            self.warning('Markierung zu klein','Bitte mindestens zwei Rohwerte markieren.')
            return
        # Good defaults for common array shapes, while supporting 1D tables.
        rows0=16 if length >= 256 and length % 16 == 0 and length//16<=512 else 1
        cols0=min(512,length//rows0)
        rows,ok=QInputDialog.getInt(self,'Bereich als Kennfeld',
            f'{length} markierte Rohwerte ab 0x{begin:08X} ({dtype}, {endian}).\n'
            'Anzahl Zeilen (Dimensionen fachlich prüfen):',rows0,1,512)
        if not ok:return
        cols,ok=QInputDialog.getInt(self,'Bereich als Kennfeld',
            'Anzahl Spalten (Markierung ist keine automatische Kennfelderkennung):',cols0,1,512)
        if not ok:return
        if rows*cols > length:
            self.warning('Abmessungen zu groß',
                'Das Kennfeld würde über die markierten Daten hinausreichen. '
                'Bitte kleinere Dimensionen wählen.')
            return
        name,ok=QInputDialog.getText(self,'Kennfeldname',
            'Vorläufiger Name:',text=f'Rohdaten @ 0x{begin:08X}')
        if not ok:return
        try:
            m=MapDefinition(name=name.strip() or f'Rohdaten @ 0x{begin:08X}',
                            offset=begin,rows=rows,cols=cols,dtype=dtype,endian=endian,
                            source='manual_2d',notes='Manuelle Auswahl in 2D-Rohdaten; Funktion/Skalierung nicht verifiziert.',
                            kind='Unbekannt',verified=False)
            m.validate(self.image.size)
        except ValueError as exc:
            self.warning('Kennfeld konnte nicht angelegt werden',exc);return
        self.maps.append(m)
        self.refresh_map_list()
        self.select_map(m)
        self.update_status()
        self.statusBar().showMessage(f'Definition erstellt: {m.name} · noch nicht verifiziert',7000)

    def add_map(self):
        if not self.require_image():return
        suggested_offset=0
        idx=self.hex_table.currentIndex()
        if idx.isValid():suggested_offset=idx.row()*16+idx.column()
        offset,ok=QInputDialog.getText(self,"Kennfeld anlegen","Dateioffset (dezimal oder 0x…):",text=f"0x{suggested_offset:X}")
        if not ok:return
        try:
            m=MapDefinition(name=f"Kennfeld @ {offset}",offset=parse_offset(offset))
            m.validate(self.image.size)
        except Exception as exc:
            self.warning("Ungültige Definition",exc);return
        self.maps.append(m)
        self.refresh_map_list()
        self.select_map(m)
        self.update_status()

    def select_map(self,map_, *, show_table=True):
        for i in range(self.catalog_model.rowCount()):
            item=self.catalog_model.index(i,0)
            if self.maps[item.data(Qt.ItemDataRole.UserRole)] is map_:
                self.map_list.selectionModel().blockSignals(True)
                self.map_list.setCurrentIndex(item)
                self.map_list.selectionModel().blockSignals(False)
                self.on_map_selection(show_table=show_table)
                return
        self.filter.clear();self.kind_filter.setCurrentIndex(0);self.tier_filter.setCurrentIndex(0)
        self.refresh_map_list()
        for i in range(self.catalog_model.rowCount()):
            item=self.catalog_model.index(i,0)
            if self.maps[item.data(Qt.ItemDataRole.UserRole)] is map_:
                self.map_list.selectionModel().blockSignals(True)
                self.map_list.setCurrentIndex(item)
                self.map_list.selectionModel().blockSignals(False)
                self.on_map_selection(show_table=show_table)
                return

    def remove_map(self):
        if self.selected is None:return
        ans=QMessageBox.question(self,"Definition entfernen","Nur diese Kennfelddefinition entfernen? Die BIN-Daten bleiben erhalten.")
        if ans != QMessageBox.StandardButton.Yes:return
        self.maps.remove(self.selected)
        for pane in list(self.map_editors):
            if pane.definition is self.selected:
                self.close_map_tab(pane)
        self.selected=None
        self.map_model.set_map(None,None)
        self.refresh_map_list();self.update_status()

    def apply_definition(self):
        if not self.image or not self.selected:return
        m=self.selected
        try:
            fields={"name":self.name_edit.text().strip(), "kind":self.type_edit.currentText(),
                    "offset":parse_offset(self.offset_edit.text()),"rows":self.rows_edit.value(),
                    "cols":self.cols_edit.value(),"dtype":self.dtype_edit.currentText(),
                    "endian":self.endian_edit.currentText(),"factor":self.factor_edit.value(),
                    "bias":self.bias_edit.value(),"unit":self.unit_edit.text(),
                    "verified":self.verified_edit.isChecked()}
            if m.equation and (fields['factor'] != m.factor or fields['bias'] != m.bias):
                raise ValueError('Original-XDF-Formel kann nicht durch Faktor/Offset ersetzt werden')
            proposal=MapDefinition(**{**m.asdict(), **fields})
            proposal.validate(self.image.size)
            if not proposal.name:raise ValueError("Name darf nicht leer sein")
            old_kind = m.kind
            for k,v in fields.items():setattr(m,k,v)
            m.source = 'manual'
            if old_kind != m.kind:
                m.label_origin = 'Manuelle Typzuordnung'
                m.label_evidence = 'Benutzer hat den Typ geändert; fachliche Verifizierung separat markieren.'
                m.type_alternatives = []
                m.type_score = 0.0
            # User explicitly sets verified; never derived from a heuristic score.
            self.map_model.set_map(self.image,m)
            self.refresh_map_list();self.select_map(m)
            self.statusBar().showMessage("Kennfelddefinition aktualisiert",5000)
        except Exception as exc:self.warning("Definition ungültig",exc)

    def goto_hex(self):
        if not self.require_image():return
        try:
            p=parse_offset(self.goto.text())
            if not 0<=p<self.image.size:raise ValueError("Offset außerhalb der Datei")
            self.tabs.setCurrentWidget(self.hex_table)
            idx=self.hex_model.index(p//16,p%16)
            self.hex_table.scrollTo(idx,QAbstractItemView.ScrollHint.PositionAtCenter)
            self.hex_table.setCurrentIndex(idx)
            self.statusBar().showMessage(f"Offset 0x{p:08X}",5000)
        except Exception as exc:self.warning("Offset ungültig",exc)

    def jump(self,offset):
        self.goto.setText(f"0x{offset:X}")
        self.goto_hex()

    def prompt_goto(self):
        if not self.require_image():return
        entry,ok=QInputDialog.getText(self,"Gehe zu Offset","Offset (z. B. 0xA320):")
        if ok:
            self.goto.setText(entry)
            self.goto_hex()

    def bookmark(self):
        if not self.require_image():return
        idx=self.hex_table.currentIndex()
        offset=idx.row()*16+idx.column() if idx.isValid() else 0
        label,ok=QInputDialog.getText(self,"Lesezeichen","Titel:",text=f"Notiz @ 0x{offset:X}")
        if ok:
            self.bookmarks.append({"offset":offset,"label":label})
            self.refresh_bookmarks()

    def refresh_bookmarks(self):
        self.bookmark_list.clear()
        for b in self.bookmarks:
            item=QListWidgetItem(f"☆ {b['label']} · 0x{b['offset']:X}")
            item.setData(Qt.ItemDataRole.UserRole,b["offset"])
            self.bookmark_list.addItem(item)

    def bookmark_jump(self,item):
        self.jump(item.data(Qt.ItemDataRole.UserRole))

    def search_hex(self):
        if not self.require_image():return
        text,ok=QInputDialog.getText(self,"Werte und Muster suchen",
            "Hex: 01 02 ?? 04 · Bits: bits:1010???? ???????? · Rohwert: u16le:1500 / s16be:-20")
        if not ok or not text.strip():return
        try:
            from ..core.search import bit_pattern_search,raw_value_search
            if text.casefold().startswith('bits:'):
                hits=bit_pattern_search(self.image,text.split(':',1)[1])
            elif ':' in text:
                encoding,number=text.split(':',1)
                encoding=encoding.strip().lower()
                endian='little' if encoding.endswith('le') else 'big'
                dtype=encoding[:-2] if encoding.endswith(('le','be')) else encoding
                hits=raw_value_search(self.image,int(number.strip(),0) if number.strip().lower().startswith(('0x','-0x')) else int(number),dtype,endian)
            else:
                hits=hex_pattern_search(self.image,text)
        except ValueError as exc:self.warning("Ungültige Suche",exc);return
        message=f"{len(hits)} Treffer (max. 500)\n"+"\n".join(f"0x{x:08X}" for x in hits[:80])
        self.diff_view.setPlainText("HEX-SUCHE: "+text+"\n"+message)
        self.tabs.setCurrentWidget(self.diff_view)
        if hits:
            self.goto.setText(f"0x{hits[0]:X}")
        self.statusBar().showMessage(f"Hex-Mustersuche: {len(hits)} Treffer",5000)

    def reclassify_maps(self):
        """User-invoked: never overwrite curated types or manually verified data."""
        if not self.require_image(): return
        updated = 0
        for m in self.maps:
            if m.source not in ('a2l', 'csv', 'manual', 'manual_2d') or m.verified:
                continue
            description = ''
            if m.source == 'a2l' and m.notes.startswith('A2L: '):
                description = m.notes.split('; ECU ', 1)[0].removeprefix('A2L: ')
            if label_from_metadata(m, description=description):
                updated += 1
        self.refresh_map_list()
        if self.selected is not None:self.select_map(self.selected)
        QMessageBox.information(self, 'Metadaten klassifiziert',
            f'{updated} bisher nicht zugeordnete Kennfelder haben Typvorschläge erhalten.\n'
            'Bestätigte oder manuell benannte Typen bleiben unverändert. '
            'Keine Klassifikation allein anhand von Rohwerten.')

    def export_recognition(self):
        if not self.require_image(): return
        path, _ = self.save_destination(self, 'Erkennungsbericht exportieren',
                                             'kennfeld_erkennung.csv', 'CSV-Dateien (*.csv)')
        if not path: return
        try:
            export_detection_report(path, self.maps)
            self.statusBar().showMessage(f'Erkennungsbericht gespeichert: {path}', 6000)
        except Exception as exc:
            self.warning('Export fehlgeschlagen', exc)


    def batch_index_definitions(self):
        path,_=QFileDialog.getOpenFileName(self,'BIN-/XDF-Paarliste auswählen','',
                    'JSON-Paarlisten (*.json)')
        if not path:return
        if self.batch_worker and self.batch_worker.isRunning():return
        self.batch_worker=BatchDefinitionWorker(path,str(self.recognition_db.path))
        self.batch_worker.complete.connect(self.batch_index_finished)
        self.batch_worker.failed.connect(lambda msg:self.warning('Batchindex nicht möglich',msg))
        self.batch_worker.start()
        self.statusBar().showMessage('Indexiere Definitionspaare, ohne Fahrzeugdateien zu verändern …')

    def batch_index_finished(self, report):
        failed=report['pairs']-report['successful']
        QMessageBox.information(self,'Stapelimport abgeschlossen',
            f'Importierte BIN/XDF-Paare: {report["successful"]}\n'
            f'Abgelehnte/fehlerhafte Paare: {failed}\n'
            f'Indexierte Kennfelddefinitionen: {report["indexed"]}\n\n'
            'Import ist KEINE fachliche Verifizierung. Nur bestätigte Kennfelder '
            'dürfen ML-Trainingsdaten werden.\n\n'
            'Für Einzelheiten die Paarliste mit dem CLI-Diagnosewerkzeug auswerten.')

    def public_library_dialog(self):
        """User-initiated pinned download. No background crawling or ECU upload."""
        if not self.require_image():return
        hits=public_candidates(self.recognition_db,self.image)
        if not hits:
            p=identify_profile(self.image)
            QMessageBox.information(self,'Öffentliche Definitionen',
                f'Für {p.family} · Software {p.software_version or p.calibration_id or "unbekannt"} '
                'liegt aktuell keine exakt nach Kennung und Größe zugeordnete Quelle vor.\n\n'
                f'Bibliothek: {self.recognition_db.stats()["public_sources"]} Quellen. '
                'Nicht passende GS20-/MS43-Definitionen werden NICHT angeboten.\n'
                'Weitere Dateien können über „TunerPro XDF mit BIN koppeln“ importiert werden.')
            return
        choices=[f"{item['id']} — {item['repository']} — {item['variant']}" for item in hits]
        choice,ok=QInputDialog.getItem(self,'Öffentliche Definitionsquelle',
             'Eine passende ECU-Kennung ist nur eine Vorauswahl, keine Layoutgarantie.\n'
             'Wähle die zu prüfende Original-XDF:',choices,0,False)
        if not ok:return
        selected=hits[choices.index(choice)]
        msg=(f"Quelldatei: {selected['repository']}/{selected['path']}\n"
             f"Software: {selected['software']}  ({selected['size']} Bytes)\n"
             f"Variante: {selected['variant']}\n"
             f"Lizenz: {selected['license']}\n\n"
             'Definition nach ausdrücklicher Zustimmung herunterladen, SHA-1-Git-Blob prüfen '
             'und als UNGEPRÜFTE Quelle indexieren?\n'
             'Es wird nur die XDF geladen. Die ECU-BIN wird NICHT hochgeladen. '
             'Insbesondere bei Extended Load muss der Patchstand unabhängig geprüft werden.')
        if QMessageBox.question(self,'Quellprüfung',msg,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            result=fetch_and_index(self.recognition_db,self.image,selected['id'],
                    acknowledged_variant=True)
        except Exception as exc:self.warning('Definition nicht geladen',exc);return
        QMessageBox.information(self,'Definitionsindex befüllt',
             f"{result['imported']} benannte Einträge aus der Original-XDF importiert.\n"
             f"Importquote: {result['import_coverage']:.1%}\n"
             f"Bestätigt: 0\n\n{result['notice']}\n"
             'Die anschließende Kennfeldansicht erfordert eine zweite bewusste Übernahme.')
        self._import_xdf_path(result['downloaded_xdf'])

    def load_ms43_offline_preview(self):
        if not self.require_image():return
        response=QMessageBox.question(self,'MS43-XDF-Vorschau OHNE Achsen',
            'Der lokale Katalog enthält 81 echte MS43-430069-Tabellen-Positionen '
            'aus einer Extended-Load-XDF. Er enthält in dieser Vorschau KEINE '
            'Stützstellen, keine vollständigen Strides und keinen Patchstand-Nachweis.\n\n'
            'Diese Daten dürfen NICHT als verifizierte Kalibrierdefinitionen '
            'oder flashbereite Werte benutzt werden.\n\n'
            'Die 81 Kennfeldnamen als ungeprüfte Vorschau für diese Datei übernehmen?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if response!=QMessageBox.StandardButton.Yes:return
        try:
            out=attach_ms43_preview(self.recognition_db,self.image,acknowledged_variant=True)
            entries=self.recognition_db.firmware_maps(self.image)
            have={(m.offset,m.name,m.rows,m.cols) for m in self.maps}
            added=0
            for m in entries:
                if m.source!='xdf-preview':continue
                key=(m.offset,m.name,m.rows,m.cols)
                if key in have:continue
                self.maps.append(m);have.add(key);added+=1
            self.maps.sort(key=lambda m:(m.offset,m.name))
            self.refresh_map_list();self.update_status()
            QMessageBox.information(self,'Ungeprüfte Vorschau geladen',
                f'{added} Kennfeldnamen zur Ansicht ergänzt. Keine Achsenprüfung, '
                'keine automatisierte fachliche Bestätigung. Für zuverlässige '
                'Kennfeldwerte bitte die vollständige XDF koppeln.')
        except Exception as exc:self.warning('Vorschau nicht möglich',exc)

    def recognition_catalog_stats(self):
        try:
            stats=self.recognition_db.stats()
            QMessageBox.information(self,'Kennfeld-Definitionsdatenbank',
                f'Datenbank: {self.recognition_db.path}\n\n'
                f'Firmwareabbilder: {stats["firmwares"]}\n'
                f'Definitionseinträge: {stats["definitions"]}\n'
                f'Fachlich bestätigte Einträge: {stats["verified_maps"]}\n'
                f'Öffentliche Definitionsquellen: {stats["public_sources"]}\n'
                f'Öffentliche Kennfeldmetadaten (Vorschau): {stats["public_map_hints"]}\n'
                f'Exakte manuell geprüfte ECU-Identitäten: {identity_stats(self.recognition_db)}\n\n'
                'Nur verifizierte Einträge sind Trainings- und Transferreferenzen.\n'
                'Die Datenbank speichert keine kompletten ECU-Dateien.')
        except Exception as exc:self.warning('Definitionsdatenbank',exc)

    def show_source_coverage(self):
        try:
            from ..recognition.source_registry import BRANDS
            entries=discovery_sources(self.recognition_db)
            stats=self.recognition_db.stats()
            dialog=QDialog(self)
            dialog.setWindowTitle('Datenbankabdeckung · Quellen sind keine Trainingsdaten')
            dialog.resize(800,410)
            layout=QVBoxLayout(dialog)
            label=QLabel(f'Verifizierte Kennfelder in allen ECU-Familien: {stats["verified_maps"]} | '
                         f'Gelistete Firmware-Dateien: {stats["firmwares"]} | '
                         f'Manuell geprüfte exakte Identitäten: {identity_stats(self.recognition_db)}\n'
                         'Markenspezifische Trainingsabdeckung darf aus ECU-Plattformen nicht abgeleitet werden.')
            label.setWordWrap(True);layout.addWidget(label)
            table=QTableWidget(len(BRANDS),4,dialog)
            table.setHorizontalHeaderLabels(['Marke','Öffentliche Quellen','Fachlich freigegebene Trainingspaare','Status'])
            for i,brand in enumerate(BRANDS):
                count=sum(entry['brand']==brand for entry in entries)
                for j,value in enumerate([brand,str(count),'Nicht nachgewiesen',
                    'Import geprüfter Firmware/Definition-Paare erforderlich']):
                    table.setItem(i,j,QTableWidgetItem(value))
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.resizeColumnsToContents()
            layout.addWidget(table)
            controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            controls.rejected.connect(dialog.reject)
            controls.accepted.connect(dialog.accept)
            layout.addWidget(controls)
            dialog.exec()
        except Exception as exc:self.warning('Datenbankabdeckung',exc)

    def index_recognition_definitions(self):
        if not self.require_image():return
        if self.image.dirty_bytes:
            self.warning('Originaldatei erforderlich','Zuerst unveränderte Original-BIN laden; bearbeitete Daten dürfen nicht als Referenz gelten.')
            return
        allowed=[m for m in self.maps if m.source not in
                 ('heuristic','reference-shape','transfer-proposed','ml-proposed','exact-reference')]
        if not allowed:
            QMessageBox.information(self,'Keine Definitionen','Bitte zuerst eine passende XDF, A2L oder geprüfte CSV koppeln.')
            return
        if QMessageBox.question(self,'Definitionsdatenbank befüllen',
           f'{len(allowed)} vorhandene Definitionen für EXAKT diese Firmware indexieren?\n\n'
           'Es werden keine Kennfelder als fachlich bestätigt markiert. '
           'Nur ausdrücklich geprüfte Einträge dienen als Transfer-/KI-Trainingsdaten.',
           QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
           QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            info=self.recognition_db.import_maps(self.image,allowed,origin='Desktop-Projekt: externe/manuelle Definitionen')
            QMessageBox.information(self,'Katalog aktualisiert',
                f'{info["indexed"]} Definitionen indexiert, '
                f'{len(info["rejected"])} abgelehnt.\n'
                'Noch keine neuen Kennfelder fachlich verifiziert.')
        except Exception as exc:self.warning('Katalogfehler',exc)

    def verify_recognition_map(self):
        if not self.require_image() or not self.selected:return
        if self.image.dirty_bytes:
            self.warning('Original erforderlich','Fachliche Bestätigung nur anhand einer unveränderten Originaldatei.')
            return
        m=self.selected
        matching=[r for r in self.recognition_db.records(firmware_sha=self.image.digest)
                  if r['map_json'] and self.recognition_db.key(MapDefinition(**json.loads(r['map_json'])))==self.recognition_db.key(m)]
        if not matching:
            QMessageBox.information(self,'Zuerst indexieren',
                'Erst „Definitionen indexieren“ verwenden und dann die Quellen, Achsen und Werte unabhängig prüfen.')
            return
        token,ok=QInputDialog.getText(self,'Kennfeld fachlich prüfen',
            f'{m.name}\n\nDie manuelle Kennfeldidentität, Adresse, Achsen und Skalierung '
            'müssen mit einer unabhängigen verlässlichen Referenz abgeglichen worden sein.\n'
            'Zur ausdrücklichen Bestätigung BESTÄTIGT eingeben:')
        if not ok or token.strip()!='BESTÄTIGT':return
        try:
            self.recognition_db.verify(matching[0]['id'],self.image,confirm=True)
            m.verified=True
            self.refresh_map_list()
            QMessageBox.information(self,'Referenz bestätigt',
                'Dieser Eintrag kann jetzt als Referenz für Firmware-Transfer und ML-Training dienen. '
                'Seine Korrektheit hängt von deiner fachlichen Prüfung ab.')
        except Exception as exc:self.warning('Bestätigung fehlgeschlagen',exc)

    def export_ai_review_queue(self):
        if not self.require_image():return
        if not self.shape_model_path.exists():
            QMessageBox.information(self,'Kein Strukturmodell','Zuerst ein Modell trainieren bzw. laden.')
            return
        file,_=self.save_destination(self,'Prüfqueue speichern','ecu-review-queue.json','JSON (*.json)')
        if not file:return
        try:
            from ..recognition.review import review_queue
            model=ShapeModel.load(self.shape_model_path)
            report=review_queue(self.image,self.recognition_db,model)
            Path(file).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            QMessageBox.information(self,'Prüfqueue gespeichert',
                f'{len(report.get("queue",[]))} unbenannte Kennfeldkandidaten gespeichert.\n'
                'Die Kandidaten werden NICHT als verifiziert oder trainierbar markiert.')
        except Exception as exc:self.warning('Prüfqueue',exc)

    def show_learning_status(self):
        info=[]
        if self.shape_model_path.exists():
            try:
                shape=ShapeModel.load(self.shape_model_path)
                info.append(f'Strukturmodell: {shape.family} / {shape.software}\n'
                            f'Echte Strukturproben: {shape.count}\n'
                            'Zuverlässige Kennfeld-Typklassifizierung: NEIN\n'
                            'Andere ECU-Familien: keine Übertragung')
            except Exception as e:info.append('Strukturmodell fehlerhaft: '+str(e))
        else:info.append('Noch kein Strukturmodell vorhanden')
        info.append('Unterstützte Datenaufnahmefamilien: '+', '.join(FAMILIES))
        info.append('Für MD1/MG1: explizite SW-ID, passende A2L/XDF und unabhängige Kennfeldprüfung nötig.')
        QMessageBox.information(self,'Trainingsstand / ECU-Familien','\n\n'.join(info))

    def show_reference_sources(self):
        """Inspectable external reference index, never installed as training truth."""
        try:
            entries=discovery_sources(self.recognition_db)
            dialog=QDialog(self)
            dialog.setWindowTitle('ECU-Quellenverzeichnis – ungeprüft')
            dialog.resize(860,570)
            layout=QVBoxLayout(dialog)
            layout.addWidget(QLabel('Nur recherchierte Definitionen/Plattformhinweise. '
                                    'Keine automatische BIN-Zuordnung, keine geprüften ML-Labels.'))
            text=QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText('\n\n'.join(
                f"{x['brand']} | {x['family']} | {x['status']}\n"
                f"Variante: {x['ecu_variant']}\n"
                f"Softwarehinweis: {x['software_hint'] or 'nicht bekannt'}\n"
                f"Quelle: {x['url'] or 'kein geprüfter Download'}\n"
                f"Git-Hash: {x['git_blob_sha1'] or 'nicht vorhanden'}\n"
                f"Rechte: {x['rights']}" for x in entries))
            layout.addWidget(text)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(dialog.reject)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            dialog.exec()
        except Exception as exc:self.warning('Quellenregister nicht verfügbar',exc)

    def train_structure_model_gui(self):
        if not self.require_image():return
        if self.image.dirty_bytes:
            self.warning('Original erforderlich','Bitte unveränderte Originaldatei öffnen.')
            return
        if QMessageBox.question(self,'Strukturerkennung trainieren',
            'Aus den mit dieser BIN verknüpften, quellbasierten Kennfeldhinweisen wird ein '
            'nicht überwachtes, lokales Strukturmodell trainiert.\n'
            'Es lernt KEINE sicheren Funktionsnamen und erhält KEINE Fahrzeugfreigabe.\n\n'
            'Trotzdem trainieren?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            model=train_shape_model(self.recognition_db,self.image)
            destination=Path.home()/'.ecu_studio_ai'/'candidate-shape-model.json'
            model.save(destination)
            QMessageBox.information(self,'Strukturmodell gespeichert',
                f'Gespeichert: {destination}\nEchte Kennfeldproben: {model.count}\n'
                'Inaktiver Kandidat: Strukturelle Vorschläge sind keine überprüften Namen. Unabhängiger Vergleich noch erforderlich.')
        except Exception as e:self.warning('Nicht genug Daten',e)

    def train_recognition_model(self):
        ModelToolsDialog(self).exec()

    def run_recognition_pipeline(self):
        if not self.require_image():return
        if self.recognition_worker and self.recognition_worker.isRunning():return
        if self.image.dirty_bytes:
            self.warning('Original erforderlich','Erkennung bitte mit unveränderter Originaldatei durchführen.')
            return
        self.recognition_worker=RecognitionWorker(self.image,self.recognition_db.path,self.trained_model_path,self.shape_model_path)
        self.recognition_worker.complete.connect(self.recognition_pipeline_finished)
        self.recognition_worker.failed.connect(lambda msg:self.warning('Erkennung fehlgeschlagen',msg))
        self.scan_progress.setRange(0,0)
        self.scan_progress.show()
        self.cancel_scan.show()
        self.recognition_worker.finished.connect(self.scan_progress.hide)
        self.recognition_worker.finished.connect(self.cancel_scan.hide)
        self.recognition_worker.start()
        self.statusBar().showMessage('Vergleiche mit bestätigten Kennfeldern und trainiertem Modell …')

    def recognition_pipeline_finished(self,result):
        worker=self.recognition_worker
        if not worker or not self.image or hashlib.sha256(self.image.materialize()).digest()!=worker.source_digest:
            self.statusBar().showMessage('Erkennung verworfen: Datei zwischenzeitlich geändert',6000)
            return
        transfers=result['transfer']
        uniquely=[h.proposed for h in transfers if h.uniquely_located]
        ml=result['ml']
        shape=result.get('shape',[])
        note='\n'.join(f'{h.source_name} → 0x{h.proposed.offset:X}: '
              f'{h.score:.3f}, eindeutig={"ja" if h.uniquely_located else "nein"}'
              for h in transfers[:12])
        answer=QMessageBox.question(self,'Mehrstufige Kennfelderkennung',
            f'Externe Referenztreffer: {len(transfers)}\n'
            f'Davon räumlich eindeutig: {len(uniquely)}\n'
            f'ML-Hypothesen: {len(ml)}\n'
            f'Nur strukturelle Ähnlichkeit (OHNE Namen): {len(shape)}\n\n'
            f'{note}\n\n'
            'Eindeutige Transfer- und ML-Typvorschläge als UNGEPRÜFT zum Katalog hinzufügen?\n'
            'Es werden keine ECU-Daten verändert.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        added=0
        for m in uniquely+ml:
            if any(self._overlaps(m,existing) and existing.source not in
                   ('heuristic','reference-shape') for existing in self.maps):continue
            # Never replace authoritative definitions with a guess.
            self.maps=[old for old in self.maps if not
                       (old.source in ('heuristic','reference-shape') and self._overlaps(m,old))]
            m.verified=False
            self.maps.append(m);added+=1
        self.maps.sort(key=lambda m:m.offset)
        self.refresh_map_list();self.update_status()
        QMessageBox.information(self,'Vorschläge eingefügt',
            f'{added} ungeprüfte Vorschläge übernommen.\n'
            'Die Quelle und Unsicherheit stehen im Kennfeldinspektor. '
            'Vorgeschlagene Achsen/Skalierungen niemals ungeprüft für Fahrzeugänderungen verwenden.')

    def scan_tcu_curves(self):
        """Opt-in search for generic packed (X,Y) curves in TCU binary data.

        Proposed addresses/units remain unverified. Original bytes unchanged.
        """
        if not self.require_image():return
        if self.image.size>16*1024*1024:
            self.warning('TCU-Scan','Maximal 16 MiB für diese experimentelle 1D-Suche.')
            return
        try:
            candidates=scan_paired_u16_curves(BinaryImage(self.image.materialize()))
        except (ValueError,IndexError,MemoryError) as exc:
            self.warning('TCU-Suche fehlgeschlagen',str(exc))
            return
        if not candidates:
            QMessageBox.information(self,'TCU-1D-Kandidaten',
                'Keine passenden 16-Bit-Wortpaarfolgen mit Endmarker gefunden. '
                'Das schließt echte TCU-Kennfelder ausdrücklich NICHT aus.')
            return
        answer=QMessageBox.question(self,'TCU-1D-Kandidaten',
            f'{len(candidates)} rein strukturelle 1D-Kandidaten gefunden.\n'
            'Diese experimentelle Suche ist von veröffentlichten Wortpaar-Formaten inspiriert, '
            'keine bestätigte Erkennung eines Getriebesteuergeräts.\n\n'
            'Alle Treffer ungeprüft in den Kennfeldkatalog übernehmen? (BIN bleibt unverändert)',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        existing={(m.offset,m.rows,m.cols,m.dtype,m.endian) for m in self.maps}
        added=0
        for m in candidates:
            key=(m.offset,m.rows,m.cols,m.dtype,m.endian)
            if key in existing or any(x.source not in ('heuristic','tcu-pair-heuristic')
                                      and self._overlaps(x,m) for x in self.maps):continue
            self.maps.append(m);existing.add(key);added+=1
        self.maps.sort(key=lambda m:m.offset)
        self.refresh_map_list();self.update_status()
        QMessageBox.information(self,'TCU-1D-Kandidaten',
            f'{added} ungeprüfte 1D-Kurvenvorschläge übernommen.\n'
            'Einheiten, Skalierungen und tatsächliche Kennfeldfunktionen sind unbekannt.')

    def scan_maps(self):
        if not self.require_image():return
        if self.scanner and self.scanner.isRunning():return
        self.last_scan_report=None
        self.statusBar().showMessage("Scanne BIN: Definitionsachsen, Datentypen und Strukturen …")
        self.scanner=ScanWorker(self.image, self.library.signatures,include_u32=self.scan32_action.isChecked())
        self.scanner.complete.connect(self.scan_finished)
        self.scanner.failed.connect(lambda err: self.warning("Scan fehlgeschlagen",err))
        self.scanner.progress.connect(self.scan_progress.setValue)
        self.scan_progress.setRange(0,100)
        self.scan_progress.setValue(0)
        self.scan_progress.show()
        self.cancel_scan.show()
        self.scanner.finished.connect(self.scan_progress.hide)
        self.scanner.finished.connect(self.cancel_scan.hide)
        self.scanner.start()

    def scan_finished(self, candidates):
        if not self.image or not self.scanner or hashlib.sha256(self.image.materialize()).digest()!=self.scanner.source_digest:
            self.statusBar().showMessage("Scan verworfen: Datei oder Änderungen währenddessen gewechselt",7000)
            return
        self.last_scan_report=getattr(self.scanner,'report',{})
        # A new scan replaces old unconfirmed guesses. Otherwise a corrected
        # detector leaves exactly the misleading saved u32 maps in the catalogue.
        removed=[m for m in self.maps if m.source=='heuristic' and not m.verified
                 and not m.label_origin.startswith('Manuelle')]
        removed_ids={id(m) for m in removed}
        previous_offset=self.selected.offset if self.selected else None
        for pane in list(self.map_editors):
            if id(pane.definition) in removed_ids:self.close_map_tab(pane)
        if self.selected and id(self.selected) in removed_ids:
            self.selected=None
            self.map_model.set_map(None,None)
        self.maps=[m for m in self.maps if id(m) not in removed_ids]
        old={(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name) for m in self.maps}
        preserved=tuple(self.maps)
        incoming_references=[]
        added=0
        reference_hits=0
        shape_hints=0
        for m in sorted(candidates,key=lambda m:(m.source=='heuristic',m.source!='exact-reference',m.offset)):
            # Existing curated/CSV maps win over overlapping guesses.
            if any((x.source != 'heuristic' or x.verified or x.label_origin.startswith('Manuelle'))
                   and self._overlaps(m,x) for x in preserved):
                continue
            if any(self._overlaps(m,x) for x in incoming_references):
                continue
            # A verified/curated reference gets priority over existing guesses.
            if m.source != 'heuristic':
                old_guesses=[x for x in self.maps if x.source=='heuristic' and not x.verified
                             and not x.label_origin.startswith('Manuelle') and self._overlaps(m,x)]
                for guess in old_guesses:
                    if self.selected is guess:
                        self.selected = None
                        self.map_model.set_map(None,None)
                    old.discard((guess.offset,guess.rows,guess.cols,guess.dtype,guess.endian,guess.name))
                    self.maps.remove(guess)
            key=(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name)
            if key not in old:
                self.maps.append(m);old.add(key);added+=1
                reference_hits += (m.source == 'exact-reference')
                shape_hints += (m.label_origin == 'Referenzform (ungeprüft)')
                if m.source=='exact-reference':incoming_references.append(m)
        self.maps.sort(key=lambda m:m.offset)
        self.refresh_map_list()
        if previous_offset is not None and self.selected is None:
            replacement=next((m for m in self.maps if m.offset<=previous_offset<m.offset+m.length),None)
            if replacement:self.select_map(replacement)
        self.update_status()
        defined=sum(m.source=='bundled-definition' for m in candidates)
        QMessageBox.information(self,"Kandidaten-Scan abgeschlossen",
           f"{len(candidates)} Kandidaten/Referenzen, davon {added} neu.\n"
           f"Definitionsbasierte Tabellen/Kennlinien: {defined}.\n"
           f"Alte ungeprüfte Strukturvorschläge ersetzt: {len(removed)}.\n"
           f"Exakte Referenztreffer: {reference_hits} · Formhinweise: {shape_hints}.\n\n"
           "Typ und Nachweis stehen direkt im Kennfeldkatalog und rechts im Inspektor.\n"
           "Mitgelieferte MS4X-Standarddefinitionen bleiben ungeprüfte Zuordnungen; "
           "Patchvarianten wie Extended Load benötigen ihre eigene XDF. "
           "Eine Funktionszuordnung allein aus BIN-Rohwerten ist unzuverlässig. "
           "Typ, Skalierung, Achsen, Offsets und Checksummen müssen unabhängig geprüft werden. "
           "Viele echte Kennfelder werden möglicherweise nicht erkannt.")

    def undo(self):
        if self.image and self.image.undo():self.on_edited()

    def export_scan_report(self):
        report=getattr(self,'last_scan_report',None)
        if not report:
            QMessageBox.information(self,'Erkennungsbericht','Zuerst einen Kennfeldscan abschließen.');return
        path,_=self.save_destination(self,'Erkennungsbericht speichern','erkennung.json','JSON (*.json)')
        if path:
            try:atomic_write(path,json.dumps(report,indent=2,ensure_ascii=False).encode('utf-8'),
                             protected=(self.image.path if self.image else None,))
            except Exception as exc:self.warning('Erkennungsbericht nicht gespeichert',exc)

    def redo(self):
        if self.image and self.image.redo():self.on_edited()

    def on_edited(self):
        # Virtual HEX model reads the patch overlay lazily. Repaint visible rows only;
        # sending a multi-million-row dataChanged range freezes large BINs.
        self.hex_table.viewport().update()
        self.map_model.refresh()
        for pane in self.map_editors:
            pane.refresh()
        self.view2d.update();self.view3d.update();self.curve_view.canvas.update();self.memory_atlas.update();self.raw2d.invalidate()
        self.update_status()
        self.refresh_map_list()
        self.update_diff()

    def update_diff(self):
        if not self.image:return
        ranges=self.image.changed_ranges()
        out=[f"PATCH AUDIT · {self.image.dirty_bytes} geänderte Bytes · {len(ranges)} zusammenhängende Blöcke", "", "ORIGINALDATEI BLEIBT UNVERÄNDERT", ""]
        for pos,a,b in ranges[:120]:
            out.append(f"@0x{pos:08X} | {len(a)} Bytes")
            out.append("  ORI  "+a[:48].hex(" ").upper()+(" …" if len(a)>48 else ""))
            out.append("  MOD  "+b[:48].hex(" ").upper()+(" …" if len(b)>48 else ""))
        if len(ranges)>120:out.append(f"… weitere {len(ranges)-120} Blöcke; CSV exportieren für vollständiges Audit")
        out.extend(['','SITZUNGSVERLAUF (letzte 30 Ereignisse; vollständig in der Projektdatei)'])
        for entry in self.image.journal[-30:]:
            out.append(f"{entry.get('utc','')} · {entry.get('label','Bearbeitung')} · {len(entry.get('changes',[]))} Byte-Einträge")
        self.diff_view.setPlainText("\n".join(out))

    def goto_first_edit(self):
        if self.image and self.image._patches:self.jump(min(self.image._patches))

    def show_vehicle_identity(self):
        if not self.require_image():return
        try:
            info=identify_vehicle(self.image,self.recognition_db)
            lines=[f'Erkennungsstufe: {info.level}',
                   f'Marke: {info.brand or "nicht bestätigt"}',
                   f'Fahrzeugmodell: {info.model or "nicht bestätigt"}',
                   f'Motor: {info.engine or "nicht bestätigt"}',
                   f'Steuergerät: {info.ecu or "nicht bestätigt"}',
                   f'ECU-Familie: {info.family}',f'Software: {info.software or "unbekannt"}',
                   '', 'Beweiskette:',*(f'• {item}' for item in info.evidence),'',info.notes]
            QMessageBox.information(self,'Fahrzeug- und ECU-Identifikation','\n'.join(lines))
        except Exception as e:self.warning('Identifikationsfehler',e)

    def import_vehicle_identities(self):
        path,_=QFileDialog.getOpenFileName(self,'Geprüfte Firmware-Identitäten importieren','',
                                          'JSON Manifest (*.json);;Alle Dateien (*)')
        if not path:return
        if QMessageBox.question(self,'Identitätsdatenbank',
            'Einlesen ausschließlich manuell überprüfter Fahrzeugmetadaten.\n'
            'Jeder Datensatz braucht eine lokal vorhandene BIN mit exakt passendem SHA-256.\n'
            'Keine Fahrzeugdaten werden allein aus ECU-Familien abgeleitet. Importieren?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            result=import_identity_manifest(self.recognition_db,path,require_files=True)
            self.update_status()
            QMessageBox.information(self,'Import erfolgreich',
                f'{result["processed"]} geprüfte Hash-Identitäten eingelesen.\n'
                'Keine vollständigen Firmwareabbilder in SQLite gespeichert.')
        except Exception as e:self.warning('Identitätsimport fehlgeschlagen',e)

    def compare_file(self):
        if not self.require_image():return
        p,_=QFileDialog.getOpenFileName(self,'Zweite BIN/ORI/MOD für Zellvergleich wählen','',
                                       'Binärdateien (*.bin *.ori *.mod *.dat);;Alle Dateien (*)')
        if not p:return
        try:
            check_raw_image(p)
            second=BinaryImage.from_file(p)
            report=compare_images(self.image,second,self.maps)
        except Exception as exc:self.warning('ORI/MOD Vergleich nicht möglich',exc);return
        dialog=QDialog(self);dialog.setWindowTitle('ORI / MOD: Kennfeldbezogener Vergleich (schreibgeschützt)')
        dialog.resize(1040,650)
        layout=QVBoxLayout(dialog)
        source=Path(self.image.path).name if self.image.path else 'Aktueller Dateiinhalt'
        caption=(f'AKTIV: {source}  |  VERGLEICH: {Path(p).name}\n'
            f'Änderungen: {report["changed_bytes"]:,} Bytes, {report["changed_ranges_count"]:,} Blöcke, '
            f'{report["maps_changed"]}/{report["maps_total"]} bekannte Kennfelder betroffen, '
            f'{report["changed_bytes_outside_maps"]:,} Bytes außerhalb aller zugeordneten Tabellen.\n'
            +report['identity_warning']+'\nBei sehr vielen Deltas werden Zell-/Bereichslisten begrenzt; Zusammenfassungszahlen bleiben exakt.')
        lbl=QLabel(caption);lbl.setWordWrap(True);layout.addWidget(lbl)
        table=QTableWidget(dialog)
        columns=('Offset','Kennfeld','Geänderte Zellen','Geänderte Bytes','Max. Δ Roh','Max. Δ physisch','Max. Δ %','Herkunft')
        table.setColumnCount(len(columns));table.setHorizontalHeaderLabels(columns)
        report['maps'].sort(key=lambda m:(-m['changed_cells'],m['offset']))
        table.setRowCount(len(report['maps']))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for idx,row in enumerate(report['maps']):
            vals=(f'0x{row["offset"]:08X}',row['name'],
                f'{row["changed_cells"]}/{row["total_cells"]}',str(row['changed_bytes']),
                str(row['max_abs_raw_delta']),str(row['max_abs_physical_delta']),
                str(row['max_relative_percent']) if row['max_relative_percent'] is not None else '–',row['provenance'])
            for j,value in enumerate(vals):
                item=QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole,row['offset'])
                table.setItem(idx,j,item)
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        tabs=QTabWidget(dialog)
        tabs.addTab(table,'Kennfelder')
        cells=QTableWidget(dialog)
        detail_fields=('map_name','cell_offset','row','col','raw_before','raw_after','physical_before','physical_after','unit')
        cells.setColumnCount(len(detail_fields))
        cells.setHorizontalHeaderLabels(('Kennfeld','Offset','Zeile','Spalte','ORI roh','MOD roh','ORI phys.','MOD phys.','Einheit'))
        cells.setRowCount(min(3000,len(report['cell_changes'])))
        cells.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for ridx,cell in enumerate(report['cell_changes'][:3000]):
            for cidx,key in enumerate(detail_fields):
                cells.setItem(ridx,cidx,QTableWidgetItem(str(cell[key])))
        cells.horizontalHeader().setStretchLastSection(True)
        cells.resizeColumnsToContents()
        tabs.addTab(cells,'Geänderte Zellen'+(' (Ausschnitt)' if report['cell_changes_truncated'] or len(report['cell_changes'])>3000 else ''))
        regions=report.get('unmapped_regions',[])
        outside=QTableWidget(dialog)
        outside.setColumnCount(3);outside.setHorizontalHeaderLabels(('Offset','Länge (Bytes)','Geänderte Bytes'))
        outside.setRowCount(len(regions))
        outside.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        outside.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for ridx,r in enumerate(regions):
            for cidx,value in enumerate((f'0x{r["offset"]:08X}',str(r['length']),str(r['changed_bytes']))):
                outside.setItem(ridx,cidx,QTableWidgetItem(value))
        outside.horizontalHeader().setStretchLastSection(True)
        outside.cellDoubleClicked.connect(lambda r,c:(dialog.accept(),self.jump(regions[r]['offset'])))
        tabs.addTab(outside,f'Außerhalb bekannter Kennfelder ({len(regions)})')
        heat=QTableWidget(dialog)
        heat.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        heat_label=QLabel('Kennfeld in der Liste wählen: Änderung je Zelle (MOD − ORI, roh). Rot = höher, Blau = niedriger.')
        heat_box=QWidget(dialog);heat_layout=QVBoxLayout(heat_box);heat_layout.addWidget(heat_label);heat_layout.addWidget(heat)
        tabs.addTab(heat_box,'Differenz-Heatmap')
        by_offset={m.offset:m for m in self.maps}
        def show_heat():
            row=table.currentRow()
            if row<0:return
            m=by_offset.get(report['maps'][row]['offset'])
            if m is None:return
            try:d=delta_matrix(self.image,second,m)
            except (ValueError,IndexError) as exc:heat_label.setText(f'Keine Heatmap: {exc}');return
            peak=float(np.max(np.abs(d))) or 1.
            heat.setRowCount(d.shape[0]);heat.setColumnCount(d.shape[1])
            for r in range(d.shape[0]):
                for c in range(d.shape[1]):
                    v=float(d[r,c]);item=QTableWidgetItem('' if v==0 else f'{v:+g}')
                    k=int(200*abs(v)/peak)
                    if v>0:item.setBackground(QColor(255,255-k,255-k))
                    elif v<0:item.setBackground(QColor(255-k,255-k,255))
                    heat.setItem(r,c,item)
            heat.resizeColumnsToContents()
            heat_label.setText(f'{m.name}: {int(np.count_nonzero(d))} von {d.size} Zellen geändert, '
                               f'größte Änderung {peak:g} (roh). Rot = höher, Blau = niedriger.')
        table.itemSelectionChanged.connect(show_heat)
        layout.addWidget(tabs)
        def jump_to_row():
            row=table.currentRow()
            if row<0:return
            target=report['maps'][row]['offset'];dialog.accept();self.jump(target)
        table.cellDoubleClicked.connect(lambda r,c:jump_to_row())
        buttons=QHBoxLayout()
        jump_button=QPushButton('Zum Kennfeld springen')
        jump_button.clicked.connect(jump_to_row);buttons.addWidget(jump_button)
        export_button=QPushButton('Alle Kennfelddifferenzen als CSV …')
        def save_csv():
            target,_=self.save_destination(dialog,'Kennfeldvergleich exportieren',
                'ECU_ORI_MOD_Vergleich.csv','CSV (*.csv)')
            if target:
                try:export_map_comparison_csv(report,target)
                except Exception as exc:self.warning('Export fehlgeschlagen',exc)
        export_button.clicked.connect(save_csv);buttons.addWidget(export_button)
        cells_button=QPushButton('Zelländerungen als CSV …')
        def save_cells():
            target,_=self.save_destination(dialog,'Zellvergleich exportieren',
                'ECU_ORI_MOD_Zellen.csv','CSV (*.csv)')
            if target:
                try:export_cell_comparison_csv(report,target)
                except Exception as exc:self.warning('Zellexport fehlgeschlagen',exc)
        cells_button.clicked.connect(save_cells);buttons.addWidget(cells_button)
        buttons.addStretch()
        close=QPushButton('Schließen');close.clicked.connect(dialog.accept);buttons.addWidget(close)
        layout.addLayout(buttons);dialog.exec()

    def import_xdf(self):
        """Import externally supplied TunerPro definition as evidence, never autodetect meaning from raw bytes."""
        if not self.require_image():return
        path,_=QFileDialog.getOpenFileName(self,'Passende TunerPro-XDF importieren','',
                                           'TunerPro-Definition (*.xdf);;Alle Dateien (*)')
        if not path:return
        # Parse the header before judging compatibility. Filenames can be
        # user-renamed; matching profile evidence is checked after import.
        self._import_xdf_path(path)

    def browse_xdf_library(self):
        if not self.require_image():return
        directory=QFileDialog.getExistingDirectory(self,'XDF-Bibliothek auswählen',str(Path.home()))
        if not directory:return
        results=search_local_xdfs(self.image,[directory],max_files=500)
        if not results:
            QMessageBox.information(self,'Keine XDF-Dateien','Keine unterstützten lokalen XDF-Dateien gefunden.')
            return
        # Dialog keeps the original path in item data and labels uncertain matches.
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QLabel
        dialog=QDialog(self);dialog.setWindowTitle('Kennfelddefinition auswählen (nicht automatisch freigegeben)')
        dialog.resize(840,460);layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(f'{len(results)} mögliche XDF-Dateien. Nur eine manuell geprüfte Datei übernehmen.'))
        widget=QListWidget(dialog)
        for path,status,explanation in results:
            item=QListWidgetItem(f'[{status}]  {path.name}   —  {path.parent}')
            item.setToolTip(explanation)
            item.setData(Qt.ItemDataRole.UserRole,str(path))
            widget.addItem(item)
        layout.addWidget(widget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        widget.itemDoubleClicked.connect(lambda item:dialog.accept())
        if dialog.exec()==QDialog.DialogCode.Accepted and widget.currentItem():
            self._import_xdf_path(widget.currentItem().data(Qt.ItemDataRole.UserRole))

    def download_ms43_xdf(self):
        """User-triggered, hash-verified download of an external GPLv3 reference."""
        if not self.require_image():return
        profile=recognize_ms43(self.image)
        if profile.get('version')!='430069' or self.image.size!=524288:
            self.warning('Kein passender MS43-Vollread',
                         'Diese Funktion ist ausschließlich für erkannte MS43 430069-Dateien '
                         'mit 512 KiB gedacht. Für andere Versionen eine passende XDF manuell auswählen.')
            return
        url=('https://raw.githubusercontent.com/ms4x-net/ms43/main/definitions/'
             'Siemens_MS43_430069_Extended_Load_512K.xdf')
        expected_git_sha='9b76a7f9887cd4bc2fafe50c9313f01e7d9ca4e0'
        notice=('Lade die öffentliche GPL-3.0-Definition von ms4x-net/ms43 herunter?\n\n'
                'WICHTIG: Es handelt sich um eine EXTENDED-LOAD-XDF. '
                'Ohne überprüfte Übereinstimmung mit deiner konkreten Software-/Patchvariante '
                'sind Adressen und Skalierungen NICHT sicher validiert.\n\n'
                'Die Datei bleibt lokal, die Firmware wird nicht hochgeladen.\n\n'
                'Quelle: '+url+'\nGPL-3.0: https://github.com/ms4x-net/ms43/blob/main/LICENSE')
        if QMessageBox.question(self,'Externe XDF herunterladen · Variantenvorbehalt',notice,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'ECU-Studio-AI/0.8'})
            with urllib.request.urlopen(request,timeout=18) as response:
                payload=response.read(6*1024*1024+1)
            if not 1000<len(payload)<=6*1024*1024:
                raise ValueError('Ungewöhnliche XDF-Dateigröße')
            git_sha=hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()
            if git_sha!=expected_git_sha:
                raise ValueError('Referenzdatei wurde seit der geprüften Version verändert. '
                                 'Download abgebrochen; überprüfe eine neuere XDF manuell.')
            dest=Path.home()/'.ecu_studio_ai'/'external_definitions'
            dest.mkdir(parents=True,exist_ok=True)
            target=dest/'Siemens_MS43_430069_Extended_Load_512K.xdf'
            target.write_bytes(payload)
        except Exception as exc:
            self.warning('XDF-Download fehlgeschlagen',exc)
            return
        self._import_xdf_path(str(target))

    def export_xdf_audit(self):
        result=getattr(self,'_last_xdf_result',None)
        if result is None:
            QMessageBox.information(self,'Kein XDF-Importbericht',
                'Lade zuerst eine XDF-Datei. Anschließend kannst du alle übernommenen '
                'und abgelehnten Einträge als CSV prüfen.')
            return
        path,_=self.save_destination(self,'XDF-Importbericht speichern',
            'xdf_importbericht.csv','CSV-Dateien (*.csv)')
        if not path:return
        try:result.write_audit_csv(path)
        except Exception as exc:self.warning('Bericht konnte nicht gespeichert werden',exc)

    def import_romraider(self):
        if not self.require_image():return
        path,_=QFileDialog.getOpenFileName(self,'RomRaider XML auswählen','','RomRaider (*.xml)')
        if path:self._import_romraider_path(path)

    def _import_romraider_path(self,path, *, approved_reuse=False):
        from ..core.romraider import read_romraider
        try:result=read_romraider(path,self.image)
        except Exception as exc:
            self.warning('RomRaider-Zuordnung abgelehnt',exc);return
        self._last_xdf_result=result
        if not result.maps:
            self.warning('Keine darstellbaren Kennfelder',result.summary());return
        if not approved_reuse and QMessageBox.question(self,'RomRaider · Importvorschau',
                result.summary()+'\n\nInterne ROM-ID und Dateigröße stimmen überein. '
                'Quellenbezeichnungen bleiben ungeprüft. Importieren?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        existing={(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name) for m in self.maps}
        for m in result.maps:
            key=(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name)
            if key in existing:continue
            self.maps[:]=[c for c in self.maps if not (c.source=='heuristic' and self._overlaps(m,c))]
            self.maps.append(m);existing.add(key)
        self.maps.sort(key=lambda m:(m.offset,m.name))
        self.kind_filter.setCurrentText('Mit Definition')
        self.refresh_map_list();self.update_status()
        self.statusBar().showMessage(f'{result.title}: {len(result.maps)} Definitionen übernommen',10000)

    def _import_xdf_path(self,path, *, approved_reuse=False):
        try: result=read_xdf(path,self.image)
        except Exception as exc:
            self.warning('XDF nicht importierbar',exc);return
        self._last_xdf_result=result
        if not result.maps:
            self.warning('Keine darstellbaren Kennfelder',result.summary()+'\n'
                         'Das XDF enthält keine durch dieses Modell darstellbaren Einträge.')
            return
        status, message = xdf_match_status(identify_profile(self.image), path, result.title)
        if status == 'rejected':
            self.warning('XDF-Kopplung abgelehnt · Kennung stimmt nicht überein', message)
            return
        summary=(result.summary() + f'\n\nKompatibilitätsprüfung: {status}\n{message}\n\n'
                 'Selbst bei gleicher Kennung müssen Software-Patchstand und Adressen geprüft werden.\n\n'
                 'Kopplung basiert auf dem XDF-Dateinamen, nicht '
                 'auf einem kryptografischen Identitätsnachweis. ECU-Softwareversion, '
                 'Achsen und physikalische Werte fachlich prüfen.\n\n'
                 'Nicht unterstützte Gleichungen oder Speicherlayouts wurden ausgelassen. '
                 'Details: Datei → Letzten XDF-Importbericht als CSV speichern. '
                 'Es werden KEINE Änderungen an der Original-BIN vorgenommen.\n\n'
                 'Importieren?')
        if not approved_reuse and QMessageBox.question(self,'XDF-BIN-Kopplung · Vorschau',summary +
            '\n\nNach Zustimmung wird dieses genaue BIN/XDF-Dateipaar lokal für spätere Öffnungen gemerkt.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        existing={(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name) for m in self.maps}
        added=0
        for m in result.maps:
            key=(m.offset,m.rows,m.cols,m.dtype,m.endian,m.name)
            if key in existing:continue
            # Remove only heuristics at overlapping positions, keep distinct
            # XDF symbols (many aliases/variants can share an address).
            for candidate in self.maps[:]:
                if candidate.source=='heuristic' and self._overlaps(m,candidate):
                    self.maps.remove(candidate)
            self.maps.append(m)
            existing.add(key)
            added+=1
        self.maps.sort(key=lambda m:(m.offset,m.name))
        self.kind_filter.setCurrentText('Mit Definition')
        self.refresh_map_list();self.update_status()
        if not approved_reuse:
            try:remember_pair(self.image,path)
            except (OSError,ValueError) as exc:
                self.statusBar().showMessage(f'XDF-Kopplung nicht gespeichert: {exc}',10000)
        QMessageBox.information(self,'XDF importiert',
           f'{added:,} benannte Einträge übernommen.\n'
           f'{sum(result.excluded.values()):,} Einträge nicht unterstützt (Importquote: {result.coverage:.1%}).\n'
           'Alle Einträge kannst du als CSV-Importbericht exportieren.\n\n'
           'Typen erscheinen direkt im Kennfeldkatalog. XDF-Namen sind '
           'quellengebundene Bezeichnungen, keine Garantie der Firmware-Kompatibilität.')

    def audit_map_values(self):
        """Independent read-only decoder audit; does not certify map semantics."""
        if not self.require_image():return
        if not self.maps:
            QMessageBox.information(self,'Keine Definitionen',
                'Zuerst eine passende XDF/A2L importieren. Unbenannte Rohdaten sind keine bestätigten Kennfelder.')
            return
        reports=audit_catalog(self.image,self.maps)
        bad=sum(r.status=='REJECT' for r in reports)
        review=sum(r.status=='REVIEW' for r in reports)
        path,_=self.save_destination(self,'Kennfeld-Datenqualitätsbericht speichern',
               'kennfeld_qualitaet.csv','CSV-Dateien (*.csv)')
        if not path:return
        try:write_quality_csv(path,reports)
        except Exception as exc:self.warning('Bericht fehlgeschlagen',exc);return
        QMessageBox.information(self,'Kennfelddaten geprüft',
            f'{len(reports)} Definitionen geprüft, {bad} Dekodierfehler, '
            f'{review} Einträge mit Warnhinweisen.\n\n'
            'Geprüft wurden Leseadressen, Datentypen, Byte-Reihenfolge, Skalierung und Achsenvollständigkeit.\n'
            'WICHTIG: Technisch konsistente Zahlen beweisen NICHT, dass die verwendete XDF/A2L '
            'zur Firmware passt oder der Kennfeldname korrekt ist.\n\n'
            f'Bericht: {path}')

    def import_a2l(self):
        """Import an explicitly anchored subset of ASAP2; no unverifiable full DAMOS claim."""
        if not self.require_image():return
        path,_=QFileDialog.getOpenFileName(self,"A2L / ASAP2 auswählen","",
               "ASAP2-Dateien (*.a2l *.asap2 *.dam *.damos);;Alle Dateien (*)")
        if not path:return
        try:
            catalog=read_a2l(path)
            if not catalog.characteristics:
                raise ValueError("Keine CHARACTERISTIC-Definitionen gelesen. Binäre oder proprietäre .dam/.damos-Dateien werden noch nicht unterstützt.")
        except Exception as exc:
            self.warning("A2L nicht importierbar",exc);return
        segments=[]
        if self.image.path:
            try:segments=read_import_segments(self.image.path)
            except Exception as exc:
                self.warning('Speichersegmente nicht übernommen',
                    str(exc)+'\nDie A2L-Verknüpfung beginnt ohne Segmentvorschlag.')
        dialog=A2LLinkDialog(catalog,self.image,path,self,suggested_segments=segments)
        if dialog.exec()!=QDialog.DialogCode.Accepted or not dialog.result_data:return
        result=dialog.result_data
        selected_definitions=dialog.selected_maps
        # When the A2L has no descriptive name, a unique local exact reference
        # can suggest the type without changing its verification status.
        try:
            enrich_with_exact_references(selected_definitions, self.library.find(self.image))
        except Exception as exc:
            self.statusBar().showMessage(f'Referenzabgleich übersprungen: {exc}', 6000)
        # Existing curated entries must win; heuristic guesses must not block A2L metadata.
        added=0; replaced=0
        for m in selected_definitions:
            existing=next((x for x in self.maps if self._overlaps(m,x)),None)
            if existing and existing.source=='heuristic':
                self.maps.remove(existing);replaced+=1
            elif existing:
                continue
            self.maps.append(m);added+=1
        self.maps.sort(key=lambda x:(x.offset,x.name))
        self.refresh_map_list();self.update_status()
        QMessageBox.information(self,"A2L-Kopplung abgeschlossen",
            f"{added:,} Definitionen übernommen, {replaced} Heuristiken ersetzt.\n"
            f"{len(result.unsupported)} nicht unterstützte Layouts/Umrechnungen, "
            f"{len(result.out_of_range)} außerhalb Datei, "
            f"{len(result.unlinked)} nicht zugeordnete Segmente.\n\n"
            "Nicht importierte Einträge wurden nicht geschätzt. Bitte Offset, Achsen, "
            "Bytes und Softwarestand manuell verifizieren. Keine Checksum-Freigabe.")

    def save_map_pack(self):
        if not self.require_image():return
        path,_=self.save_destination(self,"Eigenes ECU-Studio-Map-Pack exportieren",
                           "ecu_maps.ecupack.json","ECU-Studio-Map-Pack (*.json)")
        if not path:return
        try:
            export_map_pack(path,self.maps,self.image)
            self.statusBar().showMessage(f"{len(self.maps)} Kennfelder exportiert",7000)
        except Exception as exc:self.warning("Map-Pack-Export fehlgeschlagen",exc)

    def open_map_pack(self):
        if not self.require_image():return
        path,_=QFileDialog.getOpenFileName(self,"Eigenes ECU-Studio-Map-Pack importieren","",
                                           "ECU-Studio-Map-Pack (*.json)")
        if not path:return
        try:
            try:defs,message=import_map_pack(path,image=self.image)
            except ValueError as exc:
                if 'SHA-256' not in str(exc):raise
                answer=QMessageBox.question(self,"Anderer ECU-Softwarestand",
                    str(exc)+"\n\nTrotzdem als UNGEPRÜFTE Definitionen an gleichen Offsets laden?",
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:return
                defs,message=import_map_pack(path,image=self.image,allow_mismatch=True)
            known={(m.offset,m.rows,m.cols,m.dtype,m.endian) for m in self.maps}
            added=0
            for m in defs:
                key=(m.offset,m.rows,m.cols,m.dtype,m.endian)
                if key not in known:
                    self.maps.append(m);known.add(key);added+=1
            self.maps.sort(key=lambda m:m.offset)
            self.refresh_map_list();self.update_status()
            QMessageBox.information(self,"Map-Pack importiert",f"{added} Kennfelder neu. {message}")
        except Exception as exc:self.warning("Map-Pack-Import fehlgeschlagen",exc)

    def inspect_catalogue(self):
        if not self.require_image():return
        data=catalogue_check(self.maps,self.image.size)
        out=[f"KENNFELDKATALOG · {len(self.maps)} Definitionen",
            f"Ungültig: {len(data['invalid'])}",f"Duplikate: {len(data['duplicates'])}",
            f"Überlappungen (erste 500): {len(data['overlaps'])}","",
            "DUPLIKATE:"]
        out.extend(f"  {a}  /  {b}" for a,b in data['duplicates'][:100])
        out.append("\nÜBERLAPPUNGEN:")
        out.extend(f"  {a} <-> {b}  @0x{o:X}" for a,b,o in data['overlaps'][:100])
        out.append("\nUNGÜLTIGE DEFINITIONEN:")
        out.extend(f"  {n}: {why}" for n,why in data['invalid'][:100])
        out.append("\nHinweis: Gemeinsame Speicherbereiche können bei ECU-Kalibrierungen bewusst überlagert sein.")
        self.diff_view.setPlainText("\n".join(out))
        self.tabs.setCurrentWidget(self.diff_view)

    def impact_matrix(self):
        """Searchable changed-map list with export; no physical safety inferences."""
        if not self.require_image():return
        try:
            rows = measure_catalogue(self.image, self.maps)
            outside,total = uncovered_patches(self.image, self.maps)
        except Exception as exc:
            self.warning('Änderungs-Matrix fehlgeschlagen',exc);return
        dlg=QDialog(self)
        dlg.setWindowTitle('Impact-Explorer · alle Kennfelder gegen Original')
        dlg.resize(1080,650)
        lay=QVBoxLayout(dlg)
        lay.addWidget(QLabel(f'{len(rows):,} Kennfelder · {total:,} geänderte Bytes · '
            f'{outside:,} geänderte Bytes außerhalb definierter Kennfelder.\n'
            'Physikalische Abweichungen nur nach eingetragener Skalierung aussagekräftig. '
            'Doppelklick springt zum Kennfeld.'))
        controls=QHBoxLayout()
        query=QLineEdit();query.setPlaceholderText('Typ, Name, Quelle, Offset suchen …')
        controls.addWidget(query)
        only_changed=QCheckBox('Nur geänderte Kennfelder')
        only_changed.setChecked(True)
        controls.addWidget(only_changed)
        export=QPushButton('CSV exportieren')
        controls.addWidget(export)
        lay.addLayout(controls)
        table=QTableWidget(0,8)
        table.setHorizontalHeaderLabels(['Kennfeld','Typ','Offset','Quelle','Geprüft','Zellen Δ','Bytes Δ','Max Δ (phys.)'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSortingEnabled(False)
        lay.addWidget(table,1)
        filtered=[]
        def refresh(*_):
            nonlocal filtered
            q=query.text().casefold().strip()
            filtered=[v for v in rows if (not only_changed.isChecked() or v.bytes_changed) and
                     (not q or q in f'{v.name} {v.kind} {v.source} {v.file_offset:x}'.casefold())]
            table.setSortingEnabled(False)
            table.setRowCount(min(len(filtered),2000))
            for i,m in enumerate(filtered[:2000]):
                cells=[m.name,m.kind,f'0x{m.file_offset:X}',m.source,
                       'Ja' if m.verified else 'Nein',str(m.cells_changed),
                       str(m.bytes_changed),f'{m.max_abs_delta:.5g} {m.unit}']
                for j,value in enumerate(cells):
                    item=QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole,m.file_offset)
                    table.setItem(i,j,item)
            table.resizeColumnsToContents()
            table.setToolTip('Maximal 2.000 Treffer werden angezeigt. CSV exportiert alle gefilterten Treffer.')
        query.textChanged.connect(refresh)
        only_changed.toggled.connect(refresh)
        def export_rows():
            target,_=self.save_destination(dlg,'Impact-Matrix exportieren',
                'map_impact.csv','CSV-Dateien (*.csv)')
            if target:
                try: export_impact_csv(target,filtered)
                except Exception as exc:self.warning('CSV-Export',exc)
        export.clicked.connect(export_rows)
        def go_to_map(row,_col):
            item=table.item(row,0)
            if not item:return
            offset=item.data(Qt.ItemDataRole.UserRole)
            candidate=next((m for m in self.maps if m.offset==offset),None)
            if candidate:
                self.select_map(candidate)
                dlg.accept()
        table.cellDoubleClicked.connect(go_to_map)
        refresh()
        dlg.exec()

    def workflow_check(self):
        """File/catalogue QA cockpit highlighting unverified assumptions."""
        if not self.require_image():return
        try:
            bad=catalogue_check(self.maps,self.image.size)
            impacts=measure_catalogue(self.image,self.maps)
            untracked,total=uncovered_patches(self.image,self.maps)
        except Exception as exc:
            self.warning('Workflow-Check',exc);return
        unverified=sum(not m.verified for m in self.maps)
        external=sum(m.source in ('a2l','pack','csv') for m in self.maps)
        changed=sum(m.cells_changed>0 for m in impacts)
        lines=['WORKFLOW-CHECK | reine Strukturkontrolle, keine Flash-Freigabe','',
               f'BIN-Quelle: {self.image.path}',f'Original SHA-256: {self.image.digest}',
               f'Kennfelder: {len(self.maps)} · mit externen Definitionen: {external}',
               f'Ungeprüfte Kennfelder: {unverified}',
               f'Geänderte Kennfelder: {changed}',
               f'Geänderte Bytes: {total}, außerhalb benannter Kennfelder: {untracked}',
               f'Duplikate: {len(bad["duplicates"])} · Überlappungen: {len(bad["overlaps"])}',
               f'Ungültige Definitionen: {len(bad["invalid"])}','',
               'OFFENE PRÜFPUNKTE:',
               '• Quell-BIN und A2L/DAMOS exakt auf denselben Softwarestand prüfen.',
               '• ECU↔Dateioffset und Achsen-/RECORD_LAYOUT-Abbildung bestätigen.',
               '• Nichtlineare Umrechnungen und unbekannte Layouts nicht schätzen.',
               '• ECU-spezifische Checksummen/Flashverfahren extern prüfen.',
               '• Motorschutz, Emissionen, Fahrzeugsicherheit und Zulassung fachlich prüfen.',
               '', 'Dieses Programm erklärt keine exportierte Datei für sicher oder flashbereit.']
        self.diff_view.setPlainText('\n'.join(lines))
        self.tabs.setCurrentWidget(self.diff_view)

    def batch_transform(self):
        if not self.image or not self.selected:
            QMessageBox.information(self,"Batchbearbeitung","Bitte ein Kennfeld auswählen.")
            return
        dialog=BatchEditDialog(self.image,self.selected,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.on_edited()

    def import_maps(self):
        if not self.require_image():return
        p,_=QFileDialog.getOpenFileName(self,"Kennfelddefinitionen importieren","","CSV-Dateien (*.csv)")
        if not p:return
        try:definitions=import_definitions(p,self.image.size)
        except Exception as exc:self.warning("CSV-Import fehlgeschlagen",exc);return
        known={(m.offset,m.rows,m.cols,m.dtype,m.endian) for m in self.maps}
        self.maps.extend(m for m in definitions if (m.offset,m.rows,m.cols,m.dtype,m.endian) not in known)
        self.maps.sort(key=lambda m:m.offset)
        self.refresh_map_list();self.update_status()
        QMessageBox.information(self,"Import",f"{len(definitions)} Definitionen importiert. Quelle allein gilt noch nicht als verifiziert.")

    def export_maps(self):
        if not self.require_image():return
        p,_=self.save_destination(self,"Definitionen exportieren","maps.csv","CSV-Dateien (*.csv)")
        if p:
            try:export_definitions(p,self.maps)
            except Exception as exc:self.warning("Exportfehler",exc)

    def export_audit(self):
        if not self.require_image():return
        p,_=self.save_destination(self,"Patch-Audit exportieren","changes.csv","CSV-Dateien (*.csv)")
        if p:
            try:export_patch_csv(p,self.image)
            except Exception as exc:self.warning("Audit fehlgeschlagen",exc)

    def save_project(self):
        if not self.require_image():return
        p=self.project_path
        if not p:
            p,_=self.save_destination(self,"Projekt speichern","ecu_project.ecustudio","ECU Studio (*.ecustudio)")
        if not p:return
        try:
            save_project(p,self.image,self.maps,self.bookmarks,self.notes.toPlainText(),self.snapshots)
            self.project_path=p
            self.saved_fingerprint = self.project_state()
            try:
                self.project_store.index(p)
            except Exception as exc:
                self.statusBar().showMessage(f'Projekt gespeichert; Datenbankindex fehlgeschlagen: {exc}',8000)
            self.statusBar().showMessage("Projekt sicher gespeichert",5000)
        except Exception as exc:self.warning("Speichern fehlgeschlagen",exc)

    def open_project(self):
        if not self.ok_to_replace():return
        p,_=QFileDialog.getOpenFileName(self,"Projekt öffnen","","ECU Studio (*.ecustudio)")
        if not p:return
        try:
            image,maps,bookmarks,notes=load_project(p)
            versions=read_project_snapshots(p,image)
        except Exception as exc:self.warning("Projekt konnte nicht geöffnet werden",exc);return
        self.load_state(image,maps,bookmarks,notes,p)
        self.snapshots=versions
        self.saved_fingerprint=self.project_state()
        self.update_diff()

    @staticmethod
    def _overlaps(a, b):
        start = max(a.offset, b.offset)
        overlap = min(a.offset+a.length,b.offset+b.length)-start
        return overlap >= 0.5 * min(a.length,b.length)

    def project_state(self):
        if not self.image:return None
        return json.dumps({
            "patches": self.image.patch_records(),
            "maps": [m.asdict() for m in self.maps],
            "bookmarks": self.bookmarks,
            "notes": self.notes.toPlainText(),
            "snapshots": self.snapshots,
            "journal": self.image.journal,
        }, ensure_ascii=False, sort_keys=True)

    def ok_to_replace(self):
        if any(w and w.isRunning() for w in (self.scanner,self.recognition_worker,self.batch_worker)):
            self.warning("Scan läuft", "Während des Scans keine Datei wechseln. Bitte Scan abschließen lassen.")
            return False
        if self.image and self.project_state()!=self.saved_fingerprint:
            choice=QMessageBox.question(self,"Ungespeicherte Arbeit",
              "Kennfelder, Notizen oder Byte-Änderungen sind nicht als Projekt gespeichert. Wirklich verwerfen?",
              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
              QMessageBox.StandardButton.No)
            return choice == QMessageBox.StandardButton.Yes
        return True

    def command_palette(self):
        commands=[
            ('BIN öffnen',self.open_bin),
            ('Intel HEX / Motorola S-Record importieren',self.import_memory_records),
            ('Projekt öffnen',self.open_project),
            ('Projekt speichern',self.save_project),
            ('Kennfelder automatisch suchen',self.scan_maps),
            ('A2L / DAMOS mit BIN koppeln',self.import_a2l),
            ('TunerPro XDF mit BIN koppeln',self.import_xdf),
            ('Kennfeldliste prüfen',self.inspect_catalogue),
            ('Speicheratlas öffnen',lambda:self.tabs.setCurrentWidget(self.memory_atlas)),
            ('Kennfeld manuell definieren',self.add_map),
            ('Kennfeld-Batchbearbeitung',self.batch_transform),
            ('Versionsstand erstellen',self.create_snapshot),
            ('Versionsstände vergleichen und zurückholen',self.revisions_dialog),
            ('Impact-Explorer',self.impact_matrix),
            ('Workflow-Prüfung',self.workflow_check),
            ('Hex-Muster suchen',self.search_hex),
            ('Gehe zu Offset',self.prompt_goto),
            ('Ähnliche Kennfelder finden',self.find_twins),
            ('BIN mit Referenz vergleichen',self.compare_file),
            ('Audit als HTML exportieren',self.export_report),
            ('Gepatchte BIN exportieren',self.export_bin),
        ]
        dialog=CommandPalette(commands,self)
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.choice:
            dialog.choice()

    def create_snapshot(self):
        if not self.require_image():return
        title,ok=QInputDialog.getText(self,'Versionsstand festhalten','Name des Versionsstands:',
                                      text=f'Stand {len(self.snapshots)+1}')
        if not ok:return
        comment,ok=QInputDialog.getMultiLineText(self,'Version kommentieren',
            'Was wurde geändert oder überprüft? (optional)')
        if not ok:return
        try:
            snap=make_snapshot(self.image,title,comment)
            self.snapshots.append(snap)
            self.statusBar().showMessage(f'Versionsstand \"{title}\" gespeichert – Projektdatei sichern (Strg+S)',7000)
        except Exception as exc:self.warning('Version konnte nicht erstellt werden',exc)

    def revisions_dialog(self):
        if not self.require_image():return
        dlg=QDialog(self)
        dlg.setWindowTitle('Versions-Explorer · Snapshots / Kennfeld-Übernahme')
        dlg.resize(940,570)
        layout=QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            'Diese Versionen sind an exakt dieselbe Original-BIN gebunden (SHA-256). '
            'Vergleiche und selektive Übernahmen sind rückgängig machbar; '
            'es erfolgt keine technische ECU-Freigabe.'))
        table=QTableWidget(0,4)
        table.setHorizontalHeaderLabels(['Stand','Erstellt (UTC)','Editierte Bytes','Kommentar'])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(False)
        layout.addWidget(table,1)
        info=QPlainTextEdit()
        info.setReadOnly(True)
        info.setMaximumHeight(145)
        layout.addWidget(info)
        actions=QHBoxLayout()
        create=QPushButton('Neuen Stand speichern')
        compare=QPushButton('Änderungen anzeigen')
        restore=QPushButton('Gesamten Stand übernehmen')
        selective=QPushButton('Nur ausgewähltes Kennfeld übernehmen')
        close=QPushButton('Schließen')
        for x in (create,compare,restore,selective,close):actions.addWidget(x)
        layout.addLayout(actions)

        def reload():
            table.setRowCount(len(self.snapshots))
            for idx,snap in enumerate(self.snapshots):
                for col,value in enumerate((snap['label'],snap['created_utc'],
                                           str(len(snap['patches'])),snap.get('note','')[:160])):
                    table.setItem(idx,col,QTableWidgetItem(value))
            table.resizeColumnsToContents()
            if self.snapshots:table.selectRow(len(self.snapshots)-1)
        def current():
            row=table.currentRow()
            if row<0 or row>=len(self.snapshots):
                QMessageBox.information(dlg,'Versionsstand auswählen','Bitte einen Versionsstand auswählen.')
                return None
            return self.snapshots[row]
        def display():
            snap=current()
            if snap is None:return
            try:preview=plan_restore(self.image,snap)
            except ValueError as exc:self.warning('Versionsvergleich fehlgeschlagen',exc);return
            lines=[f'ZIELSTAND: {snap["label"]}',
                   f'Original SHA-256: {snap["original_sha256"]}',
                   f'Byte-Unterschiede zum aktuellen Stand: {preview.changed_bytes}',
                   '', 'Erste Unterschiede (Offset: jetzt → Ziel):']
            lines.extend(f'  0x{p:08X}: {before:02X} → {after:02X}'
                         for p,before,after in preview.changes[:80])
            if len(preview.changes)>80:lines.append(f'… {len(preview.changes)-80} weitere')
            info.setPlainText('\n'.join(lines))
        def restore_action(only_map=False):
            snap=current()
            if snap is None:return
            m=self.selected if only_map else None
            if only_map and m is None:
                QMessageBox.information(dlg,'Kennfeld wählen',
                    'Zuerst im Hauptfenster links ein Kennfeld auswählen. Im Dialog danach erneut übernehmen.')
                return
            try:preview=plan_restore(self.image,snap,m)
            except ValueError as exc:self.warning('Version nicht kompatibel',exc);return
            if not preview.changed_bytes:
                info.setPlainText('Dieser Bereich ist bereits identisch mit dem gewählten Stand.')
                return
            scope=f'nur Kennfeld \"{m.name}\"' if m else 'gesamte BIN'
            ans=QMessageBox.question(dlg,'Versionsstand übernehmen?',
                f'{preview.changed_bytes} Bytes für {scope} durch Stand \"{snap["label"]}\" ersetzen?\n'
                'Alle übrigen Bytes bleiben bei Kennfeldübernahme erhalten. Ein Undo-Schritt.')
            if ans!=QMessageBox.StandardButton.Yes:return
            try:apply_restore(self.image,preview)
            except Exception as exc:self.warning('Übernahme fehlgeschlagen',exc);return
            self.on_edited();display()
            self.statusBar().showMessage(f'Versionsstand {snap["label"]}: {preview.changed_bytes} Bytes übernommen',7000)
        create.clicked.connect(lambda:(self.create_snapshot(),reload()))
        compare.clicked.connect(display)
        restore.clicked.connect(lambda:restore_action(False))
        selective.clicked.connect(lambda:restore_action(True))
        close.clicked.connect(dlg.accept)
        table.itemDoubleClicked.connect(lambda _:display())
        reload()
        dlg.exec()

    def remember_signature(self):
        if not self.image or not self.selected:
            self.warning("Kein Kennfeld", "Ein Kennfeld auswählen, geprüften Typ einstellen und den Prüfstatus aktivieren.")
            return
        try:
            self.library.add(self.image, self.selected)
            QMessageBox.information(self,"Referenz gespeichert",
                f"{self.selected.name} als lokaler Byte-Fingerprint gespeichert. "
                "Bei exakter Übereinstimmung wird es später als unbestätigter Referenztreffer angezeigt.")
        except Exception as exc:
            self.warning("Fingerprint nicht gespeichert",exc)

    def find_reference_maps(self):
        if not self.require_image():return
        try:
            hits=self.library.find(self.image)
        except Exception as exc:
            self.warning("Referenzsuche fehlgeschlagen",exc);return
        new=[m for m in hits if not any(self._overlaps(m,x) for x in self.maps)]
        self.maps.extend(new)
        self.maps.sort(key=lambda x:x.offset)
        self.refresh_map_list();self.update_status()
        QMessageBox.information(self,"Referenztreffer",f"{len(hits)} exakte, eindeutige Treffer; {len(new)} neue Definitionen übernommen.\nReferenzen müssen für jede Ziel-ECU erneut geprüft werden.")

    def export_report(self):
        if not self.require_image():return
        p,_=self.save_destination(self,"HTML-Änderungsbericht","ecu_audit.html","HTML (*.html)")
        if p:
            try:
                export_html(p,self.image,self.maps,self.notes.toPlainText())
                self.statusBar().showMessage("HTML-Änderungsbericht exportiert",6000)
            except Exception as exc:self.warning("Bericht fehlgeschlagen",exc)

    def make_demo(self):
        folder=QFileDialog.getExistingDirectory(self,"Ordner für Demo-Dateien wählen")
        if not folder:return
        try:
            path,defs=generate_demo(folder)
        except Exception as exc:
            self.warning("Demo fehlgeschlagen",exc);return
        QMessageBox.information(self,"Demo erzeugt",
            f"Synthetische BIN: {path}\nKennfelddefinitionen: {defs}\n\n"
            "Die Demo enthält keine echte Fahrzeugsoftware. BIN im Editor öffnen: die begleitende CSV wird automatisch geladen.")

    def make_a2l_demo(self):
        folder=QFileDialog.getExistingDirectory(self,'Ordner für A2L-Demo wählen')
        if not folder:return
        try:
            image_path,labels_path=generate_extended_demo(folder)
            QMessageBox.information(self,'A2L-Demo erzeugt',
                f'Synthetische BIN: {image_path}\nA2L-Definitionen: {labels_path}\n\n'
                '1. BIN öffnen. 2. A2L / DAMOS koppeln. 3. ECU-Anker 0x800000 und BIN-Anker 0x0 eintragen. '
                '4. 14 unterschiedliche Kennfeldtypen prüfen. Alles rein fiktiv.')
        except Exception as exc:self.warning('Demo fehlgeschlagen',exc)

    def focus_map_cell(self,row:int,col:int):
        if not self.selected or not self.image:return
        index=self.map_model.index(row,col)
        if not index.isValid():return
        self.map_table.setCurrentIndex(index)
        self.map_table.scrollTo(index)
        self.tabs.setCurrentWidget(self.map_table)

    def open_map_groups(self):
        if not self.require_image():return
        groups=group_maps(self.maps)
        dialog=QDialog(self)
        dialog.setWindowTitle('Kennfelder · Funktionsgruppen und Nachbarschaft')
        dialog.resize(940,610)
        outer=QVBoxLayout(dialog)
        outer.addWidget(QLabel('Zuordnungen stammen aus vorhandenen Definitionen. Nähe und Form sind KEIN Funktionsnachweis.'))
        tree=QTreeWidget(dialog)
        tree.setHeaderLabels(['Gruppe / Kennfeld','Offset','Typ','Status'])
        tree.setAlternatingRowColors(True)
        tree.setColumnWidth(0,430)
        tree.setColumnWidth(1,130)
        tree.setColumnWidth(2,180)
        for group in groups:
            node=QTreeWidgetItem(tree,[f'{group.title} ({len(group.indices)})','',group.basis,
                                       f'{group.verified_members} geprüft'])
            node.setToolTip(0,group.note)
            for i in group.indices:
                m=self.maps[i]
                child=QTreeWidgetItem(node,[m.name,f'0x{m.offset:08X}',m.kind,
                                             'geprüft' if m.verified else 'ungeprüft'])
                child.setData(0,Qt.ItemDataRole.UserRole,i)
                child.setToolTip(0,m.notes or group.note)
            node.setExpanded(group.key.startswith('semantic:'))
        outer.addWidget(tree,1)
        buttons=QHBoxLayout()
        save=QPushButton('Gruppen als CSV exportieren …')
        jump=QPushButton('Kennfeld öffnen')
        close=QPushButton('Schließen')
        buttons.addWidget(save);buttons.addStretch();buttons.addWidget(jump);buttons.addWidget(close)
        outer.addLayout(buttons)
        def open_item(item=None,*args):
            item=item if isinstance(item,QTreeWidgetItem) else tree.currentItem()
            if item is None:return
            i=item.data(0,Qt.ItemDataRole.UserRole)
            if i is None:return
            self.select_map(self.maps[i]);dialog.accept()
        def save_file():
            path,_=self.save_destination(dialog,'Gruppen exportieren','kennfeldgruppen_v18.csv',
                                               'CSV (*.csv)')
            if not path:return
            try:export_groups_csv(path,groups,self.maps)
            except Exception as exc:self.warning('Export fehlgeschlagen',exc)
        tree.itemDoubleClicked.connect(open_item)
        jump.clicked.connect(open_item)
        save.clicked.connect(save_file)
        close.clicked.connect(dialog.reject)
        dialog.exec()

    def load_checksum_manifest(self):
        if not self.require_image():return
        path,_=QFileDialog.getOpenFileName(self,'ECU-Checksummenprofil importieren','',
                                           'JSON-Dateien (*.json)')
        if not path:return
        try:
            profile=load_checksum_profile(path,self.image)
            self.checksum_profile=profile
            result=audit_export(self.image,self.maps,profile)
            QMessageBox.information(self,'Checksummenprofil geladen',
                f'{len(profile.slots)} geprüfte Bereichsdefinitionen importiert.\n'
                f'Prüfstatus: {result["checksums"]["status"]}\n\n'
                'Nur die deklarierten Bereiche werden geprüft; keine ECU-Gesamtfreigabe.')
        except Exception as exc:self.warning('Profil abgewiesen',exc)

    def correct_checksums(self):
        """Plan, show every byte, ask, write, verify – or leave the file untouched."""
        if not self.require_image():return
        if self.checksum_profile is None:
            QMessageBox.information(self,'Checksummen-Korrektur','Zuerst ein geprüftes Checksummenprofil laden.');return
        try:steps=plan_checksum_correction(self.image,self.checksum_profile)
        except Exception as exc:self.warning('Korrektur verweigert',exc);return
        text=correction_preview(steps)
        if not steps:
            QMessageBox.information(self,'Checksummen-Korrektur',text);return
        box=QMessageBox(self)
        box.setWindowTitle('Checksummen-Korrektur – Vorschau')
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec()!=QMessageBox.StandardButton.Yes:return
        try:apply_checksum_correction(self.image,self.checksum_profile,steps)
        except Exception as exc:self.warning('Korrektur nicht übernommen',exc);return
        self.on_edited()
        self.statusBar().showMessage(f'{len(steps)} Prüffeld(er) geschrieben und verifiziert · rückgängig mit Strg+Z · keine Flashfreigabe',10000)

    def correct_table_checksums(self):
        """Self-describing checksum tables (ME7.x, MED9, ME9): proven on the original, then corrected."""
        if not self.require_image():return
        from ..core.checksum_tables import check_tables, plan_table_correction, apply_table_correction
        state=check_tables(self.image)
        if state['status']=='none':
            QMessageBox.information(self,'Prüfsummen-Tabellen',
                'In dieser Datei wurde keine Prüfsummen-Tabelle gefunden, deren Werte das unveränderte Original exakt '
                'reproduziert. Für diese Datei gibt es daher keine automatische Prüfung oder Korrektur.');return
        head=(f'{state["blocks"]} Prüfsummenblöcke sind am unveränderten Original bewiesen '
              f'(Verfahren aus der Datei selbst bestätigt). Aktuell stimmen {state["blocks"]-state["mismatches"]} '
              f'von {state["blocks"]}.')
        if not state['mismatches']:
            QMessageBox.information(self,'Prüfsummen-Tabellen',head+'\n\nNichts zu korrigieren. Keine Flashfreigabe: '
                                    'Signaturen und weitere ECU-Prüfungen sind nicht abgedeckt.');return
        try:steps=plan_table_correction(self.image)
        except ValueError as exc:self.warning('Korrektur verweigert',exc);return
        lines='\n'.join(f'• 0x{o:08X}: {old.hex(" ").upper()}  →  {new.hex(" ").upper()}' for o,old,new in steps[:20])
        more=f'\n… und {len(steps)-20} weitere' if len(steps)>20 else ''
        box=QMessageBox(self)
        box.setWindowTitle('Prüfsummen-Tabellen – Vorschau')
        box.setText(head+f'\n\n{len(steps)} Feld(er) würden geschrieben (Wert und invertierter Wert, rückgängig machbar):\n'
                    +lines+more+'\n\nNur diese Tabellen-Prüfsummen; Signaturen (z. B. RSA) und weitere ECU-Prüfungen '
                    'werden NICHT behandelt. Keine Flashfreigabe.')
        box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec()!=QMessageBox.StandardButton.Yes:return
        try:apply_table_correction(self.image,steps)
        except ValueError as exc:self.warning('Korrektur nicht übernommen',exc);return
        self.on_edited()
        self.statusBar().showMessage(f'{len(steps)} Tabellen-Prüfsumme(n) geschrieben, alle {state["blocks"]} Blöcke verifiziert · '
                                     'rückgängig mit Strg+Z · keine Flashfreigabe',10000)

    def correct_edc17_blocks(self):
        """Bosch MED17/EDC17 checksum blocks (CRC32/ADD32/ADD16): proven on the original, then corrected."""
        if not self.require_image():return
        from ..core.edc17_checksum import verify, check_current, plan_correction, correction_preview, apply_correction
        proof=verify(self.image)
        if not proof['detected']:
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',
                'In dieser Datei wurde kein Bosch MED17/EDC17-Prüfsummenblock gefunden '
                '(Signatur FADECAFE/CAFEAFFE). Keine Prüfung oder Korrektur für dieses Verfahren.');return
        if proof['proven_on_original']==0:
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',
                f'{proof["blocks"]} Blockkandidat(en) gefunden, aber kein Block ließ sich am unveränderten Original '
                'mit CRC32/ADD32/ADD16 reproduzieren. Das Verfahren gilt für diese Datei als NICHT nachgewiesen – '
                'keine Korrektur.');return
        if proof['coverage'] != 'full':
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',
                f'Nur {proof["proven_on_original"]} von {proof["structures_total"]} Strukturen sind am '
                'unveränderten Original bestätigt. Teilbestätigte Strukturen werden nicht korrigiert.');return
        if not proof['oem_validated']:
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',
                'Die Strukturen sind rechnerisch reproduziert, aber für diese Originaldatei fehlt der geprüfte '
                'OEM-Nachweis. Prüfung bleibt möglich; automatische Korrektur ist bis zur OEM-Validierung gesperrt.');return
        state=check_current(self.image)
        cover={'full':'Vollständig geprüft','partial':'Teilweise geprüft'}.get(state['coverage'],'Geprüft')
        head=(cover+'\n'
              +f'{state["structures_proven"]} von {state["structures_total"]} Prüfsummenstrukturen am '
              f'unveränderten Original nachgewiesen. Aktuell stimmen {state["blocks"]-state["mismatches"]} '
              f'von {state["blocks"]}.')
        if state['structures_unproven']:
            head+=f'\n{state["structures_unproven"]} Struktur(en) sind nicht nachgewiesen und bleiben ungeprüft.'
        if not state['mismatches']:
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',head+'\n\nNichts zu korrigieren. Keine Flashfreigabe: '
                                    'Signaturen und weitere ECU-Prüfungen sind nicht abgedeckt.');return
        try:steps,skipped=plan_correction(self.image)
        except ValueError as exc:self.warning('Korrektur verweigert',exc);return
        if not steps:
            QMessageBox.information(self,'EDC17/MED17-Prüfsummen',head+'\n\n'+correction_preview(steps,skipped));return
        box=QMessageBox(self)
        box.setWindowTitle('EDC17/MED17-Prüfsummen – Vorschau')
        box.setText(head+'\n\n'+correction_preview(steps,skipped))
        box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec()!=QMessageBox.StandardButton.Yes:return
        try:apply_correction(self.image,steps)
        except ValueError as exc:self.warning('Korrektur nicht übernommen',exc);return
        self.on_edited()
        self.statusBar().showMessage(f'{len(steps)} EDC17/MED17-Kompensationswort(e) geschrieben, Blöcke neu verifiziert · '
                                     'rückgängig mit Strg+Z · keine Flashfreigabe',10000)

    def correct_edc16_blocks(self):
        """Bosch EDC16 self-describing checksum regions, with strict proof gates."""
        if not self.require_image():return
        from ..core.edc16_checksum import (verify, check_current, plan_correction,
                                            apply_correction)
        proof=verify(self.image)
        if not proof['detected']:
            QMessageBox.information(self,'EDC16-Prüfsummen',
                'Kein unterstützter EDC16-Prüfsummenbereich (FADECAFE/CAFEAFFE) gefunden.');return
        if proof['coverage'] != 'full':
            QMessageBox.information(self,'EDC16-Prüfsummen',
                f'Nur {proof["proven_on_original"]} von {proof["regions_total"]} Bereichen sind am Original '
                'bestätigt. Teilbestätigte Strukturen werden nicht korrigiert.');return
        state=check_current(self.image)
        head=(f'{state["regions_proven"]} von {state["regions_total"]} EDC16-Bereichen am unveränderten '
              f'Original bestätigt. Aktuell stimmen {state["regions"]-state["mismatches"]} von {state["regions"]}.')
        if not state['mismatches']:
            QMessageBox.information(self,'EDC16-Prüfsummen',head+'\n\nNichts zu korrigieren.');return
        if not proof['oem_validated']:
            QMessageBox.information(self,'EDC16-Prüfsummen',head+'\n\nFür diese Originaldatei fehlt der geprüfte '
                                    'OEM-Nachweis. Automatische Korrektur ist gesperrt.');return
        try:steps=plan_correction(self.image)
        except ValueError as exc:self.warning('Korrektur verweigert',exc);return
        lines='\n'.join(f'• 0x{o:08X}: {old.hex(" ").upper()}  →  {new.hex(" ").upper()}'
                        for o,old,new in steps)
        box=QMessageBox(self)
        box.setWindowTitle('EDC16-Prüfsummen – Vorschau')
        box.setText(head+f'\n\n{len(steps)} Kompensationswort(e) würden geschrieben:\n{lines}')
        box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec()!=QMessageBox.StandardButton.Yes:return
        try:apply_correction(self.image,steps)
        except ValueError as exc:self.warning('Korrektur nicht übernommen',exc);return
        self.on_edited()
        self.statusBar().showMessage(f'{len(steps)} EDC16-Kompensationswort(e) geschrieben, Bereiche neu verifiziert · '
                                     'rückgängig mit Strg+Z · keine Flashfreigabe',10000)

    def open_checksum_audit(self):
        if not self.require_image():return
        try:report=audit_export(self.image,self.maps,self.checksum_profile)
        except Exception as exc:self.warning('Prüfung fehlgeschlagen',exc);return
        dialog=QDialog(self)
        dialog.setWindowTitle('ECU Studio · Checksummen und Plausibilitätsbericht')
        dialog.resize(850,610)
        layout=QVBoxLayout(dialog)
        state=report['checksums']
        layout.addWidget(QLabel('Checksum: '+state['status'].upper()+' · KEINE Flash-/Fahrzeugfreigabe'))
        out=QPlainTextEdit(dialog)
        out.setReadOnly(True)
        out.setFont(QFont('Consolas',10))
        lines=[f'Original: {report["original_sha256"]}',
               f'MOD:      {report["modified_sha256"]}',
               f'Dateigröße: {report["size"]} Bytes',
               f'Veränderte Bytes: {report["dirty_bytes"]}',
               f'Davon außerhalb bekannter Kennfelder: {report["changed_outside_maps"]}',
               f'Lesefehler in Kennfelddefinitionen: {report["map_decode_issues"]}',
               f'Definitionen mit Prüfhinweisen: {report["map_review_hints"]}',
               f'Veränderte Kennfelder: {report["changed_map_count"]}',
               '',state['message'],'','Prüfbereiche:']
        for entry in state['regions']:
            lines.append(f'{entry["name"]}: {"OK" if entry["match"] else "FEHLER"}  '
                         f'{entry["algorithm"]}  Berechnet: 0x{entry["expected"]:X} '
                         f'Gespeichert: 0x{entry["stored"]:X}')
        lines+=['','Meldungen:']+[f'{x["level"].upper()}: {x["message"]}' for x in report['issues']]
        lines+=['',report['note']]
        out.setPlainText('\n'.join(lines))
        layout.addWidget(out,1)
        row=QHBoxLayout()
        import_btn=QPushButton('Geprüftes Checksum-Profil laden …')
        correct_btn=QPushButton('Prüffelder korrigieren (Vorschau) …')
        correct_btn.setEnabled(self.checksum_profile is not None and state['status']=='mismatch')
        correct_btn.setToolTip('Nur mit geprüftem Profil, das am Original stimmt; zeigt vorher jedes Byte.')
        export_btn=QPushButton('Prüfbericht als JSON speichern …')
        close=QPushButton('Schließen')
        row.addWidget(import_btn);row.addWidget(correct_btn);row.addWidget(export_btn);row.addStretch();row.addWidget(close)
        layout.addLayout(row)
        import_btn.clicked.connect(lambda:(dialog.accept(),self.load_checksum_manifest()))
        correct_btn.clicked.connect(lambda:(dialog.accept(),self.correct_checksums()))
        def save():
            target,_=self.save_destination(dialog,'Prüfbericht speichern','ecu_check_report_v18.json','JSON (*.json)')
            if target:
                try:write_audit_json(target,report)
                except Exception as exc:self.warning('Bericht konnte nicht gespeichert werden',exc)
        export_btn.clicked.connect(save)
        close.clicked.connect(dialog.accept)
        dialog.exec()

    def _preflight(self):
        profile=identify_profile(self.image)
        return run_preflight(self.image,self.maps,checksum_profile=self.checksum_profile,
                             cal_window=(profile.cal_start,profile.cal_end) if profile.cal_start is not None else None)

    def _code_window(self):
        profile=identify_profile(self.image)
        return ((profile.cal_start,profile.cal_end) if profile.cal_start is not None else (0,self.image.size))

    def show_function_graph(self):
        if not self.require_image():return
        from ..core.function_graph import build_function_graph
        from .function_graph_dialog import FunctionGraphDialog
        try:graph=build_function_graph(self.image,self.maps,*self._code_window())
        except Exception as exc:
            self.warning('Funktionsgraph fehlgeschlagen',exc);return
        if not graph['groups'] and not graph['shared_axes'] and not graph['axis_hints']:
            QMessageBox.information(self,'Funktionsgraph','Keine Code-Verweise und keine gemeinsamen Achsen gefunden. '
                                    'Code-Verweise werden derzeit für C16x (Siemens MS4x, Bosch ME7) ausgewertet; '
                                    'gemeinsame Achsen brauchen bekannte Achsadressen.')
            return
        FunctionGraphDialog(self,self.maps,graph,lambda m:self.select_map(m)).exec()

    def show_signal_trace(self):
        if not self.require_image():return
        from ..core.signal_trace import trace_inputs, trace_report
        try:traces=trace_inputs(self.image,self.maps,*self._code_window())
        except Exception as exc:
            self.warning('Signal-Tracing fehlgeschlagen',exc);return
        self.diff_view.setPlainText(trace_report(traces,self.maps))
        self.tabs.setCurrentWidget(self.diff_view)

    def flash_preflight(self):
        if not self.require_image():return
        try:report=self._preflight()
        except Exception as exc:
            self.warning('Preflight fehlgeschlagen',exc);return
        self.diff_view.setPlainText(report.text())
        self.tabs.setCurrentWidget(self.diff_view)
        self.statusBar().showMessage(f'Flash-Preflight: {report.status.upper()} · {len(report.findings)} Befunde · '
                                     +('deklarierte Prüffelder stimmen – keine Flashfreigabe' if report.checksum_verified else 'Checksummen NICHT verifiziert – nicht flashbereit'),8000)

    def export_bin(self):
        if not self.require_image():return
        try:
            check=audit_export(self.image,self.maps,self.checksum_profile)
            preflight=self._preflight()
        except Exception as exc:
            self.warning('Exportprüfung fehlgeschlagen',exc)
            return
        check_state=check['checksums']['status']
        red=[f for f in preflight.findings if f.level=='rot']
        msg=(f"FLASH-PREFLIGHT: {preflight.status.upper()} – {len(preflight.findings)} Befunde"
             + ("".join(f"\n  • {f.title}" for f in red[:6]) if red else "")
             + "\nDetails: Datei → Flash-Preflight prüfen.\n\n"
             f"Prüfsummenstatus: {check_state.upper()}\n"
             f"Geänderte Bytes: {check['dirty_bytes']}\n"
             f"Geänderte Bytes außerhalb erkannter Tabellen: {check['changed_outside_maps']}\n"
             f"Definitionen mit Prüfhilfen: {check['map_review_hints']}\n\n"
             "Auch bei einem passenden Prüfprofil ist KEINE ECU-/Flash-, "
             "Emissions-, Motor- oder Straßensicherheitsfreigabe gegeben.\n"
             "Es erfolgt KEINE Checksummenreparatur.\n\n"
             "BIN nur zur Offline-Analyse/Validierung exportieren?")
        if QMessageBox.warning(self,"Wichtiger Sicherheitshinweis",msg,
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:return
        origin=Path(self.image.path) if self.image.path else Path("ecu.bin")
        p,_=self.save_destination(self,"Gepatchte BIN exportieren",str(origin.with_name(origin.stem+"_edited.bin")),"BIN-Dateien (*.bin);;Alle Dateien (*)")
        if not p:return
        if self.image.path and Path(p).resolve()==Path(self.image.path).resolve():
            self.warning("Export abgebrochen","Original darf niemals überschrieben werden.");return
        try:
            data=self.image.materialize()
            atomic_write(p,data,backup=True,protected=(self.image.path,))
            QMessageBox.information(self,"Export erfolgreich",f"{len(data):,} Bytes exportiert.\nSHA-256: {hashlib.sha256(data).hexdigest()}\n\nNICHT flash-validiert.")
        except Exception as exc:self.warning("Export fehlgeschlagen",exc)

    def check_map(self):
        if not self.image or not self.selected:
            QMessageBox.information(self,"Kennfeld-Check","Bitte zuerst ein Kennfeld auswählen.")
            return
        try:
            report=analyze_map(self.image,self.selected)
        except Exception as exc:self.warning("Kennfeld-Check",exc);return
        lines=["KENNFELD-CHECK | schnell prüfbare Strukturhinweise", "",
               f"Name: {self.selected.name}", f"Typ: {self.selected.kind} (Quelle: {self.selected.source})",
               f"Offset: 0x{self.selected.offset:08X}",
               f"Datenbereich: {self.selected.length} Bytes | {report['rows']}×{report['cols']}",
               f"Minimum: {report['min']:g} {self.selected.unit}",
               f"Maximum: {report['max']:g} {self.selected.unit}",
               f"Bearbeitete Bytes im Bereich: {report['modified_bytes']}","","HINWEISE:"]
        lines.extend("  • "+msg for msg in report["alerts"])
        lines += ["","Dies ist nur ein Formcheck, keine Prüfung der Kalibrierung oder Fahrzeugsicherheit."]
        self.diff_view.setPlainText("\n".join(lines))
        self.tabs.setCurrentWidget(self.diff_view)

    def find_twins(self):
        if not self.image or not self.selected:
            QMessageBox.information(self,"Ähnliche Kennfelder","Bitte zuerst ein Kennfeld auswählen.")
            return
        try:matches=find_similar_maps(self.image,self.selected,self.maps)
        except Exception as exc:self.warning("Vergleich fehlgeschlagen",exc);return
        lines=[f"ÄHNLICHE KENNFELDER · {self.selected.name}","",
               "Formähnlichkeit bei gleicher Dimension, nicht gleicher Funktion!","",
               "Korrelation     Offset       Name / Typ"]
        for similarity,m in matches:
            lines.append(f"  {similarity:7.1%}      0x{m.offset:08X}  {m.name} ({m.kind})")
        if not matches:lines.append("Keine ähnlich geformten definierten Kennfelder gefunden.")
        self.diff_view.setPlainText("\n".join(lines))
        self.tabs.setCurrentWidget(self.diff_view)

    def export_values(self):
        if not self.image or not self.selected:
            QMessageBox.information(self,"CSV-Export","Bitte zuerst ein Kennfeld auswählen.")
            return
        m=self.selected
        p,_=self.save_destination(self,"Tabellenwerte exportieren",f"map_{m.offset:X}.csv","CSV-Dateien (*.csv)")
        if not p:return
        try:
            with open(p,"w",newline="",encoding="utf-8-sig") as fh:
                writer=csv.writer(fh,delimiter=";")
                writer.writerow([f"{m.name} ({m.unit})"]+[str(i) for i in range(m.cols)])
                for r in range(m.rows):
                    writer.writerow([r]+[f"{self.image.physical_value(m,r,c):g}" for c in range(m.cols)])
            self.statusBar().showMessage("Kennfeldtabelle exportiert",5000)
        except Exception as exc:self.warning("CSV-Export fehlgeschlagen",exc)

    def _identity(self):
        """(identity, support entry) of the loaded image, cached per original content."""
        from ..core.identification import identify
        from ..core.support import lookup
        key=self.image.digest
        if getattr(self,'_identity_cache',(None,))[0]!=key:
            ident=identify(BinaryImage(self.image.original))
            self._identity_cache=(key,ident,lookup(ident.family))
        return self._identity_cache[1],self._identity_cache[2]

    def update_identity_banner(self):
        """Hint bar after loading: what the file says about itself and what is measured for it."""
        if self.image is None:
            self.identity_banner.hide();return
        ident,entry=self._identity()
        if entry:
            measured=[s for s in entry.software if s.get('exact_2d') is not None]
            best=max(measured,key=lambda s:s['exact_2d'],default=None)
            quality=(f" – gemessen an {len(measured)} {'Softwarestand' if len(measured)==1 else 'Softwareständen'}, z. B. {best['exact_2d']} von {best['reference_2d']} Kennfeldern exakt"
                     + (f", Präzision {best['precision_2d']:.0%}" if best and best.get('precision_2d') is not None else '')
                     if best else '')
            text=f'<b>{entry.family}</b> erkannt ({ident.family_evidence}). Unterstützung: <b>{entry.status}</b>{quality}.'
        elif ident.family:
            text=(f'<b>{ident.family}</b> erkannt ({ident.family_evidence}). Für diese Familie gibt es <b>keine Messung</b> – '
                  'Suchvorschläge sind ungeprüft.')
        elif ident.ambiguous:
            text='Familie <b>mehrdeutig</b> ('+', '.join(ident.ambiguous)+'). Suchvorschläge sind ungeprüft.'
        else:
            text=('Steuergerät nicht aus der Datei bestimmbar (z. B. reiner Kalibrierbereich). '
                  'Eine passende A2L mit EPK-Prüfung belegt den Softwarestand.')
        self.identity_banner_text.setText(text)
        self.identity_banner.show()

    def identity_text(self) -> str:
        """Identity markers found in the loaded image and the measured support status."""
        ident, entry = self._identity()
        status = (f'Unterstützung: {entry.status} – {entry.family}' if entry
                  else 'Unterstützung: keine Messung für diese Kennung' if ident.family
                  else 'Unterstützung: Familie nicht aus der Datei bestimmbar')
        return f'Kennung: {ident.summary()}' + chr(10) + status

    def show_support_matrix(self):
        from .support_dialog import SupportDialog
        current = None
        if self.image is not None:
            from ..core.identification import identify
            current = identify(self.image).summary()
        SupportDialog(self, current).exec()

    def show_help(self):
        QMessageBox.information(self,"Erkennungsgrenzen",
            "Für MS43 430069 (64/512 KiB) sind Standard-XDFs mit Achsen offline enthalten. "
            "Softwarekennung, Dateigröße und verteilte Achsen werden vor dem Vorschlag geprüft. "
            "Dies bestätigt keine Patchvariante und macht Definitionen nicht unabhängig verifiziert. "
            "Andere Dateien werden auf 8-/16-/32-Bit-Datenstrukturen untersucht. "
            "Konkurrierende schmalere Datentypen führen zur Enthaltung. Ohne belegte Definitionen "
            "(z. B. passende A2L-Dateien oder validierte Beschriftungen) ist eine zuverlässige Typidentifikation nicht möglich. "
            "A2L importiert nur unterstützte lineare Layouts und verlangt explizite Adresskopplung. "
            "Mehrsegment-Abbildung möglich; bei geprüftem HEX/SRecord-BIN-Konverter schlägt die GUI Segmente vor. "
            "Unter Ansicht lassen sich Arbeitsfenster verschieben und Designs auswählen. "
            "Strg+Umschalt+M öffnet den Speicheratlas für Map-Abdeckung und geänderte Bereiche. "
            "Proprietäres binäres DAMOS ist nicht enthalten. Keine Checksum-Korrektur, "
            "kein OBD/Bench-Flashing, keine automatische Deaktivierung von Emissionsfunktionen.")

    def show_definition_licenses(self):
        from ..recognition.bundled_definitions import DATA
        from ..recognition.calibration_ranker import training_status
        dialog=QDialog(self)
        dialog.setWindowTitle('Definitionsquellen und Lizenzen')
        dialog.resize(850,650)
        layout=QVBoxLayout(dialog)
        text=QPlainTextEdit(dialog)
        text.setReadOnly(True)
        training=training_status()
        text.setPlainText('KI-Strukturtraining: '+str(training.get('domain','nicht verfügbar'))+'\n'
                          'Getrennter Preset-Test: '+str(training.get('holdout',{}))+'\n'
                          'Keine universelle OEM-Erkennungsquote.\n\n'+
                          (DATA/'NOTICE.txt').read_text(encoding='utf-8')+'\n\n'+
                          (DATA.parent/'COPYING.GPL-3').read_text(encoding='utf-8'))
        layout.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def closeEvent(self,event):
        if any(w and w.isRunning() for w in (self.scanner,self.recognition_worker,self.batch_worker)):
            self.cancel_analysis()
            QMessageBox.information(self,"Analyse aktiv","Analyse wird beendet. Bitte nach Abschluss erneut schließen.")
            event.ignore();return
        if self.image and self.project_state()!=self.saved_fingerprint:
            choice=QMessageBox.question(self,"Schließen","Ungespeicherte Kennfelddefinitionen, Notizen oder Änderungen vorhanden. Wirklich schließen?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
            if choice!=QMessageBox.StandardButton.Yes:
                event.ignore();return
        self.settings.setValue("ui/geometry",self.saveGeometry())
        self.settings.setValue("ui/state_v06",self.saveState(1))
        event.accept()
        # A confirmed update starts only after closing was accepted (no unsaved work lost).
        if getattr(self,'updates',None):self.updates.launch_pending()

    def cancel_analysis(self):
        for worker in (self.scanner,self.recognition_worker,self.batch_worker):
            if worker and worker.isRunning():
                worker.requestInterruption()
        self.statusBar().showMessage('Abbruch angefordert · laufenden Analyseschritt abschließen')

    def set_byte_radix(self,radix):
        self.hex_model.radix=radix
        self.hex_model.refresh()

    def save_destination(self,*args,**kwargs):
        path,kind=QFileDialog.getSaveFileName(*args,**kwargs)
        if path and self.image:
            target=Path(path).resolve()
            original=Path(self.image.path).resolve() if self.image.path else None
            if (target.parent.name=='.ecustudio-originals' or
                    (original and (target==original or (target.exists() and original.exists() and os.path.samefile(target,original))))):
                self.warning('Original geschützt','Dieser Speicherpfad gehört zur Originaldatei oder deren Sicherung.')
                return '',kind
        return path,kind

    def autosave(self):
        if not self.image or self.project_state()==self.saved_fingerprint:
            return
        # Reuse the durable project format and exact original backup. Recovery
        # files never replace an explicit save or change the saved fingerprint.
        path=(Path(self.project_path).with_name(Path(self.project_path).stem+'.recovery.ecustudio')
              if self.project_path else Path.home()/'.ecu_studio_ai'/'recovery'/f'{self.image.digest}.ecustudio')
        try:
            save_project(str(path),self.image,self.maps,self.bookmarks,self.notes.toPlainText(),self.snapshots)
            self.statusBar().showMessage('Automatisches Wiederherstellungsprojekt gespeichert',4000)
        except Exception as exc:
            self.statusBar().showMessage(f'Automatische Sicherung fehlgeschlagen: {exc}',8000)

    def smart_transfer(self):
        if self.require_image():
            SmartTransferDialog(self).exec()

    def match_software_maps(self):
        if not self.require_image():return
        from .map_matching_dialog import MapMatchingDialog
        dialog=MapMatchingDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            transfer=SmartTransferDialog(self)
            transfer.source_loaded('Referenzprojekt',(dialog.source,dialog.source_maps,[],''))
            transfer.links=dialog.selected_links;transfer.link_target_key=dialog.target_key
            transfer.source_name.setText(f'{len(transfer.links)} mathematische Paarungen ausgewählt')
            transfer.exec()

    def compare_software_versions(self):
        if not self.require_image():return
        from .version_compare_dialog import VersionCompareDialog
        VersionCompareDialog(self).exec()

    def apply_adopted_definitions(self,added,protocol,source_label):
        """Add adopted definitions, log them and keep the result as a project version."""
        self.maps.extend(added)
        self.maps.sort(key=lambda m:m.offset)
        self.image.journal.extend(dict(entry,label=f'Definition übernommen: {entry["name"]}',revision=self.image.revision,
                                       changes=[]) for entry in protocol)
        title=f'Definitionen aus {source_label}'[:120]
        note='\n'.join(f'{e["name"]}: 0x{e["source_offset"]:X} → 0x{e["target_offset"]:X} ({e["match"]}; {e["evidence"]})'
                       for e in protocol)[:10_000]
        try:
            self.snapshots.append(make_snapshot(self.image,title,note,maps=self.maps))
        except ValueError as exc:
            self.warning('Versionsstand nicht angelegt',exc)
        self.refresh_map_list();self.update_status();self.update_diff()
        self.statusBar().showMessage(f'{len(added)} Definitionen übernommen · ungeprüft · Versionsstand „{title}“ angelegt',8000)
        answer=QMessageBox.question(self,'Projekt speichern',
            f'{len(added)} Definitionen übernommen und als Versionsstand „{title}“ festgehalten. Projekt jetzt speichern?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)
        if answer==QMessageBox.StandardButton.Yes:
            self.save_project()

    def transfer_sister_names(self):
        """Names and layouts from a sister software version with a definition (proposals only)."""
        if not self.require_image():return
        from ..core.name_transfer import transfer_names, definition_maps, EVIDENCE, MEASURED
        src_bin,_=QFileDialog.getOpenFileName(self,'Schwesterstand: BIN mit Definition',str(Path.home()),
                                              'Firmware (*.bin *.ori);;Alle Dateien (*)')
        if not src_bin:return
        src_def,_=QFileDialog.getOpenFileName(self,'Definition des Schwesterstands',str(Path(src_bin).parent),
                                              'Definitionen (*.xdf *.a2l *.xml *.csv);;Alle Dateien (*)')
        if not src_def:return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            source=BinaryImage.from_file(src_bin)
            maps=definition_maps(src_def,source)
            result=transfer_names(source,self.image,maps)
        except (OSError,ValueError) as exc:
            QApplication.restoreOverrideCursor()
            self.warning('Namensübertragung',exc);return
        QApplication.restoreOverrideCursor()
        counts={e:sum(t.evidence==e for t in result) for e in EVIDENCE}
        lines='\n'.join(f'  {e}: {n} (gemessen richtig: {MEASURED[e]})' for e,n in counts.items() if n)
        answer=QMessageBox.question(self,'Namen aus Schwesterstand',
            f'{len(result)} von {len(maps)} Kennfeldern des Schwesterstands lassen sich in dieser Datei belegen:\n'
            f'{lines or "  keine"}\n\nVerschoben wird nach Ankern, die in beiden Dateien genau einmal vorkommen. '
            'Ohne Beleg am Zielort wird nichts vorgeschlagen.\n\nAls UNGEPRÜFTE Vorschläge übernehmen? '
            '(BIN bleibt unverändert)',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        existing={(m.offset,m.rows,m.cols) for m in self.maps}
        added=0
        for t in result:
            m=t.target
            if (m.offset,m.rows,m.cols) in existing:continue
            self.maps.append(m);existing.add((m.offset,m.rows,m.cols));added+=1
        self.maps.sort(key=lambda m:m.offset)
        self.refresh_map_list();self.update_status()
        self.statusBar().showMessage(f'{added} Namensvorschläge aus dem Schwesterstand übernommen · ungeprüft',8000)

    def toggle_favorite(self):
        if self.selected:
            self.selected.favorite=not self.selected.favorite
            self.refresh_map_list()

    def set_map_folder(self):
        if self.selected:
            folder,ok=QInputDialog.getText(self,'Kennfeldgruppe','Ordner / Gruppe',text=self.selected.folder)
            if ok:
                self.selected.folder=folder.strip()
                self.refresh_map_list()

    def log_to_map(self):
        if self.require_image():
            LogAnalyzerDialog(self).exec()

    def open_map_tab(self):
        if not self.image or not self.selected:
            return
        for pane in self.map_editors:
            if pane.definition is self.selected:
                self.tabs.setCurrentWidget(pane)
                return
        pane=MapEditorPane(self.image,self.selected,self.on_edited,self)
        pane.model.dark=self.theme=='dark'
        self.map_editors.append(pane)
        index=self.tabs.addTab(pane,self.selected.name)
        self.tabs.setCurrentIndex(index)
        close=QPushButton('×')
        close.setFixedWidth(25)
        close.clicked.connect(lambda *_:self.close_map_tab(pane))
        from PySide6.QtWidgets import QTabBar
        self.tabs.tabBar().setTabButton(index,QTabBar.ButtonPosition.RightSide,close)

    def sync_map_editor(self,index):
        pane=self.tabs.widget(index)
        if isinstance(pane,MapEditorPane) and self.selected is not pane.definition:
            self.select_map(pane.definition,show_table=False)

    def close_map_tab(self,pane):
        self.tabs.removeTab(self.tabs.indexOf(pane))
        self.map_editors.remove(pane)
        pane.deleteLater()

    def edit_selected_cells(self):
        if not self.image or not self.selected:
            return
        pane=self.tabs.currentWidget()
        if isinstance(pane,MapEditorPane):
            m,view=pane.definition,pane.table
        else:
            m,view=self.selected,self.map_table
        cells=[(i.row(),i.column()) for i in view.selectionModel().selectedIndexes()]
        SurfaceEditDialog(self.image,m,cells,self.on_edited,self).exec()

    def edit_axes(self):
        if self.image and self.selected and AxisDialog(self.image,self.selected,self).exec():
            self.on_edited()

    def execute_recipe(self):
        if not self.require_image():
            return
        p,_=QFileDialog.getOpenFileName(self,'JSON-Bearbeitungsrezept','','JSON (*.json)')
        if not p:
            return
        from ..core.editing import plan_recipe
        from ..core.workflows import apply_batch
        try:
            if Path(p).stat().st_size>5*1024**2:
                raise ValueError('Rezept zu groß')
            preview=plan_recipe(self.image,self.maps,json.loads(Path(p).read_text(encoding='utf-8')))
            dialog=QDialog(self)
            dialog.setWindowTitle('Rezept · vollständige Byte-Vorschau')
            dialog.resize(900,600)
            layout=QVBoxLayout(dialog)
            model=RowsModel(['Offset','Vorher','Nachher'],[(f'0x{pos:X}',self.image.read(pos,len(data)).hex(' '),data.hex(' ')) for pos,data in preview.updates],dialog)
            view=QTableView()
            view.setModel(model)
            layout.addWidget(view)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec():
                apply_batch(self.image,preview)
                self.on_edited()
        except Exception as exc:
            self.warning('Rezept abgelehnt',exc)

    def import_zip(self):
        if not self.ok_to_replace():
            return
        p,_=QFileDialog.getOpenFileName(self,'Firmware-ZIP','','ZIP (*.zip)')
        if not p:
            return
        from ..formats.archive import archive_members,read_archive_image
        try:
            members=archive_members(p)
            if not members:
                raise ValueError('Keine BIN/ORI-Datei im ZIP')
            member,ok=QInputDialog.getItem(self,'ZIP-Eintrag','Firmwaredatei auswählen',members,0,False)
            if ok:
                image=read_archive_image(p,member)
                self.load_state(image,[],[],f'ZIP-Quelle: {p}\nEintrag: {member}',None)
        except Exception as exc:
            self.warning('ZIP-Import abgelehnt',exc)

    def browse_projects(self):
        dialog=QDialog(self)
        dialog.setWindowTitle('Durchsuchbare Projektdatenbank')
        dialog.resize(950,600)
        layout=QVBoxLayout(dialog)
        query=QLineEdit()
        query.setPlaceholderText('Projektname, Notiz, Kennfeldname, Typ oder Gruppe')
        layout.addWidget(query)
        view=QTableView()
        model=RowsModel(['Projekt','Bytes','Kennfelder','Original-SHA256','Pfad'],parent=dialog)
        view.setModel(model)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(view,1)
        found=[]
        def search():
            found[:]=self.project_store.search(query.text())
            model.set_rows([(r['name'],r['bytes'],r['maps'],r['original_sha256'],r['path']) for r in found])
        def index_existing():
            paths,_=QFileDialog.getOpenFileNames(dialog,'Projekte indexieren','','ECU Studio (*.ecustudio)')
            for path in paths:
                try:
                    self.project_store.index(path)
                except Exception as exc:
                    self.warning('Indexierung fehlgeschlagen',exc)
            search()
        def open_selected():
            i=view.currentIndex()
            if not i.isValid() or not self.ok_to_replace():
                return
            path=found[i.row()]['path']
            try:
                image,maps,bookmarks,notes=load_project(path)
                versions=read_project_snapshots(path,image)
                self.load_state(image,maps,bookmarks,notes,path)
                self.snapshots=versions
                self.saved_fingerprint=self.project_state()
                self.update_diff()
                dialog.accept()
            except Exception as exc:
                self.warning('Projekt konnte nicht geöffnet werden',exc)
        query.textChanged.connect(search)
        view.doubleClicked.connect(lambda *_:open_selected())
        line=QHBoxLayout()
        for label,fn in (('Bestehende Projekte indexieren …',index_existing),('Ausgewähltes Projekt öffnen',open_selected)):
            button=QPushButton(label)
            button.clicked.connect(fn)
            line.addWidget(button)
        layout.addLayout(line)
        search()
        dialog.exec()

