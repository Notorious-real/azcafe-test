; ============================================================
;  AZ Cafe — Admin PC installer (Inno Setup 6)
;
;  Build first:   BUILD.bat          (creates dist\AZCafe_Admin\)
;  Then compile:  iscc installer_admin.iss
;  Output:        installer_output\AZCafe_Admin_Setup.exe
;
;  Installs the admin app, adds a firewall rule for the server port and
;  creates a desktop shortcut. Data lives in %PROGRAMDATA%\AZCafe so
;  reinstalling or upgrading the app never touches the database.
; ============================================================

#define AppName       "AZ Cafe Admin"
#define AppVersion    "1.0"
#define AppPublisher  "AZ Cafe"
#define AdminExe      "AZCafe_Admin.exe"
#define ServerPort    "5555"
#define SourceDir     "dist\AZCafe_Admin"

[Setup]
AppId={{8F2C41B6-6C1E-4E4C-9C7A-AZC0FE000002}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AZCafe
DefaultGroupName=AZ Cafe
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AZCafe_Admin_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "firewall"; Description: "Allow client PCs to connect (adds a Windows Firewall rule for port {#ServerPort})"; GroupDescription: "Network:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\{#AdminExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "setup_autostart.py"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "DEPLOY.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\AZ Cafe Admin"; Filename: "{app}\{#AdminExe}"
Name: "{autodesktop}\AZ Cafe Admin"; Filename: "{app}\{#AdminExe}"; Tasks: desktopicon

[Run]
; netsh is available everywhere and does not need the PowerShell execution policy
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""AZ Cafe Server"""; \
    Flags: runhidden; Tasks: firewall
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""AZ Cafe Server"" dir=in action=allow protocol=TCP localport={#ServerPort}"; \
    Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AdminExe}"; Description: "Start AZ Cafe Admin now"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""AZ Cafe Server"""; \
    Flags: runhidden; RunOnceId: "RemoveFirewallRule"
