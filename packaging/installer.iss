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
; cleanup keeps stays there.

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

function MoveAside(Folder: String): String;
// Renames Folder to a free name "<Folder>.erhalten[-N]" and returns it ('' if Folder does not exist). This moves it
// out of reach of the blanket rules of 1.20.0 and older that remain in the uninstall log (see [UninstallDelete]).
// Renaming changes no file. If it fails, the folder keeps its name and this is logged.
var
  Target: String;
  N: Integer;
begin
  Result := '';
  if not DirExists(Folder) then
    Exit;
  Target := Folder + '.erhalten';
  N := 2;
  while DirExists(Target) or FileExists(Target) do
  begin
    Target := Folder + '.erhalten-' + IntToStr(N);
    N := N + 1;
  end;
  if RenameFile(Folder, Target) then
  begin
    Log('Ordner umbenannt (Schutz vor alter Löschregel): ' + Folder + ' -> ' + Target);
    Result := Target;
  end
  else
  begin
    Log('WARNUNG: Ordner konnte nicht umbenannt werden, alte Löschregel kann ihn erfassen: ' + Folder);
    Result := Folder;
  end;
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
  Backup, Staging: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Backup and staging first: their copies are compared with {app}, which must still be complete.
    Backup := MoveAside(ExpandConstant('{app}') + '.backup');
    if Backup <> '' then
      RunLeftoverCleanup(Backup);
    Staging := MoveAside(ExpandConstant('{app}') + '.update-staging');
    if Staging <> '' then
    begin
      RunLeftoverCleanup(Staging + '\ECU-Studio-AI');
      RemoveDir(Staging);   // only removes an EMPTY folder
    end;
    RunInventoryCleanup('-Mode Uninstall');
  end;
end;
