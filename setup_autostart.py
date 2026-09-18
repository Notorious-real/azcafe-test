# ============================================================
#  AZ Cafe - Auto-Startup Setup for Client PCs
#
#  Run this ONCE on each client PC (or let the installer do it).
#
#  Usage:
#      python setup_autostart.py                 find the exe and enable autostart
#      python setup_autostart.py --exe PATH      use a specific exe
#      python setup_autostart.py --task          delayed start via Task Scheduler
#      python setup_autostart.py --startup-folder
#                                                shortcut in shell:startup
#      python setup_autostart.py --status        show what is registered
#      python setup_autostart.py --remove        remove all autostart entries
#
#  The client should start automatically so a customer can never sit down
#  in front of an unlocked PC: the lock screen appears seconds after login.
# ============================================================

import argparse
import os
import subprocess
import sys

try:                                    # Windows only — import guard for CI/lint
    import winreg
except ImportError:                     # pragma: no cover - non-Windows
    winreg = None

APP_NAME   = "AZCafeClient"
EXE_NAME   = "AZCafe_Client.exe"
RUN_KEY    = r"Software\Microsoft\Windows\CurrentVersion\Run"
TASK_NAME  = "AZCafeClient"
TASK_DELAY = "0000:15"                  # 15 seconds after logon


# ── Locating the exe ─────────────────────────────────────────

def candidate_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    frozen = getattr(sys, "frozen", False)
    candidates = [
        os.path.join(here, "dist", "AZCafe_Client", EXE_NAME),
        os.path.join(here, EXE_NAME),
        os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Temp"),
                     "AZCafe", "Client", EXE_NAME),
        os.path.join(r"C:\AZCafe", "Client", EXE_NAME),
        os.path.join(r"C:\AZCafe", EXE_NAME),
    ]
    if frozen:
        candidates.insert(0, sys.executable)
    return candidates


def find_exe(explicit: str = None) -> str:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for path in candidate_paths():
        if path and os.path.exists(path):
            return path
    return None


# ── Registry (HKCU Run) ──────────────────────────────────────

def get_startup_value():
    if winreg is None:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def set_startup(exe_path: str) -> bool:
    if winreg is None:
        print("ERROR: winreg is unavailable — run this on Windows.")
        return False
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                 winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                              f'"{exe_path}"')
        finally:
            winreg.CloseKey(key)
        return True
    except OSError as exc:
        print(f"ERROR adding to registry: {exc}")
        return False


def remove_startup() -> bool:
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        finally:
            winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        print(f"ERROR: {exc}")
        return False


# ── Startup folder shortcut ──────────────────────────────────

def startup_folder() -> str:
    return os.path.join(os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs",
                        "Startup")


def set_startup_shortcut(exe_path: str) -> bool:
    shortcut = os.path.join(startup_folder(), f"{APP_NAME}.lnk")
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut}'); "
        f"$s.TargetPath = '{exe_path}'; "
        f"$s.WorkingDirectory = '{os.path.dirname(exe_path)}'; "
        "$s.Save()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR creating shortcut: {exc}")
        return False


def remove_startup_shortcut() -> bool:
    shortcut = os.path.join(startup_folder(), f"{APP_NAME}.lnk")
    try:
        os.remove(shortcut)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        print(f"ERROR removing shortcut: {exc}")
        return False


# ── Task Scheduler (delayed start) ───────────────────────────

def set_startup_task(exe_path: str) -> bool:
    """Delayed logon task — more reliable than Run for kiosk PCs."""
    command = [
        "schtasks", "/create", "/tn", TASK_NAME, "/tr", f'"{exe_path}"',
        "/sc", "onlogon", "/delay", TASK_DELAY, "/f",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        print(f"ERROR calling schtasks: {exc}")
        return False
    if result.returncode != 0:
        print(f"ERROR: {result.stdout.strip()} {result.stderr.strip()}")
        return False
    return True


def remove_startup_task() -> bool:
    try:
        result = subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                                capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0


# ── Status ───────────────────────────────────────────────────

def show_status():
    value = get_startup_value()
    shortcut = os.path.join(startup_folder(), f"{APP_NAME}.lnk")
    task = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME],
                          capture_output=True, text=True) \
        if os.name == "nt" else None
    print("Autostart status")
    print(f"  HKCU Run key : {value or 'not set'}")
    print(f"  Startup .lnk : {'present' if os.path.exists(shortcut) else 'not set'}")
    print(f"  Scheduled task: "
          f"{'present' if task and task.returncode == 0 else 'not set'}")


# ── Main ─────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Enable or disable AZ Cafe Client auto-start.")
    parser.add_argument("--exe", help="full path to AZCafe_Client.exe")
    parser.add_argument("--task", action="store_true",
                        help="use a delayed Task Scheduler entry instead of the Run key")
    parser.add_argument("--startup-folder", action="store_true",
                        help="also drop a shortcut in the Startup folder")
    parser.add_argument("--remove", action="store_true",
                        help="remove every autostart entry")
    parser.add_argument("--status", action="store_true",
                        help="show what is registered")
    args = parser.parse_args(argv)

    print("=" * 52)
    print("  AZ Cafe Client — Auto-Startup Setup")
    print("=" * 52)

    if args.status:
        show_status()
        return 0

    if args.remove:
        removed = [name for name, ok in (
            ("Run key", remove_startup()),
            ("Startup shortcut", remove_startup_shortcut()),
            ("Scheduled task", remove_startup_task()),
        ) if ok]
        print("Removed: " + (", ".join(removed) if removed else "nothing was registered"))
        return 0

    exe_path = find_exe(args.exe)
    if not exe_path:
        print(f"\nCould not find {EXE_NAME} automatically.")
        answer = input("Full path to AZCafe_Client.exe: ").strip().strip('"')
        exe_path = find_exe(answer)
        if not exe_path:
            print("File not found. Exiting.")
            return 1

    print(f"\nClient exe: {exe_path}")

    ok = True
    if args.task:
        ok = set_startup_task(exe_path)
        print("Delayed logon task created (starts 15 s after sign-in)."
              if ok else "Could not create the scheduled task.")
    else:
        ok = set_startup(exe_path)
        print(f"Registry entry set: HKCU\\{RUN_KEY}\\{APP_NAME}"
              if ok else "Could not write the registry entry.")

    if args.startup_folder:
        if set_startup_shortcut(exe_path):
            print(f"Shortcut created in {startup_folder()}")

    if ok:
        print("\nSUCCESS — AZ Cafe Client now starts automatically with Windows.")
        print("Run with --status to inspect, --remove to undo.")
    else:
        print("\nFAILED — try running this script as Administrator.")
    return 0 if ok else 1


if __name__ == "__main__":
    if os.name != "nt" and len(sys.argv) > 1 and sys.argv[1] not in ("-h", "--help"):
        print("This tool configures Windows startup entries; run it on Windows.")
        raise SystemExit(1)
    raise SystemExit(main())
