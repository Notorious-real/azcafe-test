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
echo  [1/5] Upgrading pip...
%PYTHON% -m pip install --upgrade pip --quiet --no-warn-script-location
echo  Done.
echo.

:: ── Install dependencies ──────────────────────────────────────
echo  [2/5] Installing dependencies...
%PYTHON% -m pip install Pillow --quiet --no-warn-script-location
if errorlevel 1 ( echo ERROR: Pillow failed. & pause & exit /b 1 )

%PYTHON% -m pip install pyinstaller --pre --quiet --no-warn-script-location
if errorlevel 1 ( echo ERROR: PyInstaller failed. & pause & exit /b 1 )

echo  All dependencies installed.
echo.

:: ── Convert icon ──────────────────────────────────────────────
echo  [3/5] Converting logo to .ico...
%PYTHON% convert_icon.py
echo.

:: ── Clean old output ──────────────────────────────────────────
echo  [4/5] Cleaning previous build...
if exist dist\AZCafe_Admin   rmdir /s /q "dist\AZCafe_Admin"
if exist dist\AZCafe_Client  rmdir /s /q "dist\AZCafe_Client"
if exist build               rmdir /s /q "build"
echo  Clean done.
echo.

:: ── Build Admin ───────────────────────────────────────────────
echo  [5/5] Building Admin app...
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
  --add-data "config.py;." ^
  --add-data "protocol.py;." ^
  --add-data "database.py;." ^
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
  --hidden-import "socket" ^
  --hidden-import "json" ^
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
echo  Building Client app...
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
  --add-data "config.py;." ^
  --add-data "protocol.py;." ^
  --add-data "database.py;." ^
  --hidden-import "tkinter" ^
  --hidden-import "tkinter.font" ^
  --hidden-import "tkinter.messagebox" ^
  --hidden-import "PIL._tkinter_finder" ^
  --hidden-import "sqlite3" ^
  --hidden-import "hashlib" ^
  --hidden-import "threading" ^
  --hidden-import "socket" ^
  --hidden-import "json" ^
  --hidden-import "subprocess" ^
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
echo  2. Copy dist\AZCafe_Client\ folder to each gaming PC
echo  3. Default password: admin123
echo.
pause
