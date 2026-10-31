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

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Zusätzliche Verknüpfungen:"; Flags: unchecked

[Files]
Source: "..\dist\ECU-Studio-AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ECU Studio AI"; Filename: "{app}\ECU-Studio-AI.exe"; WorkingDir: "{app}"
Name: "{group}\ECU Studio AI deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ECU Studio AI"; Filename: "{app}\ECU-Studio-AI.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ECU-Studio-AI.exe"; Description: "ECU Studio AI starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Folders the updater creates next to the program folder.
Type: filesandordirs; Name: "{app}.backup"
Type: filesandordirs; Name: "{app}.update-staging"
