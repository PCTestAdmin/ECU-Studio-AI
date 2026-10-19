"""Reviewed map pairing across firmware projects, with physical-cell evidence."""
import json
from pathlib import Path
from PySide6.QtCore import QThread
from PySide6.QtWidgets import (QLabel,QPushButton,QHBoxLayout,QDoubleSpinBox,
    QFileDialog,QAbstractItemView,QDialog)
from .next_dialogs import AsyncDialog,table
from ..core.model import MapDefinition,load_project
from ..core.map_matching import match_map_catalogs,compare_surfaces
from ..core.storage import atomic_write


class MapMatchingDialog(AsyncDialog):
    def __init__(self,parent,source=None,source_maps=None):
        super().__init__(parent,'Softwarestände · mathematischer Kennfeldabgleich')
        self.window=parent;self.source=source;self.source_maps=list(source_maps or [])
        self.target=parent.image
        self.target_key=[m.asdict() for m in parent.maps]
        self.target_maps=[MapDefinition(**m) for m in self.target_key]
        self.report=None;self.selected_links={}
        self.layout_.addWidget(QLabel('Vergleicht ORI-Werte und physikalische Achsen. Ähnliche Form allein bestätigt keine Funktion.'))
        line=QHBoxLayout();open_button=QPushButton('Referenzprojekt laden …');open_button.clicked.connect(self.open_source)
        line.addWidget(open_button);self.source_label=QLabel('Referenz: '+(source.digest[:12] if source else 'nicht gewählt'))
        line.addWidget(self.source_label,1);self.layout_.addLayout(line)
        line=QHBoxLayout();line.addWidget(QLabel('Normierte Abweichung (für reine Formsuche)'))
        self.tolerance=QDoubleSpinBox();self.tolerance.setRange(0,1);self.tolerance.setDecimals(3);self.tolerance.setValue(.15)
        self.tolerance.valueChanged.connect(self.invalidate);line.addWidget(self.tolerance)
        button=QPushButton('Kennfelder abgleichen');button.clicked.connect(self.compare);line.addWidget(button);self.layout_.addLayout(line)
        self.matches_view,self.matches_model=table(['Quelle → Ziel','Rangwert','RMSE','Max. Differenz','Befund'])
        self.matches_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.matches_view.selectionModel().currentRowChanged.connect(self.show_cells)
        self.layout_.addWidget(self.matches_view,2)
        self.details=QLabel('Keine Paarungen berechnet. Achsen und Einheiten müssen in den Definitionen belegt sein.')
        self.details.setWordWrap(True);self.layout_.addWidget(self.details)
        self.cells_view,self.cells_model=table(['Zeile','Spalte','Referenz auf Zielraster','Ziel-ORI','Differenz'])
        self.layout_.addWidget(self.cells_view,2)
        line=QHBoxLayout()
        for title,method in [('Zielkennfeld öffnen',self.open_target),('Paarung für Transfer verwenden',self.accept_links),
                             ('Abgleich als JSON …',self.export_report),('Schließen',self.reject)]:
            button=QPushButton(title);button.clicked.connect(method);line.addWidget(button)
        self.layout_.addLayout(line)

    def current_target(self):
        if self.window.image is not self.target or [m.asdict() for m in self.window.maps]!=self.target_key:
            raise ValueError('Zieldefinitionen haben sich geändert: Dialog neu öffnen')

    def invalidate(self,*_):
        self.task_generation+=1;self.report=None;self.selected_links={}
        self.matches_model.set_rows([]);self.cells_model.set_rows([])

    def open_source(self):
        if self.worker and self.worker.isRunning():return
        path,_=QFileDialog.getOpenFileName(self,'Referenzprojekt mit Definitionen','','ECU Studio (*.ecustudio)')
        if path:self.run_task(lambda:load_project(path),self.source_loaded)

    def source_loaded(self,result):
        self.source,self.source_maps,_,_=result
        self.source_label.setText('Referenz: '+self.source.digest[:12]);self.invalidate()

    def compare(self):
        if self.source is None:self.error('Referenzprojekt wählen');return
        try:self.current_target()
        except ValueError as exc:self.error(exc);return
        self.invalidate();source=self.source;target=self.target
        maps=[MapDefinition(**m.asdict()) for m in self.source_maps];tolerance=self.tolerance.value()
        self.run_task(lambda:match_map_catalogs(source,target,maps,self.target_maps,tolerance=tolerance,
                       cancelled=lambda:QThread.currentThread().isInterruptionRequested()),self.show_report)

    def show_report(self,report):
        self.report=report
        self.matches_model.set_rows([(m['source_name']+' → '+m['target_name'],f"{m['score']:.4f}",
            f"{m['rmse']:.6g}",f"{m['maximum_difference']:.6g}",
            ('eindeutiger Vorschlag' if m['unique'] else 'mehrdeutig')+(' · interpoliert' if m['interpolated'] else ''))
            for m in report['matches']])
        excluded='; '.join(f'{reason}: {n}' for reason,n in report['excluded'].items())
        self.details.setText(f"{report['compared_pairs']} Paare geprüft; {len(report['unmatched_sources'])} Quellen ohne kompatiblen Zielkandidaten. "+
            ('Suche unvollständig; keine Paarung freigegeben. ' if report['truncated'] or report['cancelled'] else '')+
            ('Ausgelassen: '+excluded if excluded else 'Alle Paarungen bleiben prüfpflichtig.'))

    def selected_match(self):
        index=self.matches_view.currentIndex()
        return self.report['matches'][index.row()] if self.report and index.isValid() else None

    def show_cells(self,*_):
        match=self.selected_match()
        if not match:return
        m=self.source_maps[match['source_index']];t=self.target_maps[match['target_index']]
        try:_,a,b=compare_surfaces(self.source,self.target,m,t)
        except Exception as exc:self.error(exc);return
        rows=[]
        for r in range(t.rows):
            for c in range(t.cols):
                if len(rows)<1024:rows.append((r,c,float(a[r,c]),float(b[r,c]),float(b[r,c]-a[r,c])))
        self.cells_model.set_rows(rows)
        self.details.setText(match['evidence']+f' Einheit: {t.unit}. Zellvorschau: {len(rows)}/{t.rows*t.cols}.')

    def open_target(self):
        try:self.current_target()
        except ValueError as exc:self.error(exc);return
        match=self.selected_match()
        if match:self.window.select_map(self.window.maps[match['target_index']])

    def accept_links(self):
        try:
            self.current_target()
            indices=sorted(i.row() for i in self.matches_view.selectionModel().selectedRows())
            if not indices or not self.report:raise ValueError('Paarungen zuerst in der Tabelle auswählen')
            chosen=[self.report['matches'][i] for i in indices]
            if not all(m['unique'] and m['source_verified'] and m['target_verified'] for m in chosen):
                raise ValueError('Nur eindeutige Vorschläge mit fachlich bestätigten Quell- und Zieldefinitionen sind übertragbar')
            if len({m['source_index'] for m in chosen})!=len(chosen) or len({m['target_index'] for m in chosen})!=len(chosen):
                raise ValueError('Quelle oder Ziel mehrfach ausgewählt')
            self.selected_links={m['source_index']:m['target_index'] for m in chosen}
        except (ValueError,IndexError) as exc:self.error(exc);return
        self.accept()

    def export_report(self):
        if not self.report:return
        path,_=QFileDialog.getSaveFileName(self,'Mathematischer Abgleich','map-matching.json','JSON (*.json)')
        if path:
            try:atomic_write(path,json.dumps(self.report,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8'),
                    protected=(self.source.path,self.target.path))
            except Exception as exc:self.error(exc)
