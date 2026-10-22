# Eine neue Version veröffentlichen

Releases entstehen automatisch, sobald ein Versions-Tag gepusht wird (`.github/workflows/release.yml`).
Bestehende Nutzer bekommen die neue Version danach über die eingebaute Update-Prüfung angeboten.

## Ablauf

**Updater-Hinweis für 1.16.2:** Der Updater in 1.16.2 kann den Installationsordner beim Start aus der laufenden
Anwendung selbst als Arbeitsordner festhalten. Deshalb muss 1.16.3 einmal manuell per ZIP oder Installer installiert
werden. Der 1.16.3-Updater arbeitet außerhalb des Installationsordners; ab dann funktionieren automatische Updates.
Der Release-Workflow prüft den externen Arbeitsordner und meldet den nicht vollständig abdeckbaren alten Startweg
bei einem Update von 1.16.2 ausdrücklich als Warnung.

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
     **dessen** Updater aus einem externen Arbeitsordner auf die neue Version aktualisieren, Oberflächentest,
     Wiederherstellen der Vorversion und zurück, Installer installieren/selbsttesten/deinstallieren. Der direkte
     Workflow-Aufruf reproduziert den GUI-Übergang aus der bereits laufenden Vorversion nicht vollständig; bei
     1.16.2 wird diese Einschränkung als Warnung protokolliert.
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

## Signierte Updates einrichten (Ed25519, empfohlen)

Zusätzlich zu SHA-256 und Build-Herkunft kann jedes Update mit einem eigenen Schlüssel signiert werden. Danach
installieren ausgelieferte Apps **nur noch** Updates mit gültiger Signatur – auch eine gefälschte `.sha256`-Datei
reicht dann nicht mehr. Einmalig:

1. Schlüssel erzeugen (Pfad **außerhalb** des Repositorys):
   `python -m ecu_studio.tools.sign_release keygen --secret-out C:\Sicher\update_signing.key`
2. Inhalt der Datei als Repository-Secret hinterlegen: GitHub → Settings → Secrets and variables → Actions →
   *New repository secret* → Name `UPDATE_SIGNING_KEY`, Wert = Inhalt der Datei.
3. Die erzeugte Datei `src/ecu_studio/recognition/data/update_signing_key.pub` committen.

Ab dem nächsten Tag signiert der Workflow ZIP und Installer (`.sig`-Dateien im Release). Fehlt das Secret, obwohl
ein öffentlicher Schlüssel im Repository liegt, **bricht der Release ab** – sonst würden installierte Apps das
Update ablehnen. Den geheimen Schlüssel sicher aufbewahren: Ohne ihn lassen sich keine Updates mehr ausliefern,
die bestehende Installationen annehmen (dann nur Neuinstallation).

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
