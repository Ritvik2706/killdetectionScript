; Build with Inno Setup 6, after tools/build_desktop.py.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{971365F2-3484-48E3-BB50-25C46F9717BF}
AppName=Killcutter Studio
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\KillcutterStudio
DefaultGroupName=Killcutter Studio
PrivilegesRequired=lowest
OutputDir=..\dist\installers
OutputBaseFilename=KillcutterStudio-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\killcutter\gui\assets\killcutter.ico
UninstallDisplayIcon={app}\KillcutterStudio.exe
CloseApplications=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\KillcutterStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Killcutter Studio"; Filename: "{app}\KillcutterStudio.exe"
Name: "{autodesktop}\Killcutter Studio"; Filename: "{app}\KillcutterStudio.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\KillcutterStudio.exe"; Description: "Launch Killcutter Studio"; Flags: nowait postinstall skipifsilent unchecked
