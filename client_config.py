# ============================================================
#  AZ Cafe - Client configuration file
#  Server address and PC name live in client_config.json inside the
#  data folder, so changing the admin PC's IP no longer needs a
#  rebuild. Environment variables win, for scripting.
#      AZCAFE_SERVER_IP, AZCAFE_PC_NAME, AZCAFE_SERVER_PORT
# ============================================================

import json
import os
import socket

import paths

CLIENT_CONFIG_FILE = "client_config.json"

# Kept in sync with config.SERVER_PORT on the admin side. The client reads
# this file / the AZCAFE_* environment variables, so it never needs a rebuild
# when the shop's address changes.
DEFAULT_SERVER_PORT = 5555

DEFAULTS = {
    "server_ip": "",
    "server_port": DEFAULT_SERVER_PORT,
    "pc_name": "",
    "kiosk_mode": True,
}


def client_config_path() -> str:
    return paths.data_path(CLIENT_CONFIG_FILE)


def default_pc_name() -> str:
    return socket.gethostname()


def load_client_config() -> dict:
    data = dict(DEFAULTS)
    path = client_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, json.JSONDecodeError):
            pass

    data["server_ip"] = (os.environ.get("AZCAFE_SERVER_IP")
                         or data.get("server_ip") or "")
    try:
        data["server_port"] = int(os.environ.get("AZCAFE_SERVER_PORT")
                                  or data.get("server_port")
                                  or DEFAULT_SERVER_PORT)
    except (TypeError, ValueError):
        data["server_port"] = DEFAULT_SERVER_PORT
    data["pc_name"] = (os.environ.get("AZCAFE_PC_NAME")
                       or data.get("pc_name") or default_pc_name())
    return data


def save_client_config(server_ip: str = None, server_port: int = None,
                       pc_name: str = None, kiosk_mode: bool = None) -> str:
    data = load_client_config()
    if server_ip is not None:
        data["server_ip"] = server_ip.strip()
    if server_port is not None:
        data["server_port"] = int(server_port)
    if pc_name is not None:
        data["pc_name"] = pc_name.strip() or default_pc_name()
    if kiosk_mode is not None:
        data["kiosk_mode"] = bool(kiosk_mode)

    path = client_config_path()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({k: data[k] for k in DEFAULTS}, handle, indent=2)
    return path


def is_configured() -> bool:
    return bool(load_client_config().get("server_ip"))
