@echo off
title AZ Cafe - Build Tool
color 0C

echo.
echo  ================================================
echo    AZ Cafe Management System - Build Tool
echo  ================================================
echo.

:: ── Set Python ────────────────────────────────────────────────
set PYTHON=python

:: Verify Python
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found in PATH.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
echo  Python version: %PYVER%
echo.

:: ── Upgrade pip ───────────────────────────────────────────────
echo  [1/7] Upgrading pip...
%PYTHON% -m pip install --upgrade pip --quiet --no-warn-script-location
echo  Done.
echo.

:: ── Install dependencies ──────────────────────────────────────
echo  [2/7] Installing dependencies...
%PYTHON% -m pip install Pillow --quiet --no-warn-script-location
if errorlevel 1 ( echo ERROR: Pillow failed. & pause & exit /b 1 )

%PYTHON% -m pip install pyinstaller --pre --quiet --no-warn-script-location
if errorlevel 1 ( echo ERROR: PyInstaller failed. & pause & exit /b 1 )

echo  All dependencies installed.
echo.

:: ── Convert icon ──────────────────────────────────────────────
echo  [3/7] Converting logo to .ico...
%PYTHON% convert_icon.py
echo.

:: ── Clean old output ──────────────────────────────────────────
echo  [4/7] Cleaning previous build...
if exist dist\AZCafe_Admin   rmdir /s /q "dist\AZCafe_Admin"
if exist dist\AZCafe_Client  rmdir /s /q "dist\AZCafe_Client"
if exist build               rmdir /s /q "build"
echo  Clean done.
echo.

:: ── Build Admin ───────────────────────────────────────────────
echo  [5/7] Building Admin app...
echo  (This takes 3-5 minutes, please wait)
echo.

%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "AZCafe_Admin" ^
  --icon "assets\logo.ico" ^
  --add-data "assets\logo.png;assets" ^
  --add-data "assets\logo.ico;assets" ^
  --hidden-import "tkinter" ^
  --hidden-import "tkinter.font" ^
  --hidden-import "tkinter.messagebox" ^
  --hidden-import "tkinter.simpledialog" ^
  --hidden-import "tkinter.filedialog" ^
  --hidden-import "tkinter.ttk" ^
  --hidden-import "PIL._tkinter_finder" ^
  --hidden-import "sqlite3" ^
  --hidden-import "csv" ^
  --hidden-import "hashlib" ^
  --hidden-import "threading" ^
  --hidden-import "queue" ^
  --hidden-import "socket" ^
  --hidden-import "json" ^
  --hidden-import "shutil" ^
  --hidden-import "webbrowser" ^
  --hidden-import "zipfile" ^
  --hidden-import "xml.etree.ElementTree" ^
  --hidden-import "logging.handlers" ^
  --collect-all "PIL" ^
  --collect-all "tkinter" ^
  --paths "." ^
  "server\main.py"

if errorlevel 1 (
    echo.
    echo  !! Admin build FAILED !!
    echo  Check output above for errors.
    pause
    exit /b 1
)

echo.
echo  Admin build complete.
echo.

:: ── Build Client ──────────────────────────────────────────────
echo  [6/7] Building Client app...
echo  (This takes 3-5 minutes, please wait)
echo.

%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "AZCafe_Client" ^
  --icon "assets\logo.ico" ^
  --add-data "assets\logo.png;assets" ^
  --add-data "assets\logo.ico;assets" ^
  --hidden-import "tkinter" ^
  --hidden-import "tkinter.font" ^
  --hidden-import "tkinter.messagebox" ^
  --hidden-import "PIL._tkinter_finder" ^
  --hidden-import "sqlite3" ^
  --hidden-import "hashlib" ^
  --hidden-import "threading" ^
  --hidden-import "queue" ^
  --hidden-import "socket" ^
  --hidden-import "json" ^
  --hidden-import "subprocess" ^
  --hidden-import "ctypes" ^
  --hidden-import "winsound" ^
  --hidden-import "logging.handlers" ^
  --collect-all "PIL" ^
  --collect-all "tkinter" ^
  --paths "." ^
  "client\main.py"

if errorlevel 1 (
    echo.
    echo  !! Client build FAILED !!
    echo  Check output above for errors.
    pause
    exit /b 1
)

:: ── Ship the install helpers with the build ───────────────────
echo.
echo  [7/7] Copying deployment helpers...
copy /y "setup_autostart.py" "dist\AZCafe_Client\" >nul
copy /y "setup_autostart.py" "dist\AZCafe_Admin\"  >nul
copy /y "INSTALL_CLIENT.bat" "dist\AZCafe_Client\" >nul
copy /y "DEPLOY.md"          "dist\AZCafe_Client\" >nul
copy /y "DEPLOY.md"          "dist\AZCafe_Admin\"  >nul
echo  Done.

:: ── Optional: compile the Inno Setup installers ───────────────
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    echo.
    echo  Inno Setup found - building installers...
    %ISCC% installer_admin.iss  >nul
    %ISCC% installer_client.iss >nul
    echo  Installers written to installer_output\
) else (
    echo.
    echo  Inno Setup 6 not installed - skipping installer build.
    echo  Download it from https://jrsoftware.org/isdl.php and rerun,
    echo  or use INSTALL_CLIENT.bat / setup_autostart.py on each PC.
)

echo.
echo  ================================================
echo    BUILD COMPLETE!
echo  ================================================
echo.
echo  Admin:   dist\AZCafe_Admin\AZCafe_Admin.exe
echo  Client:  dist\AZCafe_Client\AZCafe_Client.exe
echo.
echo  Next steps:
echo  1. Run AZCafe_Admin.exe on this PC
echo  2. Install the client on each gaming PC:
echo       - installer_output\AZCafe_Client_Setup.exe  (recommended), or
echo       - copy dist\AZCafe_Client\ and run INSTALL_CLIENT.bat
echo  3. Change the default admin password in Settings
echo.
pause
