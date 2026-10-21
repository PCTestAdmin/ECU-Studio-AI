"""Reviewable desktop workflows for transfer, logs and surface editing."""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import replace
from PySide6.QtCore import Qt, QThread, Signal, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QPushButton,QFileDialog,QMessageBox,QCheckBox,QComboBox,QTableView,QTableWidget,
    QPlainTextEdit,QProgressBar,QDialogButtonBox,QTabWidget,QWidget,QDoubleSpinBox,
    QHeaderView,QAbstractItemView)
from ..core.i18n import translated_roles
from ..core.model import load_project, MapDefinition
from ..core.smart_transfer import FirmwareIdentity, plan_transfer, apply_transfer, suggest_links
from ..core.log_analyzer import (CHANNELS, UNITS, infer_header, inspect_log_headers, read_log,
                                 analyze_log, map_occupancy, write_log_report)
from ..core.editing import plan_surface_edit, plan_recipe
from ..core.workflows import apply_batch
from ..core.storage import atomic_write
from .views import MapTableModel, Map2DView, Map3DView, MapCurveView


class RowsModel(QAbstractTableModel):
    def __init__(self,headers,rows=(),parent=None):
        super().__init__(parent)
        self.headers=headers
        self.rows=list(rows)

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows=list(rows)
        self.endResetModel()

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    @translated_roles
    def headerData(self,i,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole:
            return self.headers[i] if orientation==Qt.Orientation.Horizontal else str(i)

    @translated_roles
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role==Qt.ItemDataRole.DisplayRole:
            return str(self.rows[index.row()][index.column()])


class Task(QThread):
    result=Signal(object)
    failed=Signal(str)
    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn=fn
    def run(self):
        try:
            result=self.fn()
            if not self.isInterruptionRequested():
                self.result.emit(result)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class AsyncDialog(QDialog):
    def __init__(self,parent,title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1120,760)
        self.layout_=QVBoxLayout(self)
        self.progress=QProgressBar()
        self.progress.setRange(0,0)
        self.progress.hide()
        self.worker=None
        self.task_generation=0
        self.layout_.addWidget(self.progress)
        self._pending_close=False

    def error(self,err):
        QMessageBox.warning(self,'Vorgang nicht möglich',str(err))

    def run_task(self,fn,callback):
        if self.worker and self.worker.isRunning():
            return
        self.progress.show()
        generation=self.task_generation
        self.worker=Task(fn,self)
        self.worker.result.connect(lambda value:callback(value) if self.task_generation==generation else None)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.task_finished)
        self.worker.start()

    def task_finished(self):
        self.progress.hide()
        if self._pending_close:
            self.reject()

    def reject(self):
        if self.worker and self.worker.isRunning():
            self._pending_close=True
            self.worker.requestInterruption()
            self.progress.setFormat('Ergebnis wird verworfen; laufenden Schritt abschließen …')
            return
        super().reject()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            event.accept()


def table(headers):
    view=QTableView()
    model=RowsModel(headers,parent=view)
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return view,model


class SmartTransferDialog(AsyncDialog):
    def __init__(self,parent):
        super().__init__(parent,'AI Smart Map Transfer · Vorschau und Freigabe')
        self.window=parent
        self.source=None
        self.source_maps=[]
        self.plan=None
        self.proposals=[]
        self.links={}
        self.link_target_key=None
        self.location_report=None
        self.layout_.addWidget(QLabel('Quelle: gespeichertes ORI/MOD-Projekt. Ziel: aktuell geöffnete Firmware.'))
        line=QHBoxLayout()
        source_button=QPushButton('Quellprojekt öffnen …')
        source_button.clicked.connect(self.open_source)
        line.addWidget(source_button)
        self.source_name=QLabel('Kein Quellprojekt')
        line.addWidget(self.source_name,1)
        self.layout_.addLayout(line)
        form=QFormLayout()
        self.family=QLineEdit()
        self.hardware_source=QLineEdit()
        self.hardware_target=QLineEdit()
        self.software_source=QLineEdit()
        self.software_target=QLineEdit()
        self.evidence=QLineEdit()
        self.evidence.setPlaceholderText('Prüfprotokoll / Herkunft und Nachweis der Kompatibilität')
        for title,field in (('ECU-Familie beider Dateien',self.family),('Quell-Hardware',self.hardware_source),
                            ('Ziel-Hardware',self.hardware_target),('Quell-Softwarestand',self.software_source),
                            ('Ziel-Softwarestand',self.software_target),('Prüfnachweis',self.evidence)):
            form.addRow(title,field)
            field.textChanged.connect(self.invalidate)
        self.mode=QComboBox()
        self.mode.addItems(['Physikalische Differenz','Relative Änderung (%)'])
        self.mode.currentIndexChanged.connect(self.invalidate)
        form.addRow('Übertragungsart',self.mode)
        self.interpolate=QCheckBox('Abweichende Achsenraster linear/bilinear interpolieren (ohne Extrapolation)')
        self.interpolate.toggled.connect(self.invalidate)
        form.addRow(self.interpolate)
        self.reviewed=QCheckBox('Ich habe Familie, Hardware und Softwarekompatibilität beider Dateien fachlich geprüft.')
        self.reviewed.toggled.connect(self.invalidate)
        form.addRow(self.reviewed)
        self.layout_.addLayout(form)
        line=QHBoxLayout()
        preview=QPushButton('Änderungen vergleichen')
        preview.clicked.connect(self.preview)
        line.addWidget(preview)
        locate=QPushButton('Verschobene / ähnliche Rohstrukturen suchen')
        locate.clicked.connect(self.locate)
        line.addWidget(locate)
        match_button=QPushButton('Kennfelder mathematisch abgleichen')
        match_button.clicked.connect(self.match_grids);line.addWidget(match_button)
        self.layout_.addLayout(line)
        self.maps_view,self.maps_model=table(['Quelle → Ziel','Quelloffset','Zieloffset','Status','Zellen / Konflikt'])
        self.maps_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.maps_view.selectionModel().currentRowChanged.connect(self.show_cells)
        self.layout_.addWidget(self.maps_view,1)
        self.cells_view,self.cells_model=table(['Zeile','Spalte','Quell-ORI','Quell-MOD','Ziel vorher','Ziel nachher','Zieloffset','Delta / %','Interpolation'])
        self.layout_.addWidget(self.cells_view,1)
        self.layout_.addWidget(QLabel('Nur bestätigte Zieldefinitionen und passende Achsen sind übertragbar. Keine Flashfreigabe.'))
        line=QHBoxLayout()
        save=QPushButton('Vorschau als JSON …')
        save.clicked.connect(self.export_plan)
        line.addWidget(save)
        self.apply_button=QPushButton('Ausgewählte Kennfelder ausdrücklich übernehmen')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        line.addWidget(self.apply_button)
        close=QPushButton('Schließen')
        close.clicked.connect(self.reject)
        line.addWidget(close)
        self.layout_.addLayout(line)
        from ..core.profiles import identify_profile
        known=identify_profile(self.window.image)
        if known.identified:
            self.family.setText(known.family)
            self.software_target.setText(known.software_version or known.calibration_id or '')

    def invalidate(self,*_):
        self.task_generation+=1
        self.plan=None
        self.apply_button.setEnabled(False)

    def open_source(self):
        if self.worker and self.worker.isRunning():
            return
        p,_=QFileDialog.getOpenFileName(self,'Quellprojekt','','ECU Studio (*.ecustudio)')
        if p:
            self.run_task(lambda:load_project(p),lambda result:self.source_loaded(p,result))

    def source_loaded(self,path,result):
        self.source,self.source_maps,_,_=result
        self.links={};self.link_target_key=None
        self.location_report=None
        self.reviewed.setChecked(False)
        self.hardware_source.clear();self.software_source.clear();self.evidence.clear()
        from ..core.profiles import identify_profile
        known=identify_profile(self.source)
        if known.identified:
            self.software_source.setText(known.software_version or known.calibration_id or '')
            if not self.family.text():self.family.setText(known.family)
        self.source_name.setText(Path(path).name+f' · {self.source.dirty_bytes} geänderte Bytes')
        self.invalidate()

    def preview(self):
        if self.source is None:
            self.error('Quellprojekt auswählen')
            return
        if self.links and self.link_target_key!=[m.asdict() for m in self.window.maps]:
            self.error('Zieldefinitionen geändert: Kennfelder erneut mathematisch abgleichen');return
        source_identity=FirmwareIdentity(self.source.digest,self.family.text(),self.hardware_source.text(),
                                         self.software_source.text(),self.evidence.text(),self.reviewed.isChecked())
        target_identity=FirmwareIdentity(self.window.image.digest,self.family.text(),self.hardware_target.text(),
                                         self.software_target.text(),self.evidence.text(),self.reviewed.isChecked())
        mode='delta' if self.mode.currentIndex()==0 else 'percent'
        interpolate=self.interpolate.isChecked();links=dict(self.links) or None
        self.invalidate()
        self.run_task(lambda:plan_transfer(self.source,self.window.image,self.source_maps,self.window.maps,
                      source_identity=source_identity,target_identity=target_identity,mode=mode,
                      interpolate=interpolate,links=links),self.show_plan)

    def show_plan(self,plan):
        self.plan=plan
        self.maps_model.set_rows([(m.source+' → '+m.target,f'0x{m.source_offset:X}',f'0x{m.target_offset:X}',
                                   m.status,len(m.cells) if m.status=='ready' else m.evidence) for m in plan.maps])
        self.apply_button.setEnabled(any(m.status=='ready' and m.cells for m in plan.maps))
        self.cells_model.set_rows([])

    def show_cells(self,current,*_):
        if self.plan and current.isValid() and current.row()<len(self.plan.maps):
            self.cells_model.set_rows([(c.row,c.col,c.source_original,c.source_modified,c.target_before,
                                       c.target_after,f'0x{c.offset:X}',c.change_value,'ja' if c.interpolated else 'nein') for c in self.plan.maps[current.row()].cells])

    def match_grids(self):
        from .map_matching_dialog import MapMatchingDialog
        if self.source is None:self.error('Quellprojekt auswählen');return
        dialog=MapMatchingDialog(self.window,self.source,self.source_maps)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if dialog.source is not self.source:
                self.source_loaded('Referenzprojekt',(dialog.source,dialog.source_maps,[],''))
            self.source=dialog.source;self.source_maps=dialog.source_maps
            self.links=dialog.selected_links
            self.link_target_key=dialog.target_key
            self.invalidate()
            self.source_name.setText(f'{len(self.links)} mathematische Paarungen ausgewählt')

    def locate(self):
        if self.source is None:
            self.error('Quellprojekt auswählen')
            return
        from ..core.map_matching import locate_reference_surfaces
        self.run_task(lambda:locate_reference_surfaces(self.source,self.window.image,self.source_maps,
            cancelled=lambda:QThread.currentThread().isInterruptionRequested()),self.show_locations)

    def show_locations(self,report):
        self.location_report=report
        maps=[MapDefinition(**h['proposed']) for h in report['hits'] if h['unique']]
        self.show_links(maps)
        self.maps_model.set_rows([(h['proposed']['name'],f"0x{self.source_maps[h['source_index']].offset:X}",
            f"0x{h['target_offset']:X}",'ungeprüft' if h['unique'] else 'mehrdeutig',
            f"NRMSE {h['normalized_rmse']:.5f}; Alternative {h['second_score']:.4f}") for h in report['hits']])
        if not maps:
            self.source_name.setText(f"Keine eindeutige Fundstelle; {report['references_considered']} Referenzen geprüft, "
                                    f"{report['references_omitted']} weitere ausgelassen. Details: JSON-Export.")

    def show_links(self,maps):
        self.invalidate()
        self.proposals=maps
        self.maps_model.set_rows([(m.name,'',f'0x{m.offset:X}','UNGEPRÜFT',m.notes) for m in maps])
        if maps and QMessageBox.question(self,'Ungeprüfte Fundstellen',
                f'{len(maps)} mathematische Struktur-Fundstellen. Zielachsen, Skalierung und Funktion sind ungeprüft. '
                'Als Rohdatenvorschläge in den Katalog aufnehmen?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            existing={(m.offset,m.name) for m in self.window.maps}
            self.window.maps.extend(m for m in maps if (m.offset,m.name) not in existing)
            self.window.refresh_map_list()

    def export_plan(self):
        if not self.plan and not self.location_report:
            return
        p,_=QFileDialog.getSaveFileName(self,'Transfervorschau','smart-transfer.json','JSON (*.json)')
        if p:
            try:
                atomic_write(p,json.dumps(self.plan.report() if self.plan else self.location_report,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8'),
                             protected=(self.window.image.path,self.source.path if self.source else None))
            except Exception as exc:
                self.error(exc)

    def apply(self):
        if not self.plan:
            return
        selected=sorted(i.row() for i in self.maps_view.selectionModel().selectedRows())
        if not selected:
            self.error('Kennfelder in der Vorschau auswählen')
            return
        if QMessageBox.question(self,'Transfer bestätigen',f'{len(selected)} ausgewählte Kennfelder gemäß Zellvorschau übernehmen?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        try:
            report=self.plan.report()
            apply_transfer(self.window.image,self.plan,selected,confirmed=True)
            report['selected_maps']=selected
            self.window.image.journal.append({'label':'Smart Map Transfer · Freigabe','report':report})
            self.window.on_edited()
            self.invalidate()
            QMessageBox.information(self,'Transfer übernommen','Änderungen übernommen; mit Strg+Z rückgängig. Projekt zum dauerhaften Audit speichern.')
        except Exception as exc:
            self.error(exc)


class HeatModel(RowsModel):
    def set_rows(self,rows):
        rows=list(rows)
        self.maximum=max(1.,max((max(r) for r in rows),default=1.))
        super().set_rows(rows)

    @translated_roles
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            value=self.rows[index.row()][index.column()]
            if role==Qt.ItemDataRole.DisplayRole:
                return f'{value:.2f}'
            if role==Qt.ItemDataRole.BackgroundRole:
                return QColor(40,140,200,round(220*value/self.maximum))


class LogAnalyzerDialog(AsyncDialog):
    def __init__(self,parent):
        super().__init__(parent,'AI Log-to-Map Analyzer')
        self.window=parent
        self.path=None
        self.log=None
        self.analysis=None
        self.occupancy=None
        self.map_refs=list(parent.maps)
        self.active_map=None
        open_button=QPushButton('CSV-Log öffnen …')
        open_button.clicked.connect(self.open_log)
        self.layout_.addWidget(open_button)
        self.mapping=QTableWidget(0,3)
        self.mapping.setHorizontalHeaderLabels(['CSV-Kanal','Messgröße (leer = ignorieren)','Quell-Einheit'])
        self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout_.addWidget(self.mapping,1)
        analyze=QPushButton('Zugeordnete Kanäle analysieren')
        analyze.clicked.connect(self.analyze)
        self.layout_.addWidget(analyze)
        self.summary=QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.layout_.addWidget(self.summary,1)
        row=QHBoxLayout()
        self.map_combo=QComboBox()
        self.map_combo.addItems([m.name for m in self.map_refs])
        self.map_combo.currentIndexChanged.connect(self.invalidate_heatmap)
        row.addWidget(self.map_combo,1)
        bind=QPushButton('Achsen / Kanäle definieren …')
        bind.clicked.connect(self.bind_axes)
        row.addWidget(bind)
        heat=QPushButton('Belegungs-Heatmap berechnen')
        heat.clicked.connect(self.heatmap)
        row.addWidget(heat)
        self.layout_.addLayout(row)
        self.heat=QTableView()
        self.heat_model=HeatModel([])
        self.heat.setModel(self.heat_model)
        self.heat.clicked.connect(self.open_cell)
        self.layout_.addWidget(self.heat,2)
        self.layout_.addWidget(QLabel('Heatmap: bilinear gewichtete Messpunkte. Eine tatsächliche ECU-Kennfeldwahl ist damit nicht bewiesen.'))
        export=QPushButton('Diagnosebericht als HTML speichern …')
        export.clicked.connect(self.export)
        self.layout_.addWidget(export)

    def open_log(self):
        if self.worker and self.worker.isRunning():
            return
        p,_=QFileDialog.getOpenFileName(self,'Messlog öffnen','','CSV (*.csv *.tsv *.txt);;Alle Dateien (*)')
        if p:
            self.path=p
            self.log=None
            self.analysis=None
            self.invalidate_heatmap()
            self.run_task(lambda:inspect_log_headers(p),self.show_headers)

    def show_headers(self,headers):
        from PySide6.QtWidgets import QTableWidgetItem
        self.mapping.setRowCount(len(headers))
        for row,h in enumerate(headers):
            item=QTableWidgetItem(h)
            item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
            self.mapping.setItem(row,0,item)
            key,unit=infer_header(h)
            combo=QComboBox()
            combo.addItems(['',*CHANNELS])
            combo.setCurrentText(key)
            self.mapping.setCellWidget(row,1,combo)
            self.mapping.setItem(row,2,QTableWidgetItem(unit))
        self.summary.setPlainText('Kanalzuordnung und Einheiten prüfen. Unbekannte Kanäle bleiben unberücksichtigt.')

    def analyze(self):
        if not self.path:
            return
        overrides={self.mapping.item(r,0).text():(self.mapping.cellWidget(r,1).currentText(),self.mapping.item(r,2).text())
                   for r in range(self.mapping.rowCount())}
        path=self.path
        def process():
            log=read_log(path,overrides)
            return log,analyze_log(log)
        self.run_task(process,self.show_analysis)

    def show_analysis(self,result):
        self.log,self.analysis=result
        self.invalidate_heatmap()
        display={k:v for k,v in self.analysis.items() if k!='abnormal_mask'}
        self.summary.setPlainText(json.dumps(display,indent=2,ensure_ascii=False))

    def invalidate_heatmap(self,*_):
        self.occupancy=None
        self.active_map=None
        self.heat_model.headers=[]
        self.heat_model.set_rows([])

    def selected_map(self):
        i=self.map_combo.currentIndex()
        return self.map_refs[i] if 0<=i<len(self.map_refs) else None

    def bind_axes(self):
        m=self.selected_map()
        if m:
            if AxisDialog(self.window.image,m,self).exec():
                self.invalidate_heatmap()
                self.window.on_edited()

    def heatmap(self):
        m=self.selected_map()
        if self.log is None or m is None:
            self.error('Zuerst Log analysieren und Kennfeld auswählen')
            return
        try:
            self.occupancy=map_occupancy(self.log,m,self.analysis['abnormal_mask'])
            self.active_map=m
            self.heat_model.headers=[f'{x:g}' for x in m.axes_x]
            self.heat_model.set_rows(self.occupancy['counts'])
            self.summary.appendPlainText(f"\n{self.occupancy['mapped_samples']} Messpunkte zugeordnet; {self.occupancy['excluded_samples']} außerhalb/ungültig.")
        except Exception as exc:
            self.error(exc)

    def open_cell(self,index):
        if self.active_map:
            self.window.select_map(self.active_map)
            self.window.focus_map_cell(index.row(),index.column())

    def export(self):
        if self.log is None:
            return
        p,_=QFileDialog.getSaveFileName(self,'Diagnosebericht','log-to-map.html','HTML (*.html)')
        if p:
            try:
                write_log_report(p,self.log,self.analysis,self.occupancy,protected=(self.window.image.path,))
            except Exception as exc:
                self.error(exc)


class AxisDialog(QDialog):
    def __init__(self,image,m,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Physikalische Achsen und Log-Eingangssignale')
        self.image,self.m=image,m
        form=QFormLayout(self)
        self.x=QLineEdit(', '.join(map(str,m.axes_x)))
        self.y=QLineEdit(', '.join(map(str,m.axes_y)))
        form.addRow(f'X: {m.cols} Stützstellen (Komma getrennt)',self.x)
        form.addRow(f'Y: {m.rows} Stützstellen (Komma getrennt)',self.y)
        self.xc,self.yc=QComboBox(),QComboBox()
        for field,current in ((self.xc,m.axis_x_channel),(self.yc,m.axis_y_channel)):
            field.addItems(['',*CHANNELS])
            field.setCurrentText(current)
        self.xu,self.yu=QComboBox(),QComboBox()
        for field,current in ((self.xu,m.axis_x_unit),(self.yu,m.axis_y_unit)):
            field.addItems(['',*dict.fromkeys(UNITS.values())])
            field.setCurrentText(current)
        for title,field in (('X-Eingangssignal',self.xc),('X-Einheit',self.xu),('Y-Eingangssignal',self.yc),('Y-Einheit',self.yu)):
            form.addRow(title,field)
        form.addRow(QLabel('Die Werte beschreiben die Definition; Firmware-Achsbytes werden hier nicht verändert.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        import math
        try:
            axes=[]
            for text,n in ((self.x.text(),self.m.cols),(self.y.text(),self.m.rows)):
                values=[float(v.strip()) for v in text.split(',') if v.strip()]
                if values and (len(values)!=n or not all(math.isfinite(v) for v in values)):
                    raise ValueError(f'{n} endliche Stützstellen erforderlich')
                if len(values)>1 and not (all(a<b for a,b in zip(values,values[1:])) or all(a>b for a,b in zip(values,values[1:]))):
                    raise ValueError('Achsen müssen streng monoton sein')
                axes.append(values)
            self.m.axes_x,self.m.axes_y=axes
            self.m.axis_x_channel,self.m.axis_y_channel=self.xc.currentText(),self.yc.currentText()
            self.m.axis_x_unit,self.m.axis_y_unit=self.xu.currentText(),self.yu.currentText()
            self.m.source='manual'
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self,'Achsen ungültig',str(exc))


class SurfaceEditDialog(QDialog):
    def __init__(self,image,m,cells,edited,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Zellenauswahl bearbeiten · Vorschau')
        self.resize(850,570)
        self.image,self.m,self.cells,self.edited=image,m,cells,edited
        self.preview=None
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel(f'{m.name} · {len(cells)} ausgewählte Zellen'))
        self.mode=QComboBox()
        self.operations=['add','percent','set','interpolate_x','interpolate_y','interpolate_xy','smooth']
        self.mode.addItems(['Absolut addieren','Relativ (%)','Wert setzen','Linear über X','Linear über Y','Bilinear','3×3 glätten'])
        self.amount=QDoubleSpinBox()
        self.amount.setRange(-1e12,1e12)
        self.amount.setDecimals(6)
        layout.addWidget(self.mode)
        layout.addWidget(self.amount)
        self.view,self.model=table(['Offset','Vorher (Hex)','Nachher (Hex)'])
        layout.addWidget(self.view,1)
        self.info=QLabel()
        layout.addWidget(self.info)
        for field,signal in ((self.mode,self.mode.currentIndexChanged),(self.amount,self.amount.valueChanged)):
            signal.connect(self.invalidate)
        line=QHBoxLayout()
        for label,fn in (('Vorschau berechnen',self.calculate),('Rezept speichern …',self.save_recipe),('Übernehmen',self.apply),('Schließen',self.reject)):
            button=QPushButton(label)
            button.clicked.connect(fn)
            line.addWidget(button)
        layout.addLayout(line)

    def invalidate(self,*_):
        self.preview=None

    def calculate(self):
        try:
            self.preview=plan_surface_edit(self.image,self.m,self.operations[self.mode.currentIndex()],
                                           cells=self.cells,amount=self.amount.value())
            self.model.set_rows([(f'0x{p:X}',self.image.read(p,len(b)).hex(' '),b.hex(' ')) for p,b in self.preview.updates])
            self.info.setText(f'{self.preview.changed_cells} Zellen · {self.preview.changed_bytes} Bytes · '
                              f'{self.preview.before_min:g}…{self.preview.before_max:g} → {self.preview.after_min:g}…{self.preview.after_max:g}')
        except Exception as exc:
            self.preview=None
            QMessageBox.warning(self,'Vorschau fehlgeschlagen',str(exc))

    def apply(self):
        if self.preview is None:
            return
        try:
            apply_batch(self.image,self.preview)
            self.edited()
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self,'Bearbeitung abgelehnt',str(exc))

    def save_recipe(self):
        if self.preview is None:
            return
        p,_=QFileDialog.getSaveFileName(self,'Bearbeitungsrezept','map-recipe.json','JSON (*.json)')
        if p:
            payload={'schema':1,'source_sha256':self.image.digest,'operations':[{
                'map':self.m.name,'mode':self.operations[self.mode.currentIndex()],
                'amount':self.amount.value(),'cells':self.cells}]}
            try:
                atomic_write(p,json.dumps(payload,indent=2).encode('utf-8'),protected=(self.image.path,))
            except Exception as exc:
                QMessageBox.warning(self,'Rezept speichern fehlgeschlagen',str(exc))


class SlicesView(QWidget):
    def __init__(self,model):
        super().__init__()
        self.model=model
        model.modelReset.connect(self.update)
        model.dataChanged.connect(self.update)
    def paintEvent(self,event):
        values=self.model.values(max_samples=48)
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not values:
            p.drawText(20,30,'Kein Kennfeld')
            return
        lo=min(min(row) for row in values)
        hi=max(max(row) for row in values)
        for i,row in enumerate(values):
            p.setPen(QPen(QColor.fromHsv(int(180+100*i/max(1,len(values)-1)),160,230),1.5))
            points=[QPointF(25+j*(self.width()-50)/max(1,len(row)-1),
                            self.height()-25-(v-lo)/max(1e-12,hi-lo)*(self.height()-50)) for j,v in enumerate(row)]
            p.drawPolyline(QPolygonF(points))


class MapEditorPane(QWidget):
    def __init__(self,image,m,edited,parent=None):
        super().__init__(parent)
        self.definition=m
        layout=QVBoxLayout(self)
        self.model=MapTableModel()
        self.model.set_map(image,m)
        self.model.edited.connect(edited)
        buttons=QHBoxLayout()
        edit=QPushButton('Auswahl bearbeiten …')
        edit.clicked.connect(lambda:SurfaceEditDialog(image,m,
            [(i.row(),i.column()) for i in self.table.selectionModel().selectedIndexes()],edited,self).exec())
        buttons.addWidget(edit)
        axes=QPushButton('Achsen / Log-Kanäle …')
        axes.clicked.connect(lambda:self.edit_axes(image,m,edited))
        buttons.addWidget(axes)
        layout.addLayout(buttons)
        tabs=QTabWidget()
        self.table=QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tabs.addTab(self.table,'Tabelle')
        self.curves=MapCurveView(self.model)
        self.heatmap=Map2DView(self.model)
        self.surface=Map3DView(self.model)
        self.slices=SlicesView(self.model)
        self.curves.cellSelected.connect(self.select_cell)
        self.heatmap.cellSelected.connect(self.select_cell)
        for widget,title in ((self.curves,'2D / ORI-MOD'),(self.heatmap,'Heatmap'),(self.surface,'3D'),(self.slices,'Schichten')):
            tabs.addTab(widget,title)
        layout.addWidget(tabs)
        self.tabs=tabs

    def select_cell(self,row,col):
        self.table.setCurrentIndex(self.model.index(row,col))
        self.tabs.setCurrentWidget(self.table)

    def edit_axes(self,image,m,edited):
        if AxisDialog(image,m,self).exec():
            self.model.set_map(image,m)
            edited()

    def refresh(self):
        self.model.refresh()
        for widget in (self.curves.canvas,self.heatmap,self.surface,self.slices):
            widget.update()


class ModelToolsDialog(AsyncDialog):
    def __init__(self,parent):
        super().__init__(parent,'KI · Geprüftes Training und unabhängige Evaluation')
        self.window=parent
        self.report=None
        self.layout_.addWidget(QLabel('Neue Modelle werden als inaktive Kandidaten gespeichert. Eine reale Verbesserung muss separat nachgewiesen werden.'))
        line=QHBoxLayout()
        for label,fn in (('Installiertes Strukturtraining',self.show_installed_training),
                         ('Trainingsherkunft importieren …',self.import_provenance),
                         ('Bestätigten Modellkandidaten trainieren',self.train_candidate),
                         ('Holdout-Manifest evaluieren …',self.evaluate)):
            button=QPushButton(label)
            button.clicked.connect(fn)
            line.addWidget(button)
        self.layout_.addLayout(line)
        self.text=QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText('Erforderlich: fachlich bestätigte Definitionen, Nutzungsrechte und unabhängige ORI/MOD-Gruppen.\n'
                               'Synthetische Metriken werden getrennt von realer ECU-/TCU-Erkennung ausgewiesen.\n'
                               'Keine automatische Modellaktivierung oder Übernahme ungeprüfter Vorschläge.')
        self.layout_.addWidget(self.text,1)
        save=QPushButton('Bericht speichern …')
        save.clicked.connect(self.save_report)
        self.layout_.addWidget(save)

    def show_installed_training(self):
        from ..recognition.calibration_ranker import training_status
        self.show_report(training_status())

    def show_report(self,report):
        self.report=report
        self.text.setPlainText(json.dumps(report,indent=2,ensure_ascii=False))

    def import_provenance(self):
        path,_=QFileDialog.getOpenFileName(self,'Geprüfte Trainingsherkunft','','JSON (*.json)')
        if not path:
            return
        def process():
            from ..recognition.catalog import DefinitionCatalog
            db=DefinitionCatalog(self.window.recognition_db.path)
            records=json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(records,list) or not 1<=len(records)<=10000:
                raise ValueError('Liste mit 1–10.000 Herkunftsnachweisen erforderlich')
            # Validate the entire batch in a disposable copy before any live writes.
            import sqlite3,tempfile
            with tempfile.TemporaryDirectory() as directory:
                copy=Path(directory)/'review.sqlite3'
                with db.connect() as source,sqlite3.connect(copy) as target:
                    source.backup(target)
                preview=DefinitionCatalog(copy)
                for rec in records:
                    preview.review_training_provenance(rec)
            for rec in records:
                db.review_training_provenance(rec)
            return {'provenance_records_imported':len(records),'model_trained':False}
        self.run_task(process,self.show_report)

    def train_candidate(self):
        if not self.window.image:
            self.error('Zuerst Firmware öffnen')
            return
        from ..core.profiles import identify_profile
        family=identify_profile(self.window.image).family
        path=self.window.recognition_db.path
        def process():
            from ..recognition.catalog import DefinitionCatalog
            from ..recognition.safe_classifier import train_safe
            from ..recognition.ml import Model
            model=train_safe(DefinitionCatalog(path),family)
            destination=Path.home()/'.ecu_studio_ai'/'candidate-models'/f'{model.training_hash}.json'
            model.save(destination)
            Model.load(destination)
            return {'candidate_path':str(destination),'activated':False,'training_hash':model.training_hash,
                    'metrics':model.metrics,'pending':'Gepaarter Vergleich auf unabhängigen realen Firmwaredateien gegen bisheriges Modell'}
        self.run_task(process,self.show_report)

    def evaluate(self):
        path,_=QFileDialog.getOpenFileName(self,'Geprüftes Holdout-Manifest','','JSON (*.json)')
        if not path:
            return
        def process():
            from ..recognition.evaluation import evaluate
            from ..core.scoped_scan import scan_calibration_candidates
            return evaluate(path,{'current':scan_calibration_candidates})
        self.run_task(process,self.show_report)

    def save_report(self):
        if self.report is None:
            return
        p,_=QFileDialog.getSaveFileName(self,'KI-Bericht','model-evaluation.json','JSON (*.json)')
        if p:
            try:
                atomic_write(p,json.dumps(self.report,indent=2,ensure_ascii=False).encode('utf-8'),
                             protected=(self.window.image.path if self.window.image else None,))
            except Exception as exc:
                self.error(exc)
