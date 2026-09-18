# ============================================================
#  AZ Cafe Client - Game Launcher  (Phase 6.5C)
#  Tiles come from games.json (editable in Admin → Settings → Games)
#  instead of being hardcoded, unavailable titles are shown greyed
#  out, and a failed launch says so instead of pretending it worked.
# ============================================================

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config                                            # noqa: E402
import games as games_store                              # noqa: E402
from client import sounds                                # noqa: E402


class GameLauncherScreen(tk.Frame):
    """Full-screen launcher: pick a game, watch the clock, end the session."""

    def __init__(self, parent, user_name: str = "Member", on_end_session=None,
                 **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.user_name = user_name
        self.on_end_session = on_end_session
        self.remaining_secs = 0
        self.running_processes = []
        self.games = games_store.load_games()
        self._filter = tk.StringVar()
        self._tiles = []
        self._build_ui()
        self._render_games()

    # ── layout ──────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg=config.COLOR_BG2, height=64)
        top.pack(fill=tk.X)
        top.pack_propagate(False)

        brand = tk.Frame(top, bg=config.COLOR_BG2)
        brand.pack(side=tk.LEFT, padx=20)
        tk.Label(brand, text="AZ CAFE", font=("Segoe UI", 16, "bold"),
                 fg=config.COLOR_RED, bg=config.COLOR_BG2).pack(side=tk.LEFT)
        tk.Label(brand, text="  GAME LAUNCHER", font=("Segoe UI", 10, "bold"),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=10)

        right = tk.Frame(top, bg=config.COLOR_BG2)
        right.pack(side=tk.RIGHT, padx=20)

        self.time_lbl = tk.Label(right, text="00:00:00", font=("Consolas", 22, "bold"),
                                 fg=config.COLOR_GREEN, bg=config.COLOR_BG2)
        self.time_lbl.pack(side=tk.RIGHT, padx=(14, 0))

        tk.Label(right, text=self.user_name, font=("Segoe UI", 10),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2).pack(side=tk.RIGHT, padx=6)

        tk.Button(right, text="⏻  End Session", command=self._confirm_end_session,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=6,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT, padx=10)

        tk.Frame(self, bg=config.COLOR_RED, height=2).pack(fill=tk.X)

        main = tk.Frame(self, bg=config.COLOR_BG, padx=40, pady=24)
        main.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(main, bg=config.COLOR_BG)
        header.pack(fill=tk.X)
        tk.Label(header, text="SELECT A GAME OR APP TO LAUNCH",
                 font=("Segoe UI", 12, "bold"),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        search = tk.Entry(header, textvariable=self._filter, width=22,
                          font=("Segoe UI", 10), bg=config.COLOR_BG3,
                          fg=config.COLOR_TEXT, insertbackground=config.COLOR_TEXT,
                          relief=tk.FLAT, bd=5)
        search.pack(side=tk.RIGHT)
        self._filter.trace_add("write", lambda *_: self._render_games())

        self.grid_frame = tk.Frame(main, bg=config.COLOR_BG)
        self.grid_frame.pack(fill=tk.BOTH, expand=True, pady=(16, 0))

    # ── tiles ───────────────────────────────────────────────
    def _render_games(self, *_):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._tiles = []

        needle = self._filter.get().strip().lower()
        games = [g for g in self.games
                 if needle in g.get("name", "").lower()
                 or needle in g.get("category", "").lower()]
        if not games:
            tk.Label(self.grid_frame, text="No games match that search.",
                     font=("Segoe UI", 11), fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG).grid(row=0, column=0, padx=10, pady=30)
            return

        columns = 4
        for index, game in enumerate(games):
            self._build_tile(self.grid_frame, game, index // columns, index % columns)

    def _build_tile(self, parent, game: dict, row: int, col: int):
        available = games_store.game_available(game)
        bg = config.COLOR_BG3 if available else "#161616"

        card = tk.Frame(parent, bg=bg, highlightbackground=config.COLOR_BORDER,
                        highlightthickness=1, padx=15, pady=12, width=230, height=150)
        card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
        card.grid_propagate(False)

        tk.Label(card, text=str(game.get("category", "")).upper(),
                 font=("Segoe UI", 7, "bold"),
                 fg=config.COLOR_TEXT_DIM if available else "#555555",
                 bg=bg).pack(anchor="w")

        icon = tk.Label(card, text=game.get("icon", "🎮"), font=("Segoe UI", 26),
                        bg=bg)
        icon.pack(pady=(4, 2))

        title = tk.Label(card, text=game.get("name", "?"),
                         font=("Segoe UI", 10, "bold"),
                         fg=config.COLOR_TEXT if available else "#777777",
                         bg=bg, wraplength=200, justify="center")
        title.pack()

        status = tk.Label(card, text="" if available else "not installed here",
                          font=("Segoe UI", 7), fg="#666666", bg=bg)
        status.pack(pady=(2, 0))

        if available:
            for widget in (card, icon, title, status):
                widget.bind("<Enter>", lambda e, c=card: c.config(bg=config.COLOR_RED_DARK))
                widget.bind("<Leave>", lambda e, c=card: c.config(bg=bg))
                widget.bind("<Button-1>", lambda e, g=game: self._launch_game(g))
            card.config(cursor="hand2")
        self._tiles.append((game, card))

    # ── launching ───────────────────────────────────────────
    def _launch_game(self, game: dict):
        cmd = str(game.get("cmd", "")).strip()
        name = game.get("name", "Game")
        sounds.play("click")

        try:
            if cmd.lower().startswith(("steam://", "http://", "https://")):
                os.startfile(cmd)                              # type: ignore[attr-defined]
            elif os.path.exists(cmd):
                self.running_processes.append(subprocess.Popen([cmd]))
            else:
                messagebox.showwarning(
                    "Not available",
                    f"{name} is not installed on this PC.\n\n"
                    f"Expected at:\n{cmd}\n\nPlease tell the counter.",
                    parent=self)
                return
        except Exception as exc:                               # noqa: BLE001
            messagebox.showerror(
                "Could not launch",
                f"{name} could not be started.\n\n{exc}\n\nPlease tell the counter.",
                parent=self)
            return

        self._flash_status(f"Launching {name}…")

    def _flash_status(self, message: str):
        banner = tk.Label(self, text=message, font=("Segoe UI", 10, "bold"),
                          fg=config.COLOR_TEXT, bg=config.COLOR_BG3, pady=8)
        banner.place(relx=0.5, rely=0.06, anchor="center")
        banner.after(2200, banner.destroy)

    # ── clock / lifecycle ───────────────────────────────────
    def update_time(self, remaining_secs: int):
        self.remaining_secs = max(0, remaining_secs)
        hours, rest = divmod(self.remaining_secs, 3600)
        minutes, seconds = divmod(rest, 60)
        self.time_lbl.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        if self.remaining_secs <= 300:
            self.time_lbl.config(fg=config.COLOR_RED_BRIGHT)
        elif self.remaining_secs <= 600:
            self.time_lbl.config(fg=config.COLOR_YELLOW)
        else:
            self.time_lbl.config(fg=config.COLOR_GREEN)

    def _confirm_end_session(self):
        if messagebox.askyesno("End Session",
                               "End your session now?\n\n"
                               "Your PC will be locked and the counter will be told.",
                               parent=self):
            if self.on_end_session:
                self.on_end_session()

    def kill_launched_games(self):
        """Close what we launched (best effort — some launchers spawn children)."""
        for process in list(self.running_processes):
            try:
                process.terminate()
            except Exception:                                  # noqa: BLE001
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, timeout=10)
                except Exception:                              # noqa: BLE001
                    pass
        self.running_processes.clear()
