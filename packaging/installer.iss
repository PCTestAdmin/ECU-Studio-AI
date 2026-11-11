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
; Folders the updater creates next to the program folder. Program files themselves are removed by the
; uninstall log and by the inventory cleanup in [Code] below, never by a pattern rule such as {app}\_internal.
Type: filesandordirs; Name: "{app}.backup"
Type: filesandordirs; Name: "{app}.update-staging"

[Code]
// Program files by inventory (packaging/uninstall_cleanup.ps1, shipped in {app}\_internal):
// - before uninstalling: every file of {app}\RUNTIME_INVENTORY.json that is unchanged (SHA-256), also
//   files an in-app update added after the last installer run (finding A5 of 1.20.0);
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

procedure RunInventoryCleanup(Arguments: String);
var
  Script: String;
  ResultCode: Integer;
begin
  Script := ExpandConstant('{app}\') + CleanupScript;
  if not FileExists(Script) then
  begin
    Log('Inventarbereinigung übersprungen, Skript fehlt: ' + Script);
    Exit;
  end;
  ForceDirectories(ExtractFileDir(CleanupLogFile()));
  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
          '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Script + '" -InstallDir "' +
          ExpandConstant('{app}') + '" ' + Arguments + ' -LogFile "' + CleanupLogFile() + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Log('Inventarbereinigung beendet, Exit ' + IntToStr(ResultCode))
  else
    Log('Inventarbereinigung nicht gestartet: ' + SysErrorMessage(ResultCode));
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
begin
  if CurUninstallStep = usUninstall then
    RunInventoryCleanup('-Mode Uninstall');
end;
