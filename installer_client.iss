; ============================================================
;  AZ Cafe — Client PC installer (Inno Setup 6)
;
;  Build first:   BUILD.bat          (creates dist\AZCafe_Client\)
;  Then compile:  iscc installer_client.iss
;  Output:        installer_output\AZCafe_Client_Setup.exe
;
;  The installer asks for the admin PC's address, stores it for the
;  client (environment variable + config file) and registers autostart,
;  so a fresh gaming PC is ready without editing any file by hand.
; ============================================================

#define AppName        "AZ Cafe Client"
#define AppVersion     "1.0"
#define AppPublisher   "AZ Cafe"
#define ClientExe      "AZCafe_Client.exe"
#define SourceDir      "dist\AZCafe_Client"

[Setup]
AppId={{8F2C41B6-6C1E-4E4C-9C7A-AZC0FE000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\AZCafe\Client
DefaultGroupName=AZ Cafe
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AZCafe_Client_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start AZ Cafe Client automatically when Windows starts"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\{#ClientExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Registry]
; Autostart for the signed-in customer account (no admin rights needed)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "AZCafeClient"; \
    ValueData: """{app}\{#ClientExe}"""; \
    Flags: uninsdeletevalue; Tasks: autostart
; Server address — the client reads AZCAFE_SERVER_IP before the config file
Root: HKCU; Subkey: "Environment"; ValueType: string; \
    ValueName: "AZCAFE_SERVER_IP"; ValueData: "{code:GetServerIp}"; \
    Flags: uninsdeletevalue

[Icons]
Name: "{autoprograms}\AZ Cafe Client"; Filename: "{app}\{#ClientExe}"
Name: "{autodesktop}\AZ Cafe Client"; Filename: "{app}\{#ClientExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ClientExe}"; Description: "Start AZ Cafe Client now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\*.log"

[Code]
var
  ServerPage: TInputQueryWizardPage;

function GetServerIp(Param: String): String;
begin
  Result := ServerPage.Values[0];
end;

procedure InitializeWizard;
begin
  ServerPage := CreateInputQueryPage(wpSelectTasks,
    'Admin PC address',
    'Where is the admin PC?',
    'Type the LAN IP (or PC name) of the computer running AZ Cafe Admin.' + #13#10 +
    'Run  ipconfig  on that PC and look for "IPv4 Address" — for example 192.168.1.10.');
  ServerPage.Add('Server address:', False);
  ServerPage.Values[0] := '192.168.1.10';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Ip: String;
begin
  Result := True;
  if CurPageID = ServerPage.ID then
  begin
    Ip := Trim(ServerPage.Values[0]);
    if Ip = '' then
    begin
      MsgBox('Please enter the admin PC address.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath: String;
  Json: String;
begin
  if CurStep = ssPostInstall then
  begin
    { Also write the JSON config so tools that ignore env vars still work. }
    ConfigPath := ExpandConstant('{commonappdata}\AZCafe');
    if not ForceDirectories(ConfigPath) then
      ConfigPath := ExpandConstant('{localappdata}\AZCafe');
    Json := '{"server_ip": "' + Trim(ServerPage.Values[0]) +
            '", "server_port": 5555}' + #13#10;
    SaveStringToFile(ConfigPath + '\client_config.json', Json, False);
  end;
end;
