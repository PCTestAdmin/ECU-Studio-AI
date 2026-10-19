"""Offline HTML session report; escapes all names/notes and avoids embedded binary data."""
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from .analysis import analyze_map
from .model import BinaryImage, MapDefinition


def make_report_html(image: BinaryImage, maps: list[MapDefinition], notes: str) -> str:
    cards=[]
    for m in maps:
        try:
            details=analyze_map(image,m)
            label="Manuell bestätigt" if m.verified else "Nicht verifiziert"
            alerts="".join(f"<li>{escape(x)}</li>" for x in details['alerts'])
            cards.append(f"<tr><td>{escape(m.name)}</td><td>0x{m.offset:08X}</td>"
                         f"<td>{escape(m.kind)}</td><td>{m.rows}×{m.cols}</td>"
                         f"<td>{escape(label)} ({escape(m.source)})</td>"
                         f"<td>{details['min']:.4g} … {details['max']:.4g} {escape(m.unit)}</td>"
                         f"<td>{details['modified_bytes']}</td><td><ul>{alerts}</ul></td></tr>")
        except ValueError:
            continue
    changes="".join(f"<tr><td>0x{pos:08X}</td><td>{len(orig)}</td><td><code>{escape(orig[:24].hex(' '))}</code></td>"
                    f"<td><code>{escape(mod[:24].hex(' '))}</code></td></tr>"
                    for pos,orig,mod in image.changed_ranges()[:500])
    generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"/>
<title>ECU Studio AI – Analysebericht</title>
<style>body{{background:#101a27;color:#e2edf8;font:15px system-ui;margin:36px;line-height:1.5}}
section{{background:#17283b;padding:22px;border:1px solid #345368;border-radius:10px;margin:16px 0}}
h1,h2{{color:#52d7c6}}table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:10px;border-bottom:1px solid #3a5365;text-align:left;vertical-align:top}}
th{{color:#8beadd}}code,pre{{color:#c5dced;white-space:pre-wrap;overflow-wrap:anywhere}}
.warning{{color:#ffc383}}li{{margin:3px 0}}</style></head><body>
<h1>ECU Studio AI <small>· Analysebericht</small></h1><p>Erzeugt {escape(generated)}</p>
<section><h2>Datei-Identität</h2><p>Datei: {escape(Path(image.path).name if image.path else 'Unbenannt')}</p>
<p>Größe: {image.size:,} Bytes · SHA-256 Original: <code>{escape(image.digest)}</code></p>
<p>Geänderte Bytes: {image.dirty_bytes:,} · Definierte Kennfelder: {len(maps)}</p></section>
<section><h2>Kennfeld-Checkliste</h2><table><thead><tr><th>Name</th><th>Offset</th><th>Typ-Hypothese</th>
<th>Maße</th><th>Prüfstatus</th><th>Wertebereich</th><th>Änderungen</th><th>Strukturhinweise</th></tr></thead>
<tbody>{''.join(cards)}</tbody></table></section>
<section><h2>Änderungsaudit</h2><table><thead><tr><th>Offset</th><th>Bytes</th><th>Original</th><th>Bearbeitet</th></tr></thead>
<tbody>{changes}</tbody></table></section>
<section><h2>Arbeitsnotizen</h2><pre>{escape(notes)}</pre></section>
<p class="warning"><b>WICHTIG:</b> Nur Offline-Analyse; KI-/Heuristik-Typvorschläge sind keine verifizierte ECU-Funktionszuordnung.
Keine ECU-spezifische Checksummenprüfung, keine Flashbarkeits-, Abgas- oder Sicherheitsfreigabe.</p>
</body></html>'''


def report_html(image: BinaryImage, maps: list[MapDefinition], notes: str = "") -> str:
    """Compatibility façade for downloadable report and unit tests."""
    return make_report_html(image, maps, notes)


def export_html(path: str, image: BinaryImage, maps: list[MapDefinition], notes: str = "") -> None:
    """Write a self-contained offline HTML audit report."""
    Path(path).write_text(report_html(image, maps, notes), encoding="utf-8")
