; ============================================================
; Sortly Windows Installer Script
; Compiled with Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;
; Usage:
;   ISCC.exe /DMyAppVersion=1.2.3 installer\sortly.iss
; ============================================================

; Allow version to be passed on the command line: /DMyAppVersion=x.y.z
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName        "Sortly"
#define MyAppPublisher   "Arsh Sisodiya"
#define MyAppURL         "https://github.com/sortly/sortly"
#define MyAppExeName     "sortly-gui.exe"
; Stable GUID — NEVER change this once published, or upgrades will break
#define MyAppId          "{B8F2A14D-3E6C-4F01-9A7B-2D5C8E0F1A3B}"

; ============================================================
[Setup]
; AppId identifies this product for upgrades. Double-brace escapes one brace.
AppId={{B8F2A14D-3E6C-4F01-9A7B-2D5C8E0F1A3B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install into Program Files by default (respects 32/64-bit automatically)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Skip the "Select Start Menu Folder" page — we always use the default
DisableProgramGroupPage=yes

; Output
OutputDir=..\dist
OutputBaseFilename=SortlySetup-{#MyAppVersion}
SetupIconFile=..\assets\sortly_logos\ICO\sortly.ico

; Wizard images (Inno Setup 6 supports PNG natively)
; WizardImageFile   : tall left-panel image shown on all wizard pages
; WizardSmallImageFile : small top-right image on welcome/finish pages
WizardImageFile=..\assets\sortly_logos\PNG\transparent\sortly_transparent_1024x1024.png
WizardSmallImageFile=..\assets\sortly_logos\PNG\dark\sortly_dark_64x64.png
WizardImageStretch=yes

; Compression
Compression=lzma2/ultra64
SolidCompression=yes

; Appearance
WizardStyle=modern

; Require 64-bit Windows
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Ask for elevation; allow user to override to per-user install
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Exe version metadata
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (C) 2026 Arsh Sisodiya

; Minimum Windows version: Windows 10
MinVersion=10.0

; ============================================================
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ============================================================
[Tasks]
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; \
  Flags: unchecked

; ============================================================
[Files]
; Copy entire PyInstaller onedir output (exe + all Qt/Python dlls)
Source: "..\dist\sortly-gui\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ============================================================
[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; \
  Comment: "Windows file organizer"

Name: "{group}\Uninstall {#MyAppName}"; \
  Filename: "{uninstallexe}"

; Desktop (optional task)
Name: "{autodesktop}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

; ============================================================
[Run]
; "Launch Sortly" checkbox at the end of setup
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

; ============================================================
[UninstallDelete]
; Remove the user-data directory on uninstall (optional — comment out to keep settings)
; Type: dirifempty; Name: "{userappdata}\.sortly"
