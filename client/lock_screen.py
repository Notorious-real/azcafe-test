# ============================================================
#  AZ Cafe - Client Lock Screen
#  Full-screen lock shown when no session is active
#  Admin can unlock via hidden button + password
# ============================================================

import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk
import os
import sys
import time

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config

LOGO_PATH = os.path.join(ROOT_DIR, "assets", "logo.png")


class LockScreen(tk.Frame):
    """
    Full-screen lock screen shown when:
    - No active session
    - Admin locks the PC
    - Session expires

    Has a hidden admin unlock area (bottom-right corner)
    and a visible Member Login button (3B).
    """

    def __init__(self, parent, on_admin_unlock,
                 on_member_login_attempt=None, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.on_admin_unlock          = on_admin_unlock
        self.on_member_login_attempt  = on_member_login_attempt or (lambda u, p: None)
        self._click_count             = 0
        self._click_timer             = None
        self._build_ui()

    def _build_ui(self):
        # ── Center content ────────────────────────────────────
        center = tk.Frame(self, bg=config.COLOR_BG)
        center.place(relx=0.5, rely=0.45, anchor="center")

        # Logo
        if os.path.exists(LOGO_PATH):
            try:
                img = Image.open(LOGO_PATH).resize((140, 140), Image.LANCZOS)
                self._logo = ImageTk.PhotoImage(img)
                tk.Label(center, image=self._logo,
                         bg=config.COLOR_BG).pack(pady=(0, 20))
            except Exception:
                pass

        # AZ Cafe title
        tk.Label(
            center,
            text=config.APP_NAME,
            font=("Segoe UI", 38, "bold"),
            fg=config.COLOR_RED,
            bg=config.COLOR_BG
        ).pack()

        # Subtitle
        tk.Label(
            center,
            text="G A M I N G   Z O N E",
            font=("Segoe UI", 13, "bold"),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        ).pack(pady=(0, 30))

        # Red divider line
        tk.Frame(center, bg=config.COLOR_RED,
                 height=2, width=300).pack(pady=(0, 30))

        # Lock message
        tk.Label(
            center,
            text="SESSION NOT ACTIVE",
            font=("Segoe UI", 14, "bold"),
            fg=config.COLOR_TEXT,
            bg=config.COLOR_BG
        ).pack()

        tk.Label(
            center,
            text="Please ask the cashier to start your session",
            font=("Segoe UI", 10),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        ).pack(pady=(8, 0))

        # ── Member Login button ────────────────────────────────
        tk.Button(
            center,
            text="👤  Member Login",
            command=self._show_member_panel,
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=24, pady=10,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED,
            activeforeground=config.COLOR_TEXT
        ).pack(pady=(20, 0))

        # ── Clock ─────────────────────────────────────────────
        self._clock_var = tk.StringVar()
        tk.Label(
            self,
            textvariable=self._clock_var,
            font=("Segoe UI", 13),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        ).place(relx=0.5, rely=0.88, anchor="center")

        # ── Connection status ─────────────────────────────────
        self._conn_var = tk.StringVar(value="● Connecting...")
        self._conn_lbl = tk.Label(
            self,
            textvariable=self._conn_var,
            font=("Segoe UI", 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        )
        self._conn_lbl.place(relx=0.01, rely=0.98, anchor="sw")

        # ── Hidden admin area (bottom-right corner) ───────────
        # Triple-click the corner to reveal password field
        self._admin_zone = tk.Label(
            self,
            text="",
            bg=config.COLOR_BG,
            width=4, height=2,
            cursor="arrow"
        )
        self._admin_zone.place(relx=1.0, rely=1.0, anchor="se")
        self._admin_zone.bind("<Button-1>", self._corner_click)

        # Admin panel (hidden until triple-click)
        self._admin_panel = AdminUnlockPanel(
            self,
            on_unlock=self._do_admin_unlock,
            on_cancel=self._hide_admin_panel
        )

        # Member login panel (hidden until button click) — 3B
        self._member_panel = MemberLoginPanel(
            self,
            on_login_attempt=self.on_member_login_attempt,
            on_cancel=self._hide_member_panel
        )

        self._tick_clock()


    def _tick_clock(self):
        now = time.strftime("%A  %d %B %Y   %I:%M:%S %p")
        self._clock_var.set(now)
        self.after(1000, self._tick_clock)

    # ── Connection status ─────────────────────────────────────

    def set_connected(self, connected: bool):
        if connected:
            self._conn_var.set("● Connected")
            self._conn_lbl.config(fg=config.COLOR_GREEN)
        else:
            self._conn_var.set("● Connecting to server...")
            self._conn_lbl.config(fg="#cc4400")

    # ── Hidden admin corner ───────────────────────────────────

    def _corner_click(self, e):
        """Triple-click bottom-right corner to show admin panel."""
        self._click_count += 1
        if self._click_timer:
            self.after_cancel(self._click_timer)
        if self._click_count >= 3:
            self._click_count = 0
            self._show_admin_panel()
        else:
            self._click_timer = self.after(800, self._reset_clicks)

    def _reset_clicks(self):
        self._click_count = 0

    def _show_admin_panel(self):
        self._admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self._admin_panel.lift()
        self._admin_panel.focus_entry()

    def _hide_admin_panel(self):
        self._admin_panel.place_forget()

    def _do_admin_unlock(self):
        self._hide_admin_panel()
        self.on_admin_unlock()

    def _show_member_panel(self):
        self._member_panel.place(relx=0.5, rely=0.5, anchor="center")
        self._member_panel.lift()
        self._member_panel.focus_entry()

    def _hide_member_panel(self):
        self._member_panel.place_forget()

    def show_member_login(self):
        """Show the member login panel (called by ClientApp)."""
        self._show_member_panel()

    def hide_member_login(self):
        self._hide_member_panel()


class AdminUnlockPanel(tk.Frame):
    """
    Password panel that slides in when admin triple-clicks corner.
    Correct password → goes to desktop.
    """

    def __init__(self, parent, on_unlock, on_cancel, **kwargs):
        super().__init__(
            parent,
            bg=config.COLOR_BG2,
            padx=30, pady=25,
            highlightthickness=1,
            highlightbackground=config.COLOR_RED,
            **kwargs
        )
        self.on_unlock = on_unlock
        self.on_cancel = on_cancel
        self._attempts = 0
        self._build()

    def _build(self):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(
            self,
            text="🔐  Admin Access",
            font=("Segoe UI", 12, "bold"),
            fg=config.COLOR_TEXT,
            bg=config.COLOR_BG2,
            pady=10
        ).pack()

        tk.Label(
            self,
            text="Enter admin password:",
            font=("Segoe UI", 9),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        ).pack(anchor="w")

        self._pwd_var = tk.StringVar()
        self._entry = tk.Entry(
            self,
            textvariable=self._pwd_var,
            show="●",
            font=("Segoe UI", 12),
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT,
            insertbackground=config.COLOR_TEXT,
            relief=tk.FLAT,
            bd=6,
            width=22
        )
        self._entry.pack(pady=8)
        self._entry.bind("<Return>", lambda e: self._check())

        self._msg_var = tk.StringVar()
        tk.Label(
            self,
            textvariable=self._msg_var,
            font=("Segoe UI", 8),
            fg=config.COLOR_RED_BRIGHT,
            bg=config.COLOR_BG2
        ).pack()

        btn_row = tk.Frame(self, bg=config.COLOR_BG2)
        btn_row.pack(pady=(10, 0))

        tk.Button(
            btn_row,
            text="Unlock",
            command=self._check,
            bg=config.COLOR_RED,
            fg=config.COLOR_TEXT,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            padx=18, pady=6,
            cursor="hand2",
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT,
            bd=0
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_row,
            text="Cancel",
            command=self._cancel,
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=14, pady=6,
            cursor="hand2",
            bd=0
        ).pack(side=tk.LEFT)

    def _check(self):
        import database as db
        pwd = self._pwd_var.get()
        correct = db.get_setting("admin_password", config.ADMIN_PASSWORD)
        if pwd == correct:
            self._pwd_var.set("")
            self._msg_var.set("")
            self._attempts = 0
            self.on_unlock()
        else:
            self._attempts += 1
            self._msg_var.set(f"Wrong password. ({self._attempts} attempt{'s' if self._attempts > 1 else ''})")
            self._pwd_var.set("")
            self._entry.focus_set()

    def _cancel(self):
        self._pwd_var.set("")
        self._msg_var.set("")
        self.on_cancel()

    def focus_entry(self):
        self._entry.focus_set()


# ============================================================
#  3B — Member Login Panel
#  Shown when the customer clicks "Member Login" on lock screen
# ============================================================

class MemberLoginPanel(tk.Frame):
    """
    Member self-service login panel.
    Member types username + password → request sent to server.
    Server verifies, deducts balance, starts session automatically.

    on_login_attempt(username, password) — called when form is submitted.
    on_cancel()                          — called when user dismisses panel.
    """

    def __init__(self, parent, on_login_attempt, on_cancel, **kwargs):
        super().__init__(
            parent,
            bg=config.COLOR_BG2,
            padx=32, pady=28,
            highlightthickness=1,
            highlightbackground=config.COLOR_RED,
            **kwargs
        )
        self.on_login_attempt = on_login_attempt
        self.on_cancel        = on_cancel
        self._waiting         = False
        self._build()

    def _build(self):
        # ── Title strip ───────────────────────────────────────
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)

        tk.Label(
            self,
            text="👤  Member Login",
            font=("Segoe UI", 13, "bold"),
            fg=config.COLOR_TEXT,
            bg=config.COLOR_BG2,
            pady=12
        ).pack()

        tk.Label(
            self,
            text="Login with your member account to start a session.",
            font=("Segoe UI", 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        ).pack(pady=(0, 12))

        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        # ── Fields ────────────────────────────────────────────
        fields_frame = tk.Frame(self, bg=config.COLOR_BG2, pady=14)
        fields_frame.pack(fill=tk.X)

        def _lbl(text):
            tk.Label(
                fields_frame, text=text,
                font=("Segoe UI", 9),
                fg=config.COLOR_TEXT_DIM,
                bg=config.COLOR_BG2,
                anchor="w"
            ).pack(fill=tk.X, pady=(6, 2))

        def _ent(var, show=None):
            kw = dict(
                textvariable=var,
                font=("Segoe UI", 11),
                bg=config.COLOR_BG3,
                fg=config.COLOR_TEXT,
                insertbackground=config.COLOR_TEXT,
                relief=tk.FLAT, bd=6, width=26
            )
            if show:
                kw["show"] = show
            e = tk.Entry(fields_frame, **kw)
            e.pack(fill=tk.X)
            return e

        _lbl("Username")
        self._uname_var = tk.StringVar()
        self._uname_ent = _ent(self._uname_var)
        self._uname_ent.bind("<Return>", lambda e: self._pwd_ent.focus_set())

        _lbl("Password")
        self._pwd_var = tk.StringVar()
        self._pwd_ent = _ent(self._pwd_var, show="●")
        self._pwd_ent.bind("<Return>", lambda e: self._submit())

        # ── Feedback label ────────────────────────────────────
        self._msg_var = tk.StringVar()
        self._msg_lbl = tk.Label(
            self,
            textvariable=self._msg_var,
            font=("Segoe UI", 8, "bold"),
            fg=config.COLOR_RED_BRIGHT,
            bg=config.COLOR_BG2,
            wraplength=280
        )
        self._msg_lbl.pack(pady=(4, 0))

        # ── Buttons ───────────────────────────────────────────
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(
            fill=tk.X, pady=(12, 0))

        btn_row = tk.Frame(self, bg=config.COLOR_BG2, pady=14)
        btn_row.pack(fill=tk.X)

        self._login_btn = tk.Button(
            btn_row,
            text="▶  Start Session",
            command=self._submit,
            bg=config.COLOR_RED,
            fg=config.COLOR_TEXT,
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT, padx=22, pady=9,
            cursor="hand2",
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT,
            bd=0
        )
        self._login_btn.pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            btn_row,
            text="Cancel",
            command=self._cancel,
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=16, pady=9,
            cursor="hand2", bd=0
        ).pack(side=tk.LEFT)

    # ── Actions ───────────────────────────────────────────────

    def _submit(self):
        username = self._uname_var.get().strip()
        password = self._pwd_var.get()

        if not username:
            self._show_error("Please enter your username.")
            return
        if not password:
            self._show_error("Please enter your password.")
            return

        self._set_waiting(True)
        self.on_login_attempt(username, password)

    def _cancel(self):
        self._reset()
        self.on_cancel()

    def _set_waiting(self, waiting: bool):
        self._waiting = waiting
        if waiting:
            self._login_btn.config(
                text="Verifying...",
                state=tk.DISABLED,
                bg=config.COLOR_BG3,
                fg=config.COLOR_TEXT_DIM
            )
            self._msg_var.set("")
        else:
            self._login_btn.config(
                text="▶  Start Session",
                state=tk.NORMAL,
                bg=config.COLOR_RED,
                fg=config.COLOR_TEXT
            )

    # ── Public API ────────────────────────────────────────────

    def show_result(self, success: bool, message: str):
        """Called by ClientApp with the server's LOGIN_RESULT."""
        self._set_waiting(False)
        if success:
            self._msg_lbl.config(fg=config.COLOR_GREEN)
            self._msg_var.set(f"✓  {message}")
            # Panel will be hidden by ClientApp when session_started fires
        else:
            self._show_error(message)

    def _show_error(self, msg: str):
        self._msg_lbl.config(fg=config.COLOR_RED_BRIGHT)
        self._msg_var.set(f"✗  {msg}")

    def _reset(self):
        self._uname_var.set("")
        self._pwd_var.set("")
        self._msg_var.set("")
        self._set_waiting(False)

    def focus_entry(self):
        self._uname_ent.focus_set()

