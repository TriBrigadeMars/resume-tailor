; Inno Setup script for ResumeTailor Desktop (Windows).
;
; Built by .github/workflows/build.yml on a windows-latest runner using
; the Minionguyjpro/Inno-Setup-Action@1.2.7 action, which expects the
; .iss to live at the repo root.

#define MyAppName "ResumeTailor"
#define MyAppPublisher "TriBrigadeMars"
#define MyAppURL "https://github.com/TriBrigadeMars/resume-tailor"
#define MyAppExeName "ResumeTailor-Desktop.exe"

[Setup]
AppId={{B8B7C5E1-2A4F-4F4E-8E6D-1A2B3C4D5E6F}
AppName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=output
OutputBaseName=ResumeTailor-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The build.yml "installer" job downloads the PyInstaller output into
; dist-desktop/ at the repo root, so we package everything from there.
Source: "dist-desktop\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; NOTE: any extra runtime files (LICENSE, README, etc.) should be added
; here once the PyInstaller build produces them.

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
