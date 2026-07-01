; installer.iss — Inno Setup script para DJ Mix Player
; Requer Inno Setup: https://jrsoftware.org/isinfo.php

#define AppName      "DJ Mix Player"
#define AppVersion   "1.0.8"
#define AppPublisher "Rafael Lauriano"
#define AppURL       "https://github.com/rafalau/app-dj-mix"
#define AppExeName   "DJMixPlayer.exe"
#define BuildDir     "..\..\dist\DJMixPlayer"

[Setup]
AppId={{A3F2B1C4-7D8E-4F5A-9B2C-1E6D3A8F0C7B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\DJMixPlayer
DefaultGroupName={#AppName}
OutputDir=..\..\dist
OutputBaseFilename=DJMixPlayer_Setup_v{#AppVersion}
SetupIconFile=..\..\assets\icon_256.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
PrivilegesRequired=lowest

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";      Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar";     Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
