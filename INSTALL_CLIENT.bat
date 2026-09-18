@echo off
setlocal
title AZ Cafe Client - Quick Install
color 0C

echo.
echo  ================================================
echo    AZ Cafe Client - Quick Install
echo  ================================================
echo.
echo  Copies the client to %LOCALAPPDATA%\AZCafe\Client,
echo  stores the admin PC address and enables auto-start.
echo.
echo  For a normal setup, use installer_output\AZCafe_Client_Setup.exe
echo  instead of this script.
echo.

set "SRC=%~dp0dist\AZCafe_Client"
set "DEST=%LOCALAPPDATA%\AZCafe\Client"

if not exist "%SRC%\AZCafe_Client.exe" (
    echo  ERROR: %SRC%\AZCafe_Client.exe not found.
    echo  Run BUILD.bat first.
    echo.
    pause
    exit /b 1
)

set /p SERVERIP=  Admin PC IP address (e.g. 192.168.1.10):
if "%SERVERIP%"=="" (
    echo  No address entered - nothing installed.
    pause
    exit /b 1
)

echo.
echo  [1/4] Copying client to "%DEST%" ...
robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo  ERROR: copy failed.
    pause
    exit /b 1
)

echo  [2/4] Saving the server address ...
reg add "HKCU\Environment" /v AZCAFE_SERVER_IP /t REG_SZ /d "%SERVERIP%" /f >nul
if not exist "%PROGRAMDATA%\AZCafe" mkdir "%PROGRAMDATA%\AZCafe" >nul 2>&1
powershell -NoProfile -Command ^
  "$d='%PROGRAMDATA%\AZCafe'; if (-not (Test-Path $d)) { $d=Join-Path $env:LOCALAPPDATA 'AZCafe' }; New-Item -ItemType Directory -Force -Path $d | Out-Null; @{server_ip='%SERVERIP%'; server_port=5555} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $d 'client_config.json')" >nul

echo  [3/4] Enabling auto-start ...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v AZCafeClient /t REG_SZ /d "\"%DEST%\AZCafe_Client.exe\"" /f >nul

echo  [4/4] Starting the client ...
start "" "%DEST%\AZCafe_Client.exe"

echo.
echo  ================================================
echo    DONE
echo  ================================================
echo.
echo  Client folder : %DEST%
echo  Server address: %SERVERIP%
echo  Auto-start    : enabled (remove with setup_autostart.py --remove)
echo.
echo  Repeat this on every gaming PC.
echo.
pause
