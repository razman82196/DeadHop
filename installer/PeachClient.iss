; Inno Setup Script for PeachClient
; Requires Inno Setup 6 (iscc.exe)

#define MyAppName "PeachClient"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DeadHop"
#define MyAppURL "https://example.com"
#define MyAppExeName "PeachClient.exe"

[Setup]
AppId={{A7E7A6A4-6E1A-49C7-8E6B-9E2B1D2C4D8F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=no
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
OutputDir=dist\installer
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=app\resources\icons\custom\main app pixels.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Install the one-folder PyInstaller build
Source: "dist\PeachClient\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
