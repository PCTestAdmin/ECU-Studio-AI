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

4. GitHub Actions („Release“) läuft in drei Stufen:
   - **build:** Tag gegen `__version__` und CHANGELOG prüfen, alle Tests in frischer Python-3.13-Umgebung, portables Paket,
     EXE-Tests (Oberflächentest, `--self-check`, entpacktes ZIP ohne Python im PATH), Installer.
   - **update-test** auf Windows Server 2022 **und** 2025: das zuletzt veröffentlichte Release installieren und mit
     **dessen** Updater auf die neue Version aktualisieren (wie bei Anwendern), Oberflächentest, Wiederherstellen der
     Vorversion und zurück, Installer installieren/selbsttesten/deinstallieren.
   - **publish:** nur wenn beide Update-Tests bestanden haben – Herkunftsbestätigung und Veröffentlichung:

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
wenn Inno Setup 6 installiert ist (`winget install JRSoftware.InnoSetup`). Ist der Windows-Defender-Schutz
„Überwachter Ordnerzugriff“ aktiv, darf Inno Setup nicht in den Dokumente-Ordner schreiben – das Skript baut den
Installer deshalb in einem temporären Ordner und kopiert ihn anschließend nach `dist`.

## Erstes Release (1.15.0, 21.10.2026)

Workflow vollständig durchgelaufen (Tests, Paket, EXE-Tests ohne Python, Installer, Attestation, Veröffentlichung).
Geprüft: echtes Update einer 1.14.0-Installation über die GitHub-API auf 1.15.0 (Download, SHA-256 gegen `.sha256`
und GitHub-Digest, Updater, Selbsttest, Sicherung); Installer aus dem Release: Installation, Selbsttest,
Deinstallation.
