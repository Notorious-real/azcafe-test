# ============================================================
#  AZ Cafe - Auto-Startup Setup for Client PCs
#  Run this ONCE on each client PC after installing
#  It adds AZCafe_Client.exe to Windows startup
#  Usage: python setup_autostart.py
# ============================================================

import os
import sys
import winreg
import shutil

APP_NAME   = "AZCafeClient"
EXE_NAME   = "AZCafe_Client.exe"

def find_exe():
    """Find the client exe — checks common locations."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "dist", "AZCafe_Client", EXE_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), EXE_NAME),
        os.path.join("C:\\", "AZCafe", EXE_NAME),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def add_to_startup(exe_path: str):
    """Add exe to HKCU startup registry key."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"ERROR adding to registry: {e}")
        return False


def remove_from_startup():
    """Remove exe from startup (for uninstall)."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("Removed from startup.")
    except FileNotFoundError:
        print("Not in startup — nothing to remove.")
    except Exception as e:
        print(f"ERROR: {e}")


def check_startup():
    """Check if already in startup."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path, 0, winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return val
    except FileNotFoundError:
        return None


def main():
    print("=" * 50)
    print("  AZ Cafe Client — Auto-Startup Setup")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_from_startup()
        return

    # Check current status
    current = check_startup()
    if current:
        print(f"\nAlready in startup:\n  {current}")
        ans = input("\nUpdate it? (y/n): ").strip().lower()
        if ans != "y":
            print("No changes made.")
            return

    # Find exe
    exe_path = find_exe()
    if not exe_path:
        print(f"\nERROR: Could not find {EXE_NAME}")
        print("\nPlease enter the full path to AZCafe_Client.exe:")
        exe_path = input("Path: ").strip().strip('"')
        if not os.path.exists(exe_path):
            print("File not found. Exiting.")
            sys.exit(1)

    print(f"\nFound exe: {exe_path}")

    # Add to startup
    if add_to_startup(exe_path):
        print(f"\nSUCCESS: AZ Cafe Client will now start automatically with Windows.")
        print(f"Registry key: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{APP_NAME}")
    else:
        print("\nFAILED: Could not add to startup.")
        print("Try running as Administrator.")

    print("\nTo remove from startup later, run:")
    print("  python setup_autostart.py --remove")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
