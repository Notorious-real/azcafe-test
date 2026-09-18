# ============================================================
#  AZ Cafe - Application Paths
#  Resolves where data (database, game list, logs, backups) lives.
#
#  Priority:
#    1. AZCAFE_DATA_DIR environment variable  (used by tests / portable mode)
#    2. %PROGRAMDATA%\AZCafe   when running as a frozen .exe
#    3. Repository root        when running from source
# ============================================================

import os
import sys


APP_DIR_NAME = "AZCafe"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> str:
    """Directory the app itself lives in (exe folder when frozen)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """
    Writable folder for azcafe.db, games.json, logs and backups.
    Created on first use.
    """
    override = os.environ.get("AZCAFE_DATA_DIR")
    if override:
        path = os.path.abspath(override)
    elif is_frozen():
        base = os.environ.get("PROGRAMDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_DIR_NAME)
    else:
        path = os.path.dirname(os.path.abspath(__file__))

    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        # Last resort: never crash on a read-only location
        path = os.path.join(os.path.expanduser("~"), f".{APP_DIR_NAME.lower()}")
        os.makedirs(path, exist_ok=True)
    return path


def data_path(*parts: str) -> str:
    return os.path.join(data_dir(), *parts)


def backups_dir() -> str:
    path = data_path("backups")
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir() -> str:
    path = data_path("logs")
    os.makedirs(path, exist_ok=True)
    return path


def resource_path(*parts: str) -> str:
    """
    Read-only bundled resources (assets/logo.png).
    Works both from source and from a PyInstaller bundle.
    """
    base = getattr(sys, "_MEIPASS", None) or install_dir()
    return os.path.join(base, *parts)
