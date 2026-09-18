# ============================================================
#  AZ Cafe - Game launcher catalogue  (Phase 6.5C)
#  Games live in games.json inside the data folder instead of
#  being hardcoded, so the operator can add a title without a
#  rebuild. Editable from Admin → Settings → Games.
# ============================================================

import json
import os

import paths

GAMES_FILE = "games.json"

DEFAULT_GAMES = [
    {"name": "Steam",           "category": "Launcher", "icon": "🎮",
     "cmd": r"C:\Program Files (x86)\Steam\steam.exe"},
    {"name": "Discord",         "category": "Chat",     "icon": "💬",
     "cmd": r"C:\Users\Public\Desktop\Discord.lnk"},
    {"name": "Google Chrome",   "category": "Browser",  "icon": "🌐",
     "cmd": r"C:\Program Files\Google\Chrome\Application\chrome.exe"},
    {"name": "Valorant",        "category": "FPS",      "icon": "🎯",
     "cmd": r"C:\Riot Games\Riot Client\RiotClientServices.exe"},
    {"name": "Counter-Strike 2", "category": "FPS",     "icon": "💣",
     "cmd": "steam://rungameid/730"},
    {"name": "GTA V",           "category": "Action",   "icon": "🚗",
     "cmd": "steam://rungameid/271590"},
    {"name": "Minecraft",       "category": "Sandbox",  "icon": "⛏️",
     "cmd": r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe"},
    {"name": "Epic Games",      "category": "Launcher", "icon": "🚀",
     "cmd": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"},
]

CATEGORIES = ["Launcher", "Browser", "Chat", "FPS", "MOBA", "Action",
              "Sports", "Sandbox", "Other"]
ICONS = ["🎮", "💬", "🌐", "🎯", "💣", "🚗", "⛏️", "🚀", "⚽", "🕹️", "🧩", "🎲"]


def games_path() -> str:
    return paths.data_path(GAMES_FILE)


def load_games() -> list:
    """Games for the launcher. Falls back to the built-in list."""
    path = games_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [g for g in data if validate_game(g) is None]
        except (OSError, json.JSONDecodeError):
            pass
    return [dict(game) for game in DEFAULT_GAMES]


def save_games(games: list) -> str:
    path = games_path()
    clean = [g for g in games if validate_game(g) is None]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2, ensure_ascii=False)
    return path


def reset_games() -> list:
    games = [dict(game) for game in DEFAULT_GAMES]
    save_games(games)
    return games


def validate_game(game: dict):
    """Return None when valid, otherwise a human-readable problem."""
    if not isinstance(game, dict):
        return "Entry is not an object."
    if not str(game.get("name", "")).strip():
        return "Name is required."
    cmd = str(game.get("cmd", "")).strip()
    if not cmd:
        return "Command / path is required."
    return None


def game_available(game: dict) -> bool:
    """steam:// URLs are assumed available; files must exist."""
    cmd = str(game.get("cmd", "")).strip()
    if cmd.lower().startswith(("steam://", "http://", "https://")):
        return True
    return os.path.exists(cmd)


def available_flags(games: list) -> list:
    """[(game, is_available)] for the launcher tiles."""
    return [(g, game_available(g)) for g in games]
