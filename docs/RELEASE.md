# Eine neue Version veröffentlichen

Releases entstehen automatisch, sobald ein Versions-Tag gepusht wird (`.github/workflows/release.yml`).
Bestehende Nutzer bekommen die neue Version danach über die eingebaute Update-Prüfung angeboten.

## Ablauf

1. **Version erhöhen** in `src/ecu_studio/__init__.py`, z. B. `__version__ = "1.15.0"`.
2. **Änderungen eintragen:** in `CHANGELOG.md` einen Abschnitt `## 1.15.0 (Datum)` anlegen. Sein Inhalt erscheint
   als Release-Text und im Update-Fenster. Ohne diesen Abschnitt bricht der Release ab.
3. Committen und pushen, dann den Tag setzen:

   ```bash
   git tag v1.15.0
   git push origin v1.15.0
   ```

4. GitHub Actions („Release“) prüft, dass Tag und `__version__` übereinstimmen, führt alle Tests in einer frischen
   Python-3.13-Umgebung aus, baut das portable Paket, startet die EXE (Oberflächentest und `--self-check`), testet das
   entpackte ZIP ohne Python im PATH, baut den Installer und veröffentlicht:

   | Datei | Zweck |
   |---|---|
   | `ECU-Studio-AI-<version>-windows-x64.zip` | portables Paket; wird vom Updater verwendet |
   | `….zip.sha256` | Prüfsumme; der Updater bricht bei Abweichung ab |
   | `ECU-Studio-AI-<version>-setup.exe` (+ `.sha256`) | Installer (Startmenü, Deinstallation, ohne Adminrechte) |

   Zusätzlich wird eine Build-Herkunftsbestätigung (Attestation) erzeugt:
   `gh attestation verify <datei> --repo PCTestAdmin/ECU-Studio-AI`.

Nur **stabile** Versionen (`vX.Y.Z`, kein Entwurf, keine Vorabversion) werden Nutzern angeboten. Für Testversionen
den Release auf GitHub als „Pre-release“ markieren – die Update-Prüfung ignoriert ihn.

## Berechtigungen

Der Workflow nutzt nur das automatische `GITHUB_TOKEN` mit `contents: write` (Release anlegen), `id-token: write`
und `attestations: write` (Herkunftsbestätigung). Sollte die Organisation/das Repository Workflow-Schreibrechte
einschränken: Settings → Actions → General → „Workflow permissions“ → „Read and write permissions“ aktivieren.

## Code-Signatur (optional, empfohlen)

Die EXE ist bisher nicht signiert. Mit einem Code-Signing-Zertifikat (z. B. Azure Trusted Signing oder ein
OV/EV-Zertifikat) kann im Workflow vor „Build provenance“ ein Schritt `signtool sign` für `dist\ECU-Studio-AI\ECU-Studio-AI.exe`
und den Installer ergänzt werden. Der Updater prüft die Authenticode-Signatur bereits: ist sie vorhanden und ungültig,
bricht er ab; fehlt sie, gilt die SHA-256-Prüfung.

## Lokal testen

`build_exe_windows.bat` (bzw. `build_release.ps1`) führt dieselben Schritte lokal aus; der Installer entsteht nur,
wenn Inno Setup 6 installiert ist.
