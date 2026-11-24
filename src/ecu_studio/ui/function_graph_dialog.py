"""Dialog: map groups by consuming code routine and by shared axes; code relations and function groups."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QDialogButtonBox

MAX_ITEMS = 500


class FunctionGraphDialog(QDialog):
    def __init__(self, parent, maps, graph, on_select, code=None):
        """``code``: (uses, code relations) from core/tricore_flow, or None (no program code analysed)."""
        super().__init__(parent)
        self.setWindowTitle('Funktionsgraph – zusammengehörige Kennfelder')
        self.resize(820, 660)
        self.maps, self.on_select = maps, on_select
        layout = QVBoxLayout(self)
        info = QLabel(f"{graph['referenced']} Kennfelder werden im Programmcode referenziert. "
                      'Gruppen = von derselben Routine gelesen (Routinen-Grenzen aus Rücksprungbefehlen, '
                      'strukturelle Näherung) oder dieselbe gespeicherte Achse (gleiche Adresse). '
                      'Beziehungen aus dem Programmcode sind technische Belege, keine Funktionsnamen. '
                      'Doppelklick öffnet das Kennfeld.')
        info.setWordWrap(True)
        info.setObjectName('hint')
        layout.addWidget(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Gruppe / Kennfeld', 'Adresse', 'Größe'])
        self.tree.setColumnWidth(0, 520)
        layout.addWidget(self.tree, 1)
        routines = QTreeWidgetItem(self.tree, [f"Gleiche Routine ({len(graph['groups'])} Gruppen)"])
        for g in graph['groups']:
            node = QTreeWidgetItem(routines, [f'Routine 0x{g.routine_start:06X} · {g.size} Kennfelder', '', ''])
            self._add_members(node, g.members)
        axes = QTreeWidgetItem(self.tree, [f"Gemeinsame gespeicherte Achse ({len(graph['shared_axes'])} Gruppen)"])
        for g in graph['shared_axes']:
            status = ('unsicher' if g.uncertain else
                      'aus Definition' if g.evidence == 'definition' else 'strukturell, ungeprüft')
            name = f'{g.reference} · ' if g.reference else ''
            node = QTreeWidgetItem(axes, [f'{name}{g.points} Punkte · {len(g.indices)} Kennfelder · {status}',
                                          f'0x{g.axis_offset:08X}', ''])
            node.setToolTip(0, g.describe())
            self._add_members(node, g.indices)
        hints = QTreeWidgetItem(self.tree, [f"Gleiche Achswerte, andere Adresse – Hypothese ({len(graph['axis_hints'])})"])
        hints.setToolTip(0, 'Gleiche Stützstellenwerte belegen keine Zusammengehörigkeit; nur ein Hinweis zur Prüfung.')
        for members in graph['axis_hints']:
            self._add_members(QTreeWidgetItem(hints, [f'{len(members)} Kennfelder', '', '']), members)
        self._add_axis_references()
        self.relations = self._relations(graph, code)
        code_node = self._add_code(code) if code is not None else None
        self._add_groups()
        self._add_functions()
        routines.setExpanded(True)
        axes.setExpanded(not graph['groups'] and code_node is None)
        if code_node is not None:
            code_node.setExpanded(True)
        self.tree.itemDoubleClicked.connect(self._open)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_axis_references(self):
        """Axis references by status (stored / fixed / unresolved) and contradicted axis objects
        (core/axis_refs): shared only by storage address, never by equal values."""
        from ..core import axis_refs
        objs = axis_refs.objects(self.maps)
        n = axis_refs.summary(self.maps, objs)
        top = QTreeWidgetItem(self.tree, [f"Achsenreferenzen: {n[axis_refs.STORED]} gespeichert · "
                                          f"{n[axis_refs.FIXED]} fest · {n[axis_refs.OPEN]} ungeklärt", '', ''])
        top.setToolTip(0, 'Kennfeld → Achsenreferenz → gespeichertes Achsenobjekt. Gemeinsam heißt: gleiche '
                          'Speicheradresse. Ungeklärt: keine Quelle nennt die Speicheradresse; sie wird nicht aus '
                          'Werten geraten.')
        bad = [o for o in objs if o.contradictory]
        node = QTreeWidgetItem(top, [f'Widersprüchliche Achsenobjekte ({len(bad)})', '', ''])
        for o in bad[:MAX_ITEMS]:
            item = QTreeWidgetItem(node, [o.describe(), f'0x{o.offset:08X}', ''])
            item.setToolTip(0, o.describe())
            self._add_members(item, o.tables)
        open_refs = [r for r in axis_refs.references(self.maps) if r.status == axis_refs.OPEN]
        node = QTreeWidgetItem(top, [f'Achsenreferenz ungeklärt ({len(open_refs)})', '', ''])
        for r in open_refs[:MAX_ITEMS]:
            m = self.maps[r.table]
            item = QTreeWidgetItem(node, [f'{m.name}: {r.describe()}', f'0x{m.offset:08X}', ''])
            item.setData(0, Qt.ItemDataRole.UserRole, r.table)

    def _relations(self, graph, code):
        from ..core.function_id import code_links, relations
        rels = relations(self.maps, graph)
        if code is not None:
            rels += code_links(self.maps, code[1])
        return rels

    def _add_code(self, code):
        """Relations from the program code (core/code_flow), by kind, with evidence, method and open points."""
        from ..core.code_flow import summary
        from ..core.function_id import CODE_EVIDENCE, RELATION_LABELS, SHARED_INPUT
        uses, _ = code
        linked = [r for r in self.relations if r.evidence is not None]
        top = QTreeWidgetItem(self.tree, [f'Beziehungen aus dem Programmcode ({len(linked)})', '', ''])
        top.setToolTip(0, 'Begrenzte Datenflussanalyse um die Aufrufe der Interpolationsroutinen (TriCore, '
                          'experimentell). Ein Wert, der nicht sicher verfolgt werden kann, bleibt offen.')
        for kind in (*CODE_EVIDENCE, SHARED_INPUT):
            chosen = [r for r in linked if r.kind == kind]
            if not chosen:
                continue
            note = (' – kein Funktionsbeleg (gemeinsamer Betriebspunkt)' if kind == SHARED_INPUT else
                    ' – Programmcode-Beleg')
            node = QTreeWidgetItem(top, [f'{RELATION_LABELS[kind]}: {len(chosen)}{note}', '', ''])
            for r in chosen[:MAX_ITEMS]:
                a, b = self.maps[r.a], self.maps[r.b]
                item = QTreeWidgetItem(node, [f'{a.name} ↔ {b.name}', f'0x{a.offset:08X}', f'0x{b.offset:08X}'])
                e = r.evidence
                item.setToolTip(0, f'{e.evidence}\nBeleg bei 0x{e.source_address:X} → 0x{e.target_address:X}\n'
                                   f'Verfahren: {e.method}' + (f'\nOffen: {e.uncertainty}' if e.uncertainty else ''))
                item.setData(0, Qt.ItemDataRole.UserRole, r.a)
            if len(chosen) > MAX_ITEMS:
                QTreeWidgetItem(node, [f'… {len(chosen) - MAX_ITEMS} weitere', '', ''])
        counts = summary(uses)
        open_reasons = sorted(((k[6:], v) for k, v in counts.items() if k.startswith('open: ')), key=lambda x: -x[1])
        pending = QTreeWidgetItem(top, [f"Nicht eindeutig bestimmt: {counts.get('uses', 0)} Aufrufe, "
                                        f"{counts.get('with_result', 0)} mit gespeichertem Ergebnis", '', ''])
        for reason, n in open_reasons:
            QTreeWidgetItem(pending, [f'{reason}: {n}', '', ''])
        return top

    def _add_groups(self):
        """Tables linked by technical relations, numbered; never named after a function."""
        from ..core.function_id import RELATION_LABELS, function_groups
        groups = function_groups(self.maps, self.relations)
        top = QTreeWidgetItem(self.tree, [f'Funktionsgruppen ohne Namen ({len(groups)})', '', ''])
        top.setToolTip(0, 'Kennfelder, die über gemeinsame Achsen oder den Programmcode verbunden sind. Eine Gruppe '
                          'ist ein technischer Befund, keine Funktion: Kennfelder verschiedener Funktionen können '
                          'Achsen teilen. Bekannte Funktionen stammen nur aus Definitionen.')
        for g in groups[:MAX_ITEMS]:
            kinds = ', '.join(f'{RELATION_LABELS[k]} {n}' for k, n in sorted(g.kinds.items()))
            known = ('; widersprüchlich: ' + ', '.join(sorted(g.functions)) if g.contradictory else
                     f'; bekannte Funktion: {next(iter(g.functions))}' if g.functions else '')
            node = QTreeWidgetItem(top, [f'{g.label} · {len(g.members)} Kennfelder · '
                                         f'{"Programmcode" if g.code_backed else "nur Struktur"}{known}', '', ''])
            node.setToolTip(0, kinds)
            self._add_members(node, g.members, show_function=True)
        if len(groups) > MAX_ITEMS:
            QTreeWidgetItem(top, [f'… {len(groups) - MAX_ITEMS} weitere', '', ''])

    def _add_functions(self):
        """Function membership per table (core/function_id): only from definitions and relations to tables
        with a known function; a hypothesis never names a function nobody declared."""
        from ..core.function_id import CONFIRMED, STATUSES, counts, identify
        hyps = identify(self.maps, self.relations)
        n = counts(hyps)
        top = QTreeWidgetItem(self.tree, ['Funktionszuordnung (' + ' · '.join(f'{s} {n[s]}' for s in STATUSES) + ')'])
        top.setToolTip(0, 'Funktionen nur aus Definitionen (A2L FUNCTION) oder über Beziehungen zu Kennfeldern mit '
                          'bekannter Funktion (gemeinsame Achse, Programmcode, direkter Nachbar). Keine Namen aus Werten. '
                          'Reichen die Belege nicht, bleibt die Funktion unbekannt; die zurückgehaltene Funktion und '
                          'der Grund stehen im Tooltip.')
        sections = [(status, [h for h in hyps if h.status == status and h.function]) for status in STATUSES[:3]]
        sections.append(('widersprüchlich', [h for h in hyps if not h.function and h.contradictions]))
        sections.append(('zurückgehalten', [h for h in hyps if not h.function and not h.contradictions and h.candidates]))
        labels = {'widersprüchlich': 'Widersprüchlich (Funktion unbekannt)',
                  'zurückgehalten': 'Zurückgehalten (Funktion unbekannt, Belege reichen nicht)'}
        for status, chosen in sections:
            if not chosen:
                continue
            node = QTreeWidgetItem(top, [f'{labels.get(status, status)}: {len(chosen)} Kennfelder', '', ''])
            for h in chosen[:MAX_ITEMS]:
                m = self.maps[h.index]
                shown = (f'{m.name} → {h.function}' if h.status == CONFIRMED else
                         f'{m.name} → {h.function} ({h.status}, nicht bestätigt)' if h.function else
                         f'{m.name} → Funktion unbekannt')
                item = QTreeWidgetItem(node, [shown, f'0x{m.offset:08X}', f'{m.rows}×{m.cols} {m.dtype}'])
                item.setToolTip(0, h.describe())
                item.setData(0, Qt.ItemDataRole.UserRole, h.index)
            if len(chosen) > MAX_ITEMS:
                QTreeWidgetItem(node, [f'… {len(chosen) - MAX_ITEMS} weitere', '', ''])

    def _add_members(self, parent, members, show_function=False):
        for i in members:
            m = self.maps[i]
            label = f'{m.name} – Funktion: {m.function}' if show_function and m.function else m.name
            item = QTreeWidgetItem(parent, [label, f'0x{m.offset:08X}', f'{m.rows}×{m.cols} {m.dtype}'])
            item.setData(0, Qt.ItemDataRole.UserRole, i)

    def _open(self, item, _column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.on_select(self.maps[index])
