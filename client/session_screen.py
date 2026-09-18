# ============================================================
#  AZ Cafe - Session Screen
#  Shown in corner/overlay when session is active
#  Displays remaining time + user name
# ============================================================

import tkinter as tk
import os
import sys

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config


class SessionOverlay(tk.Toplevel):
    """
    Small floating overlay shown during an active session.
    Always-on-top, shows remaining time.
    User can minimize it but cannot close it.
    """

    def __init__(self, parent, user: str, duration_secs: int):
        super().__init__(parent)

        self.user            = user
        self.remaining_secs  = duration_secs
        self.paused          = False

        self._build_ui()
        self._position_window()
        self._tick()

    def _build_ui(self):
        self.title("")
        self.configure(bg=config.COLOR_BG2)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.overrideredirect(True)   # No titlebar — custom one below

        # Drag support
        self.bind("<ButtonPress-1>",   self._drag_start)
        self.bind("<B1-Motion>",       self._drag_motion)

        # ── Top strip ─────────────────────────────────────────
        top = tk.Frame(self, bg=config.COLOR_RED, height=3)
        top.pack(fill=tk.X)
        top.bind("<ButtonPress-1>", self._drag_start)
        top.bind("<B1-Motion>",     self._drag_motion)

        # ── Header ────────────────────────────────────────────
        header = tk.Frame(self, bg=config.COLOR_BG2, padx=12, pady=6)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=config.APP_NAME,
            font=("Segoe UI", 8, "bold"),
            fg=config.COLOR_RED,
            bg=config.COLOR_BG2
        ).pack(side=tk.LEFT)

        # Minimize button
        tk.Label(
            header,
            text="—",
            font=("Segoe UI", 10),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2,
            cursor="hand2"
        ).pack(side=tk.RIGHT)

        # ── User name ─────────────────────────────────────────
        tk.Label(
            self,
            text=self.user,
            font=("Segoe UI", 9),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        ).pack(padx=14)

        # ── Timer ─────────────────────────────────────────────
        self._timer_var = tk.StringVar(value="00:00:00")
        self._timer_lbl = tk.Label(
            self,
            textvariable=self._timer_var,
            font=("Segoe UI", 22, "bold"),
            fg=config.COLOR_GREEN,
            bg=config.COLOR_BG2,
            padx=14, pady=4
        )
        self._timer_lbl.pack()

        # ── Status ────────────────────────────────────────────
        self._status_var = tk.StringVar(value="SESSION ACTIVE")
        tk.Label(
            self,
            textvariable=self._status_var,
            font=("Segoe UI", 7, "bold"),
            fg=config.COLOR_GREEN,
            bg=config.COLOR_BG2,
            pady=4
        ).pack()

        self.geometry("180x120")
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # Block close

    def _position_window(self):
        """Place in bottom-right corner of screen."""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_width()
        h  = self.winfo_height()
        self._target_xy = (sw - w - 20, sh - h - 60)
        self.geometry(f"+{self._target_xy[0]}+{self._target_xy[1]}")

    def slide_in(self, steps: int = 12):
        """Small polish (7D): slide the overlay up into place."""
        if not getattr(self, "_target_xy", None):
            return
        target_x, target_y = self._target_xy

        def _step(index):
            if index > steps:
                try:
                    self.geometry(f"+{target_x}+{target_y}")
                except tk.TclError:
                    pass
                return
            offset = int((steps - index) * 8)
            try:
                self.geometry(f"+{target_x}+{target_y + offset}")
                self.after(18, lambda: _step(index + 1))
            except tk.TclError:
                pass

        _step(1)

    def _drag_start(self, e):
        self._dx = e.x
        self._dy = e.y

    def _drag_motion(self, e):
        x = self.winfo_x() + e.x - self._dx
        y = self.winfo_y() + e.y - self._dy
        self.geometry(f"+{x}+{y}")

    def _tick(self):
        if not self.paused and self.remaining_secs > 0:
            self.remaining_secs -= 1

        secs = max(0, self.remaining_secs)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        self._timer_var.set(f"{h:02d}:{m:02d}:{s:02d}")

        # Color changes as time runs low
        if secs <= 300:     # last 5 mins — red
            self._timer_lbl.config(fg=config.COLOR_RED_BRIGHT)
            self._status_var.set("⚠ TIME RUNNING LOW")
        elif secs <= 600:   # last 10 mins — yellow
            self._timer_lbl.config(fg=config.COLOR_YELLOW)
        else:
            self._timer_lbl.config(fg=config.COLOR_GREEN)
            self._status_var.set("SESSION ACTIVE")

        self.after(1000, self._tick)

    def update_remaining(self, secs: int):
        self.remaining_secs = secs

    def set_paused(self, paused: bool):
        self.paused = paused
        if paused:
            self._status_var.set("⏸ PAUSED")
            self._timer_lbl.config(fg=config.COLOR_YELLOW)
        else:
            self._status_var.set("SESSION ACTIVE")
            self._timer_lbl.config(fg=config.COLOR_GREEN)

    def flash_warning(self, minutes: int):
        """Flash the overlay border red to grab attention."""
        self._status_var.set(f"⚠ {minutes} MIN LEFT!")
        original_bg = self.cget("bg")
        self._flash(3, original_bg)

    def _flash(self, count: int, original_bg: str):
        """Flash background red/dark alternately."""
        if count <= 0:
            self.configure(
                highlightthickness=1,
                highlightbackground=config.COLOR_RED
            )
            return
        flash_on = count % 2 == 0
        self.configure(
            highlightthickness=2,
            highlightbackground=config.COLOR_RED_BRIGHT if flash_on
                                else config.COLOR_RED_DARK
        )
        self.after(300, lambda: self._flash(count - 1, original_bg))
