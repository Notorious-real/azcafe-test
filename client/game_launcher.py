# ============================================================
#  AZ Cafe Client - Game Launcher UI (Phase 6.5 C)
#  Custom kiosk game launcher for member sessions
# ============================================================

import tkinter as tk
from tkinter import messagebox
import subprocess
import os
import sys

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config

# Pre-configured popular games & applications
DEFAULT_GAMES = [
    {
        "name": "Steam",
        "category": "Launcher",
        "icon": "🎮",
        "cmd": r"C:\Program Files (x86)\Steam\steam.exe",
        "color": "#171a21"
    },
    {
        "name": "Discord",
        "category": "Chat",
        "icon": "💬",
        "cmd": r"C:\Users\Public\Desktop\Discord.lnk",
        "color": "#5865F2"
    },
    {
        "name": "Google Chrome",
        "category": "Browser",
        "icon": "🌐",
        "cmd": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "color": "#4285F4"
    },
    {
        "name": "Valorant",
        "category": "FPS",
        "icon": "🎯",
        "cmd": r"C:\Riot Games\Riot Client\RiotClientServices.exe",
        "color": "#FF4655"
    },
    {
        "name": "Counter-Strike 2",
        "category": "FPS",
        "icon": "💣",
        "cmd": "steam://rungameid/730",
        "color": "#DE9B35"
    },
    {
        "name": "GTA V",
        "category": "Action",
        "icon": "🚗",
        "cmd": "steam://rungameid/271590",
        "color": "#287336"
    },
    {
        "name": "Minecraft",
        "category": "Sandbox",
        "icon": "⛏️",
        "cmd": r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe",
        "color": "#5C8E32"
    },
    {
        "name": "Epic Games",
        "category": "Launcher",
        "icon": "🚀",
        "cmd": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        "color": "#333333"
    }
]


class GameLauncherScreen(tk.Frame):
    """
    Full-screen kiosk game launcher UI for active sessions.
    Allows users to play pre-approved games and apps securely.
    """

    def __init__(self, parent, user_name: str = "Member", on_end_session=None, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.user_name = user_name
        self.on_end_session = on_end_session
        self.remaining_secs = 0
        self.running_processes = []
        self._build_ui()

    def _build_ui(self):
        # ── Top Bar ─────────────────────────────────────────────
        top = tk.Frame(self, bg=config.COLOR_BG2, height=60)
        top.pack(fill=tk.X)
        top.pack_propagate(False)

        # Brand / Logo
        brand_frame = tk.Frame(top, bg=config.COLOR_BG2)
        brand_frame.pack(side=tk.LEFT, padx=20)

        tk.Label(
            brand_frame, text="AZ CAFE",
            font=("Segoe UI", 16, "bold"),
            fg=config.COLOR_RED, bg=config.COLOR_BG2
        ).pack(side=tk.LEFT)

        tk.Label(
            brand_frame, text="  GAME LAUNCHER",
            font=("Segoe UI", 10, "bold"),
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2
        ).pack(side=tk.LEFT, padx=10)

        # Right status & controls
        right = tk.Frame(top, bg=config.COLOR_BG2)
        right.pack(side=tk.RIGHT, padx=20)

        # Timer Badge
        self.time_lbl = tk.Label(
            right, text="00:00:00",
            font=("Segoe UI", 14, "bold"),
            fg=config.COLOR_GREEN, bg=config.COLOR_BG3,
            padx=14, pady=4
        )
        self.time_lbl.pack(side=tk.LEFT, padx=10)

        # User Info
        user_frame = tk.Frame(right, bg=config.COLOR_BG2)
        user_frame.pack(side=tk.LEFT, padx=10)

        tk.Label(
            user_frame, text=f"👤 {self.user_name}",
            font=("Segoe UI", 10, "bold"),
            fg=config.COLOR_TEXT, bg=config.COLOR_BG2
        ).pack(anchor="e")

        # End Session Button
        tk.Button(
            right, text="🔒 End Session",
            command=self._confirm_end_session,
            font=("Segoe UI", 9, "bold"),
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.LEFT, padx=10)

        tk.Frame(self, bg=config.COLOR_RED, height=2).pack(fill=tk.X)

        # ── Main Content Area ──────────────────────────────────
        main = tk.Frame(self, bg=config.COLOR_BG, padx=40, pady=30)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="SELECT A GAME OR APP TO LAUNCH",
            font=("Segoe UI", 12, "bold"),
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG
        ).pack(anchor="w", pady=(0, 20))

        # Grid Container
        grid_frame = tk.Frame(main, bg=config.COLOR_BG)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        cols = 4
        for idx, game in enumerate(DEFAULT_GAMES):
            r = idx // cols
            c = idx % cols
            self._build_game_card(grid_frame, game, r, c)

    def _build_game_card(self, parent, game: dict, row: int, col: int):
        card = tk.Frame(
            parent, bg=config.COLOR_BG3,
            highlightbackground=config.COLOR_BORDER,
            highlightthickness=1, padx=15, pady=15,
            width=220, height=140
        )
        card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        card.pack_propagate(False)

        # Category badge
        tk.Label(
            card, text=game["category"].upper(),
            font=("Segoe UI", 7, "bold"),
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG3
        ).pack(anchor="w")

        # Game Icon & Title
        icon_lbl = tk.Label(
            card, text=game["icon"],
            font=("Segoe UI", 28),
            bg=config.COLOR_BG3
        )
        icon_lbl.pack(pady=(2, 2))

        title_lbl = tk.Label(
            card, text=game["name"],
            font=("Segoe UI", 10, "bold"),
            fg=config.COLOR_TEXT, bg=config.COLOR_BG3
        )
        title_lbl.pack()

        # Hover & Click bindings
        for w in (card, icon_lbl, title_lbl):
            w.bind("<Enter>", lambda e, c=card: c.config(bg=config.COLOR_RED_DARK))
            w.bind("<Leave>", lambda e, c=card: c.config(bg=config.COLOR_BG3))
            w.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

    def _launch_game(self, game: dict):
        cmd = game["cmd"]
        try:
            if cmd.startswith("steam://"):
                os.startfile(cmd)
            elif os.path.exists(cmd):
                proc = subprocess.Popen([cmd])
                self.running_processes.append(proc)
            else:
                # Fallback to system start
                os.startfile(cmd)
        except Exception as e:
            messagebox.showinfo(
                "Launch Game",
                f"Launching {game['name']}...\nIf the game is installed, it will open shortly.",
                parent=self
            )

    def update_time(self, remaining_secs: int):
        self.remaining_secs = remaining_secs
        h = remaining_secs // 3600
        m = (remaining_secs % 3600) // 60
        s = remaining_secs % 60
        self.time_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        if remaining_secs <= 300:
            self.time_lbl.config(fg=config.COLOR_RED_BRIGHT)

    def _confirm_end_session(self):
        if messagebox.askyesno("End Session", "Are you sure you want to end your session?", parent=self):
            if self.on_end_session:
                self.on_end_session()

    def kill_launched_games(self):
        """Terminate processes launched during this session."""
        for p in self.running_processes:
            try:
                p.terminate()
            except Exception:
                pass
        self.running_processes.clear()
