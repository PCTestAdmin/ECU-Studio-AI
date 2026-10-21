"""Modal tools: searchable A2L link preview, batch edits, and quick commands."""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,
    QLineEdit,QPushButton,QTableView,QComboBox,QDoubleSpinBox,
    QSpinBox,QMessageBox,QPlainTextEdit,QDialogButtonBox,QCheckBox,
    QListWidget,QListWidgetItem,QAbstractItemView,QHeaderView,QFileDialog)
from ..core.i18n import translated_roles
from ..core.definitions import parse_offset
from ..core.addressing import parse_segments
from ..core.workflows import plan_map_transform, apply_batch


class A2LMapPreviewModel(QAbstractTableModel):
    HEADERS = ('Import', 'Name', 'Kategorie', 'ECU-Adresse', 'BIN-Offset', 'Dimension', 'Skalierung', 'Achsen')

    def __init__(self):
        super().__init__()
        self.maps = []
        self.checked = []

    def set_maps(self, maps):
        self.beginResetModel()
        self.maps = list(maps)
        self.checked = [True] * len(self.maps)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.maps)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    @translated_roles
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return None
        if orientation == Qt.Orientation.Horizontal: return self.HEADERS[section]
        return str(section+1)

    @translated_roles
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        r,c=index.row(),index.column()
        m=self.maps[r]
        if c==0 and role==Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if self.checked[r] else Qt.CheckState.Unchecked
        if role==Qt.ItemDataRole.DisplayRole:
            return ('',m.name,m.kind,f'0x{m.ecu_address:X}' if m.ecu_address is not None else '',
                    f'0x{m.offset:X}',f'{m.rows}×{m.cols}',f'×{m.factor:g} {m.bias:+g} {m.unit}',
                    m.axes_info)[c]
        if role==Qt.ItemDataRole.ToolTipRole:
            return 'Ungeprüft: '+m.notes
        return None

    def flags(self,index):
        flags=super().flags(index)
        if index.isValid() and index.column()==0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        return flags

    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column()!=0 or role!=Qt.ItemDataRole.CheckStateRole:
            return False
        self.checked[index.row()]=(value==Qt.CheckState.Checked.value or value==Qt.CheckState.Checked)
        self.dataChanged.emit(index,index,[Qt.ItemDataRole.CheckStateRole])
        return True

    def selected_maps(self):
        return [m for m,keep in zip(self.maps,self.checked) if keep]

    def set_selected_indices(self,indices,checked):
        for index in indices:
            if 0<=index<len(self.checked): self.checked[index]=checked
        if self.maps:
            self.dataChanged.emit(self.index(0,0),self.index(len(self.maps)-1,0),[Qt.ItemDataRole.CheckStateRole])


class A2LLinkDialog(QDialog):
    def __init__(self, catalog, image, filename, parent=None, *, suggested_segments=None):
        super().__init__(parent)
        self.setWindowTitle('DAMOS / A2L → BIN koppeln · Suchbare Vorschau')
        self.resize(1120,740)
        self.catalog=catalog
        self.image=image
        self.result_data=None
        outer=QVBoxLayout(self)
        outer.addWidget(QLabel(
            f'Definitionsdatei: {Path(filename).name} · {len(catalog.characteristics):,} CHARACTERISTIC-Einträge\n'
            'Adresskopplung allein beweist keinen gleichen Softwarestand. Nur fachlich geprüfte Definitionen verwenden.'))
        form=QFormLayout()
        self.ecu=QLineEdit('0x0')
        self.offset=QLineEdit('0x0')
        form.addRow('ECU-Adresse des Ankers',self.ecu)
        form.addRow('BIN-Dateioffset des Ankers',self.offset)
        outer.addLayout(form)
        self.multi=QCheckBox('Erweiterte Adresskopplung: mehrere Speichersegmente')
        self.multi.toggled.connect(self.on_mode_changed)
        outer.addWidget(self.multi)
        self.segment_text=QPlainTextEdit()
        self.segment_text.setPlainText('# ECU_START ECU_ENDE BIN_START\n0x800000 0x801FFF 0x0')
        self.segment_text.setMaximumHeight(80)
        self.segment_text.setVisible(False)
        outer.addWidget(self.segment_text)
        row=QHBoxLayout()
        auto=QPushButton('Basis aus der Firmware bestimmen')
        auto.setToolTip('Sucht die ECU-Adresse, an der die gespeicherten Achsen der A2L-Datensätze aufsteigen. '
                        'Findet sich keine, beschreibt die A2L diese Datei nicht.')
        auto.clicked.connect(self.auto_anchor)
        calc=QPushButton('Adresskopplung prüfen / Vorschau aktualisieren')
        calc.clicked.connect(self.preview)
        row.addWidget(auto);row.addWidget(calc)
        outer.addLayout(row)
        self.summary=QLabel('Bitte Vorschau berechnen.')
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        bar=QHBoxLayout()
        self.search=QLineEdit()
        self.search.setPlaceholderText('Kennfelder nach Symbol, Typ, Adresse oder Achsen suchen …')
        bar.addWidget(self.search)
        self.all_visible=QPushButton('Sichtbare markieren')
        self.none_visible=QPushButton('Sichtbare abwählen')
        bar.addWidget(self.all_visible)
        bar.addWidget(self.none_visible)
        outer.addLayout(bar)
        self.model=A2LMapPreviewModel()
        self.proxy=QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setDynamicSortFilter(True)
        self.table=QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        outer.addWidget(self.table,1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.all_visible.clicked.connect(lambda:self.mark_visible(True))
        self.none_visible.clicked.connect(lambda:self.mark_visible(False))
        self.diagnostics=QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(105)
        outer.addWidget(self.diagnostics)
        foot=QHBoxLayout()
        export=QPushButton('Diagnose speichern …')
        export.clicked.connect(self.export_diagnostics)
        foot.addWidget(export)
        foot.addStretch()
        btns=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.accept_button=btns.button(QDialogButtonBox.StandardButton.Ok)
        self.accept_button.setText('Markierte Kennfelder importieren')
        self.accept_button.setEnabled(False)
        btns.accepted.connect(self.finish)
        btns.rejected.connect(self.reject)
        foot.addWidget(btns)
        outer.addLayout(foot)
        if suggested_segments:
            lines=['# Aus konvertierter BIN mit SHA-256-Abgleich übernommen; ECU-Softwarestand separat prüfen']
            lines += [f'0x{s.ecu_start:X} 0x{s.ecu_end:X} 0x{s.file_start:X}' for s in suggested_segments]
            self.segment_text.setPlainText('\n'.join(lines))
            self.multi.setChecked(True)
        self.preview()

    def auto_anchor(self):
        from ..core.a2l import suggest_anchor
        found=suggest_anchor(self.catalog,self.image.original)
        if found is None:
            self.summary.setText('Keine Basis gefunden, an der die Achsen aufsteigen: Die A2L passt '
                                 'vermutlich nicht zu dieser Datei (anderer Softwarestand).')
            return
        self.multi.setChecked(False)
        self.ecu.setText(f'0x{found["anchor"]:X}');self.offset.setText('0x0')
        self.preview()

    def on_mode_changed(self,active):
        self.ecu.setEnabled(not active)
        self.offset.setEnabled(not active)
        self.segment_text.setVisible(active)
        self.result_data=None
        self.accept_button.setEnabled(False)

    def preview(self):
        self.result_data=None
        self.accept_button.setEnabled(False)
        try:
            if self.multi.isChecked():
                segments=parse_segments(self.segment_text.toPlainText(),self.image.size)
                result=self.catalog.link(file_size=self.image.size,segments=segments,data=self.image.original)
                ident=self.catalog.identity(self.image.original,segments=segments)
            else:
                ecu,off=parse_offset(self.ecu.text()),parse_offset(self.offset.text())
                # Original bytes: record counts and axes come from the file itself.
                result=self.catalog.link(file_size=self.image.size,ecu_anchor=ecu,file_anchor=off,
                                         data=self.image.original)
                ident=self.catalog.identity(self.image.original,ecu,off)
        except Exception as exc:
            self.summary.setText('Fehler: '+str(exc))
            self.model.set_maps([])
            return
        self.result_data=result
        self.model.set_maps(result.maps)
        epk={'match':'EPK stimmt mit der Datei überein','mismatch':'EPK PASST NICHT – andere Software',
             'not-declared':'A2L deklariert keine EPK – Softwarestand nicht belegt',
             'outside':'EPK-Adresse liegt nicht in Datei/Segmenttabelle – Softwarestand nicht geprüft'}[ident['status']]
        self.summary.setText(f'{len(result.maps):,} verknüpfbar · {len(result.unsupported):,} Layout/Umrechnung offen · '
            f'{len(result.out_of_range):,} außerhalb BIN · {len(result.unlinked):,} nicht verknüpft · {epk}. '
            'Alle Treffer sind UNBESTÄTIGT. Filter anwenden und gewünschte Kennfelder markieren.')
        details=[*self.catalog.warnings,*result.warnings,*result.unsupported,*result.unlinked,*result.out_of_range]
        self.diagnostics.setPlainText('\n'.join(details[:250]) or 'Keine Parserwarnungen')
        if len(details)>250:self.diagnostics.appendPlainText(f'… weitere {len(details)-250} Hinweise (alle per Export)')
        self.accept_button.setEnabled(bool(result.maps))

    def mark_visible(self,checked):
        indices=[self.proxy.mapToSource(self.proxy.index(i,0)).row() for i in range(self.proxy.rowCount())]
        self.model.set_selected_indices(indices,checked)

    def export_diagnostics(self):
        if not self.result_data:return
        path,_=QFileDialog.getSaveFileName(self,'Import-Diagnose speichern','a2l_import_diagnose.txt','Text (*.txt)')
        if path:
            r=self.result_data
            lines=[f'Erkannt {r.total} / verknüpfbar {len(r.maps)}',
                   'WARNUNGEN:',*self.catalog.warnings,*r.warnings,
                   'NICHT UNTERSTÜTZT:',*r.unsupported,
                   'OHNE SEGMENT:',*r.unlinked,'AUSSERHALB BIN:',*r.out_of_range]
            Path(path).write_text('\n'.join(lines),encoding='utf-8')

    def finish(self):
        selected=self.model.selected_maps()
        if not selected:
            QMessageBox.information(self,'Keine Auswahl','Mindestens ein Kennfeld auswählen.')
            return
        self.selected_maps=selected
        self.accept()


class CommandPalette(QDialog):
    """Fast keyboard/filter command launcher; actions stay owned by main GUI."""
    def __init__(self, commands: list[tuple[str, object]], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Schnellbefehle · Suche')
        self.resize(620,440)
        self.commands=commands
        self.choice=None
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel('Befehl eintippen und Enter drücken – oder doppelklicken.'))
        self.query=QLineEdit()
        self.query.setPlaceholderText('Suchen: Kennfeld, Versionsstand, A2L, Vergleich …')
        lay.addWidget(self.query)
        self.items=QListWidget()
        lay.addWidget(self.items,1)
        self.query.textChanged.connect(self.refresh)
        self.query.returnPressed.connect(self.choose)
        self.items.itemActivated.connect(lambda _:self.choose())
        self.refresh()
        self.query.setFocus()

    def refresh(self,*_):
        self.items.clear()
        query=self.query.text().casefold().strip()
        for idx,(title,_) in enumerate(self.commands):
            if query and not all(fragment in title.casefold() for fragment in query.split()):continue
            item=QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole,idx)
            self.items.addItem(item)
        if self.items.count():self.items.setCurrentRow(0)

    def choose(self):
        item=self.items.currentItem()
        if item is None:return
        self.choice=self.commands[item.data(Qt.ItemDataRole.UserRole)][1]
        self.accept()


class BatchEditDialog(QDialog):
    def __init__(self, image, definition, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Kennfeld-Batchbearbeitung · Vorschau + ein Undo')
        self.setMinimumWidth(490)
        self.image=image;self.map=definition
        self.plan=None
        outer=QVBoxLayout(self)
        outer.addWidget(QLabel(f'{definition.name} · {definition.rows}×{definition.cols} · {definition.unit}\n'
                               'Alle gewählten Zellen vor dem Schreiben auf gültige Rohwerte prüfen.'))
        form=QFormLayout()
        self.mode=QComboBox();self.mode.addItems(['Addieren (phys. Einheit)','Prozentual ändern','Konstanten Wert setzen'])
        form.addRow('Methode',self.mode)
        self.amount=QDoubleSpinBox();self.amount.setRange(-1e9,1e9);self.amount.setDecimals(4)
        form.addRow('Wert / Prozent',self.amount)
        self.r0=QSpinBox();self.r0.setRange(0,definition.rows-1)
        self.r1=QSpinBox();self.r1.setRange(1,definition.rows);self.r1.setValue(definition.rows)
        self.c0=QSpinBox();self.c0.setRange(0,definition.cols-1)
        self.c1=QSpinBox();self.c1.setRange(1,definition.cols);self.c1.setValue(definition.cols)
        for title,widget in [('Zeile von (0-basiert)',self.r0),('Zeile bis (exklusiv)',self.r1),
                             ('Spalte von (0-basiert)',self.c0),('Spalte bis (exklusiv)',self.c1)]:
            form.addRow(title,widget)
        outer.addLayout(form)
        self.summary=QLabel('Vor der Bearbeitung Vorschau berechnen.')
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        actions=QHBoxLayout()
        preview=QPushButton('Vorschau berechnen')
        preview.clicked.connect(self.preview)
        actions.addWidget(preview)
        self.commit=QPushButton('Jetzt ändern (1 Undo-Schritt)')
        self.commit.setEnabled(False)
        self.commit.clicked.connect(self.do_apply)
        actions.addWidget(self.commit)
        outer.addLayout(actions)
        for ctl in (self.mode,self.amount,self.r0,self.r1,self.c0,self.c1):
            (ctl.currentIndexChanged if isinstance(ctl,QComboBox) else ctl.valueChanged).connect(self.invalidate)

    def invalidate(self,*_):
        self.plan=None
        self.commit.setEnabled(False)
        self.summary.setText('Einstellungen geändert. Erneut Vorschau berechnen.')

    def preview(self):
        try:
            mode=('add','percent','set')[self.mode.currentIndex()]
            self.plan=plan_map_transform(self.image,self.map,mode=mode,amount=self.amount.value(),
                row_range=(self.r0.value(),self.r1.value()),col_range=(self.c0.value(),self.c1.value()))
            p=self.plan
            self.summary.setText(f'Vorher: {p.before_min:g} … {p.before_max:g}\n'
                f'Nachher: {p.after_min:g} … {p.after_max:g}\n'
                f'{p.changed_cells} betroffene Zellen · {p.changed_bytes} unterschiedliche Bytes. '
                'Keine ECU-Checksummen-/Sicherheitsprüfung.')
            self.commit.setEnabled(bool(p.changed_cells))
        except Exception as exc:
            self.plan=None;self.commit.setEnabled(False)
            self.summary.setText('Ungültige Änderung: '+str(exc))

    def do_apply(self):
        if self.plan is None:return
        try:apply_batch(self.image,self.plan)
        except Exception as exc:
            QMessageBox.warning(self,'Bearbeitung abgebrochen',str(exc));return
        self.accept()
