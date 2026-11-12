"""Drives the REAL running old version through Windows UI Automation, like a user with the mouse.

Only for the isolated installer test (installer_test.ps1 -Mode InApp); runs with the runner's own Python
(pywinauto, Pillow), not inside the application. Steps: menu "Einstellungen" -> "Jetzt nach Updates suchen",
update dialog shown (version texts read from the screen), "Jetzt aktualisieren", download with SHA-256 check by the
application, "Update bereit" -> Yes, application closes itself.

  python inapp_ui.py <pid> <out dir> <old version> <new version>
"""
import json
import sys
import time
import traceback
from pathlib import Path

from PIL import ImageGrab
from pywinauto import Desktop
from pywinauto.application import Application

PID, OUT, OLD, NEW = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
OUT.mkdir(parents=True, exist_ok=True)
RESULT = {'checks': [], 'steps': []}
# The program follows the Windows display language: German texts and their English translations (en.json of the
# old version). Each entry lists the accepted variants.
T = {
    'settings': ('Einstellungen', 'Settings'),
    'check': ('Jetzt nach Updates suchen', 'Check for updates now'),
    'dialog': ('Update verfügbar', 'update available'),
    'available': (f'Version {NEW} ist verfügbar', f'version {NEW} is available'),
    'installed': (f'Installiert: {OLD}', f'Installed: {OLD}'),
    'new': (f'Neu: {NEW}', f'New: {NEW}'),
    'now': ('Jetzt aktualisieren', 'Update now'),
    'ready': ('Update bereit', 'Update ready'),
    'not_installed': ('Update nicht installiert', 'Update not installed'),
    'verified': (f'{NEW} ist geprüft (SHA-256', f'{NEW} has been verified (SHA-256'),
    'yes': ('Ja', 'Yes'),
}


def has(text, key):
    return any(v in text for v in T[key])


def check(name, condition, detail=''):
    RESULT['checks'].append({'name': name, 'ok': bool(condition), 'detail': str(detail)[:400]})
    if not condition:
        raise AssertionError(f'{name}: {detail}')


def shot(name):
    try:
        ImageGrab.grab(all_screens=True).save(OUT / f'{name}.png')
    except Exception as exc:          # screenshots are evidence, not a test condition
        RESULT['steps'].append(f'screenshot {name} failed: {exc}')


def windows():
    """Top-level windows of the process and the dialogs UIA lists as their children (Qt dialogs with a parent)."""
    found = []
    for top in Desktop(backend='uia').windows(process=PID):
        found.append(top)
        try:
            found += top.descendants(control_type='Window')
        except Exception:
            pass
    return found


def find_window(key, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in windows():
            try:
                if has(w.window_text(), key):
                    return w
            except Exception:
                pass
        time.sleep(0.5)
    return None


def texts(w):
    out = []
    for c in w.descendants():
        try:
            t = c.window_text()
        except Exception:
            continue
        if t:
            out.append(t)
    return out


def click_menu_item(key, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in windows():
            for item in w.descendants(control_type='MenuItem'):
                try:
                    if item.window_text().replace('&', '') in T[key]:
                        item.click_input()
                        return True
                except Exception:
                    pass
        time.sleep(0.3)
    return False


def run():
    app = Application(backend='uia').connect(process=PID, timeout=30)
    main = app.top_window()
    main.set_focus()
    title = main.window_text()
    check('alte Version läuft (Fenstertitel)', f'v{OLD}' in title, title)
    shot('inapp-1-alte-version')

    menus = [i.window_text() for w in windows() for i in w.descendants(control_type='MenuItem')]
    RESULT['menu_items'] = menus
    check('Menü „Einstellungen“ geöffnet', click_menu_item('settings'), menus)
    time.sleep(0.5)
    shot('inapp-2-menue')
    check('„Jetzt nach Updates suchen“ angeklickt', click_menu_item('check'))

    dialog = find_window('dialog', 90)
    check('Update-Dialog erscheint', dialog is not None, [w.window_text() for w in windows()])
    shown = texts(dialog)
    RESULT['dialog_texts'] = shown
    shot('inapp-3-update-dialog')
    check('Dialog zeigt die neue Version', any(has(t, 'available') for t in shown), shown[:4])
    check('Dialog zeigt installierte und neue Version', any(has(t, 'installed') and has(t, 'new') for t in shown))
    buttons = {b.window_text().replace('&', ''): b for b in dialog.descendants(control_type='Button')}
    now = next((buttons[t] for t in T['now'] if t in buttons), None)
    check('Schaltfläche „Jetzt aktualisieren“', now is not None, list(buttons))
    now.click_input()
    RESULT['steps'].append('Jetzt aktualisieren geklickt')

    ready = None
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline and ready is None:
        for w in windows():
            text = w.window_text()
            if text in T['ready'] + T['not_installed']:
                ready = w
        if ready is None:
            for w in windows():
                if w.window_text() == 'Update':
                    RESULT['progress_seen'] = True
            time.sleep(0.5)
    check('Download beendet (Meldung erscheint)', ready is not None, [w.window_text() for w in windows()])
    shown = texts(ready)
    RESULT['ready_texts'] = shown
    shot('inapp-4-update-bereit')
    check('Download und SHA-256-Prüfung erfolgreich', ready.window_text() in T['ready']
          and any(has(t, 'verified') for t in shown), shown)
    yes = [b for b in ready.descendants(control_type='Button') if b.window_text().replace('&', '') in T['yes']]
    check('Schaltfläche „Ja“', yes, [b.window_text() for b in ready.descendants(control_type='Button')])
    yes[0].click_input()
    RESULT['steps'].append('Update bestätigt')

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and app.is_process_running():
        extra = [w.window_text() for w in windows() if w.window_text() not in ('', title)]
        if extra:
            RESULT.setdefault('while_closing', extra)
        time.sleep(0.5)
    check('alte Version schließt sich für das Update', not app.is_process_running(), RESULT.get('while_closing'))


if __name__ == '__main__':
    try:
        run()
        RESULT['passed'] = True
    except Exception:
        RESULT['passed'] = False
        RESULT['error'] = traceback.format_exc()
        shot('inapp-fehler')
    (OUT / 'inapp-ui.json').write_text(json.dumps(RESULT, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps({k: RESULT.get(k) for k in ('passed', 'error')}, ensure_ascii=False))
    sys.exit(0 if RESULT['passed'] else 1)
