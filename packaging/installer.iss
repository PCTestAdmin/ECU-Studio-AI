; ECU Studio AI – optional Windows installer (Inno Setup 6).
; Installs per user (no administrator rights), so the built-in updater can replace
; the program folder later. Projects and settings live outside the program folder
; (%USERPROFILE%\.ecu_studio_ai, registry) and survive updates and uninstallation.
; Build: ISCC.exe /DAppVersion=1.15.0 packaging\installer.iss   (after build_release.ps1)

#ifndef AppVersion
  #error AppVersion fehlt: ISCC /DAppVersion=x.y.z
#endif

[Setup]
AppId={{F8CD5330-FC90-4891-BFDA-58E6668C93A5}
AppName=ECU Studio AI
AppVersion={#AppVersion}
AppVerName=ECU Studio AI {#AppVersion}
; Windows file version of setup.exe (Properties > Details) instead of 0.0.0.0.
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
AppPublisher=PCTestAdmin
AppPublisherURL=https://github.com/PCTestAdmin/ECU-Studio-AI
AppUpdatesURL=https://github.com/PCTestAdmin/ECU-Studio-AI/releases
DefaultDirName={localappdata}\Programs\ECU-Studio-AI
DefaultGroupName=ECU Studio AI
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=ECU-Studio-AI-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ECU-Studio-AI.exe
SetupIconFile=..\src\ecu_studio\ui\assets\app.ico
WizardStyle=modern
; List of every file compressed into the installer with its SHA-256 (release check, tools/withdrawn.py).
OutputManifestFile=ECU-Studio-AI-{#AppVersion}-setup-manifest.txt

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Zusätzliche Verknüpfungen:"; Flags: unchecked

[Files]
Source: "..\dist\ECU-Studio-AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID = APP_USER_MODEL_ID in src/ecu_studio/main.py: links the running window (pythonw.exe) to these
; shortcuts, so taskbar and Start menu show the program icon and a pin starts ECU-Studio-AI.exe.
Name: "{group}\ECU Studio AI"; Filename: "{app}\ECU-Studio-AI.exe"; WorkingDir: "{app}"; AppUserModelID: "PCTestAdmin.ECUStudioAI"
Name: "{group}\ECU Studio AI deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ECU Studio AI"; Filename: "{app}\ECU-Studio-AI.exe"; WorkingDir: "{app}"; AppUserModelID: "PCTestAdmin.ECUStudioAI"; Tasks: desktopicon

[Run]
Filename: "{app}\ECU-Studio-AI.exe"; Description: "ECU Studio AI starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately empty: no blanket or pattern rule (from 1.20.1). Up to 1.20.0 the folders the updater creates
; next to the program folder, {app}.backup and {app}.update-staging, were deleted here as a whole
; ("filesandordirs"). A backup can hold the only copy of a program file the user changed, or of an own file
; whose name a new version took. They are now cleaned file by file in [Code] below (-Mode Leftover).
; Inno Setup keeps the entries of earlier installer runs in unins000.dat: an installation that was ever set up with
; 1.20.0 or older still carries those two blanket rules, and the uninstaller would run them AFTER [Code]. So both
; folders are first renamed to "<folder>.erhalten" (MoveAside): the old rules then find nothing, and whatever the
; cleanup keeps stays there. If a folder cannot be renamed, the uninstallation stops before anything is removed
; (StopUninstall); it never continues with such a folder under its old name.

[Code]
// Program files by inventory (packaging/uninstall_cleanup.ps1, shipped in {app}\_internal):
// - before uninstalling: first {app}.backup and {app}.update-staging\ECU-Studio-AI (-Mode Leftover, compared
//   with the still complete {app}): only unchanged inventory files, byte-identical copies of files in {app}
//   and this application's own uninstaller files; the folders go only when empty. Then every file of
//   {app}\RUNTIME_INVENTORY.json that is unchanged (SHA-256), also files an in-app update added after the
//   last installer run (finding A5 of 1.20.0);
// - after installing over an existing version: unchanged files of the previous version that the new
//   version no longer ships.
// User files, changed files and anything outside the program folder or behind a junction/link stay.
// A failing cleanup never fails the setup or uninstall: the files then simply remain.
const
  CleanupScript = '_internal\uninstall_cleanup.ps1';
  InventoryFile = 'RUNTIME_INVENTORY.json';

var
  PreviousInventory: String;

function CleanupLogFile(): String;
begin
  Result := ExpandConstant('{localappdata}\ECUStudioAI\install-cleanup.log');
end;

procedure RunCleanup(Folder, Arguments: String);
var
  Shipped, Script: String;
  ResultCode: Integer;
begin
  Shipped := ExpandConstant('{app}\') + CleanupScript;
  if not FileExists(Shipped) then
  begin
    Log('Inventarbereinigung übersprungen, Skript fehlt: ' + Shipped);
    Exit;
  end;
  // The script is itself listed in the inventory and removes its own file: run a temporary copy.
  Script := ExpandConstant('{tmp}\uninstall_cleanup.ps1');
  if not FileCopy(Shipped, Script, False) then
  begin
    Log('Inventarbereinigung übersprungen, Skript nicht kopierbar: ' + Shipped);
    Exit;
  end;
  ForceDirectories(ExtractFileDir(CleanupLogFile()));
  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
          '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Script + '" -InstallDir "' +
          Folder + '" ' + Arguments + ' -LogFile "' + CleanupLogFile() + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Log('Inventarbereinigung beendet (' + Folder + '), Exit ' + IntToStr(ResultCode))
  else
    Log('Inventarbereinigung nicht gestartet: ' + SysErrorMessage(ResultCode));
end;

procedure RunInventoryCleanup(Arguments: String);
begin
  RunCleanup(ExpandConstant('{app}'), Arguments);
end;

procedure RunLeftoverCleanup(Folder: String);
begin
  // The updater's backup or staging copy: nothing of it is deleted as a whole (see [UninstallDelete]).
  if DirExists(Folder) then
    RunCleanup(Folder, '-Mode Leftover -Reference "' + ExpandConstant('{app}') + '"');
end;

function MoveAside(Folder: String; var Target: String): Boolean;
// Moves Folder out of reach of the blanket rules of 1.20.0 and older that remain in the uninstall log (see
// [UninstallDelete]) by renaming it to a free name "<Folder>.erhalten[-N]" (Target; '' if nothing was renamed).
// Renaming changes no file. Returns True only if NOTHING exists under the name Folder any more (it never existed or
// was renamed); False if it is still there (rename failed: a file in it is open, no permission, ...).
var
  N: Integer;
begin
  Target := '';
  if DirExists(Folder) or FileExists(Folder) then
  begin
    Target := Folder + '.erhalten';
    N := 2;
    while DirExists(Target) or FileExists(Target) do
    begin
      Target := Folder + '.erhalten-' + IntToStr(N);
      N := N + 1;
    end;
    if RenameFile(Folder, Target) then
      Log('Ordner umbenannt (Schutz vor alter Löschregel): ' + Folder + ' -> ' + Target)
    else
    begin
      Log('Ordner konnte nicht umbenannt werden: ' + Folder);
      Target := '';
    end;
  end;
  Result := not (DirExists(Folder) or FileExists(Folder));
end;

procedure PutBack(Target, Folder: String);
// Undoes a rename of MoveAside when the uninstallation is stopped: the program stays installed and its rollback
// keeps finding the backup. If that fails, the folder stays under Target (out of reach of the old rules).
begin
  if Target = '' then
    Exit;
  if RenameFile(Target, Folder) then
    Log('Umbenennung zurückgenommen: ' + Target + ' -> ' + Folder)
  else
    Log('Umbenennung nicht zurückgenommen, der Ordner bleibt unverändert unter ' + Target);
end;

procedure StopUninstall(Folder: String);
// Called before anything was removed. Abort in CurUninstallStepChanged(usUninstall) ends the uninstaller before it
// processes its log: neither the program files nor Folder are touched, and the old blanket rules never run.
begin
  Log('DEINSTALLATION ABGEBROCHEN, nichts entfernt: ' + Folder + ' konnte nicht umbenannt werden. Eine Löschregel ' +
      'älterer Versionen im Deinstallationsprotokoll würde diesen Ordner sonst vollständig löschen.');
  SuppressibleMsgBox('Die Deinstallation wurde abgebrochen. Es wurde nichts entfernt.' + #13#10#13#10 +
    'Der Ordner' + #13#10 + Folder + #13#10 + 'konnte nicht umbenannt werden, vermutlich ist eine Datei darin ' +
    'geöffnet. Ohne Umbenennung würde eine Löschregel älterer Versionen ihn vollständig löschen, auch eigene oder ' +
    'veränderte Dateien darin.' + #13#10#13#10 +
    'Bitte schließe alle Programme, die Dateien aus diesem Ordner verwenden, und starte die Deinstallation erneut.',
    mbCriticalError, MB_OK, IDOK);
  Abort;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    PreviousInventory := '';
    if FileExists(ExpandConstant('{app}\') + InventoryFile) then
    begin
      PreviousInventory := ExpandConstant('{tmp}\previous-inventory.json');
      if not FileCopy(ExpandConstant('{app}\') + InventoryFile, PreviousInventory, False) then
        PreviousInventory := '';
    end;
  end
  else if (CurStep = ssPostInstall) and (PreviousInventory <> '') then
    RunInventoryCleanup('-Mode Obsolete -Inventory "' + PreviousInventory + '" -Keep "' +
                        ExpandConstant('{app}\') + InventoryFile + '"');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  BackupFolder, StagingFolder, Backup, Staging: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 1. Both folders out of reach of the old blanket rules BEFORE anything is removed. If one of them cannot be
    //    renamed, the uninstallation stops here (StopUninstall): nothing has been removed yet.
    BackupFolder := ExpandConstant('{app}') + '.backup';
    StagingFolder := ExpandConstant('{app}') + '.update-staging';
    if not MoveAside(BackupFolder, Backup) then
      StopUninstall(BackupFolder);
    if not MoveAside(StagingFolder, Staging) then
    begin
      PutBack(Backup, BackupFolder);
      StopUninstall(StagingFolder);
    end;
    // 2. Backup and staging file by file: their copies are compared with {app}, which must still be complete.
    if Backup <> '' then
      RunLeftoverCleanup(Backup);
    if Staging <> '' then
    begin
      RunLeftoverCleanup(Staging + '\ECU-Studio-AI');
      RemoveDir(Staging);   // only removes an EMPTY folder
    end;
    RunInventoryCleanup('-Mode Uninstall');
  end;
end;
