# ============================================================
#  AZ Cafe - Admin Application
#  Main window, top bar, status bar, navigation
# ============================================================

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
import sys
import os
import queue
from datetime import datetime
from PIL import Image, ImageTk

# Add parent directory to path so we can import shared modules
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
import config
import database as db

# Dashboard imported lazily to avoid circular import issues
_Dashboard = None
def _get_dashboard_class():
    global _Dashboard
    if _Dashboard is None:
        from server.dashboard import Dashboard
        _Dashboard = Dashboard
    return _Dashboard

# ── Constants ────────────────────────────────────────────────
WIN_MIN_W = 1100
WIN_MIN_H = 660
TOPBAR_H  = 64
STATBAR_H = 30
SIDEBAR_W = 180


class AdminApp(tk.Tk):
    """
    Root window for AZ Cafe Admin.
    Hosts: TopBar | Sidebar | Main content area | StatusBar
    """

    def __init__(self):
        super().__init__()

        db.init_db()

        # ── Thread-safe UI updates ───────────────────────────
        # Server threads never touch Tk directly; they post callables
        # here and the main loop drains them (~50 ms).
        self._ui_queue = queue.Queue()
        self._drain_ui_queue()

        # ── Window setup ─────────────────────────────────────
        self.title(f"{config.APP_NAME}  v{config.APP_VERSION}  —  Admin Panel")
        self.configure(bg=config.COLOR_BG)
        self.minsize(WIN_MIN_W, WIN_MIN_H)
        self.geometry("1280x720")

        # Remove default titlebar decorations on Windows and add custom
        # Keep standard titlebar for now — full custom chrome in Phase 7
        self._set_icon()

        # ── Fonts ────────────────────────────────────────────
        self._load_fonts()

        # ── State vars ───────────────────────────────────────
        self.active_pcs   = tk.IntVar(value=0)
        self.total_pcs    = tk.IntVar(value=0)
        self.today_rev    = tk.DoubleVar(value=0.0)
        self.today_sess   = tk.IntVar(value=0)
        self.clock_var    = tk.StringVar(value="")
        self.status_msg   = tk.StringVar(value="Ready")

        # Reference to server (injected after server starts)
        self.server    = None
        self.dashboard = None

        # ── Build UI ─────────────────────────────────────────
        self._build_topbar()
        self._build_body()
        self._build_statusbar()

        # ── Start clock + stats refresh ──────────────────────
        self._tick_clock()
        self._refresh_stats()

        # ── Handle close ─────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Icon ─────────────────────────────────────────────────

    def _set_icon(self):
        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "logo.png"
        )
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((32, 32), Image.LANCZOS)
                self._icon_img = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._icon_img)
            except Exception:
                pass

    # ── Fonts ─────────────────────────────────────────────────

    def _load_fonts(self):
        self.font_title   = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.font_nav     = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_stat_v  = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.font_stat_l  = tkfont.Font(family="Segoe UI", size=8)
        self.font_clock   = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.font_status  = tkfont.Font(family="Segoe UI", size=9)
        self.font_body    = tkfont.Font(family="Segoe UI", size=10)

    # ── Top Bar ──────────────────────────────────────────────

    def _build_topbar(self):
        """
        Top bar layout:
        [Logo | App Name]   [Stats: Active | Total | Revenue | Sessions]   [Clock]
        """
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=TOPBAR_H)
        bar.pack(side=tk.TOP, fill=tk.X)
        bar.pack_propagate(False)

        # Thin red accent line at bottom of topbar
        accent = tk.Frame(self, bg=config.COLOR_RED, height=2)
        accent.pack(side=tk.TOP, fill=tk.X)

        # ── Left: Logo + Name ────────────────────────────────
        left = tk.Frame(bar, bg=config.COLOR_BG2)
        left.pack(side=tk.LEFT, padx=12, pady=6)

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "logo.png"
        )
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).resize((44, 44), Image.LANCZOS)
                self._topbar_logo = ImageTk.PhotoImage(img)
                tk.Label(
                    left, image=self._topbar_logo,
                    bg=config.COLOR_BG2
                ).pack(side=tk.LEFT, padx=(0, 8))
            except Exception:
                pass

        name_frame = tk.Frame(left, bg=config.COLOR_BG2)
        name_frame.pack(side=tk.LEFT)

        tk.Label(
            name_frame, text=config.APP_NAME,
            font=self.font_title,
            fg=config.COLOR_RED, bg=config.COLOR_BG2
        ).pack(anchor="w")

        tk.Label(
            name_frame, text="Management System",
            font=self.font_status,
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2
        ).pack(anchor="w")

        # ── Center: Stats ────────────────────────────────────
        center = tk.Frame(bar, bg=config.COLOR_BG2)
        center.pack(side=tk.LEFT, expand=True)

        stats = [
            ("ACTIVE PCs",    self.active_pcs,  config.COLOR_GREEN,      "int"),
            ("TOTAL PCs",     self.total_pcs,   config.COLOR_TEXT,       "int"),
            ("TODAY REVENUE", self.today_rev,   config.COLOR_RED_BRIGHT, "money"),
            ("SESSIONS TODAY",self.today_sess,  config.COLOR_YELLOW,     "int"),
        ]

        for label, var, color, fmt in stats:
            self._stat_card(center, label, var, color, fmt)

        # ── Right: Clock ─────────────────────────────────────
        right = tk.Frame(bar, bg=config.COLOR_BG2)
        right.pack(side=tk.RIGHT, padx=16)

        tk.Label(
            right, textvariable=self.clock_var,
            font=self.font_clock,
            fg=config.COLOR_TEXT, bg=config.COLOR_BG2
        ).pack(anchor="e")

        tk.Label(
            right, text="SERVER ONLINE",
            font=self.font_stat_l,
            fg=config.COLOR_GREEN, bg=config.COLOR_BG2
        ).pack(anchor="e")

    def _stat_card(self, parent, label, var, color, fmt):
        """A single stat block in the top bar."""
        card = tk.Frame(parent, bg=config.COLOR_BG3,
                        padx=16, pady=4,
                        relief=tk.FLAT)
        card.pack(side=tk.LEFT, padx=8, pady=10, ipadx=4)

        # Value display — dynamically formatted
        val_lbl = tk.Label(
            card, text="0",
            font=self.font_stat_v,
            fg=color, bg=config.COLOR_BG3
        )
        val_lbl.pack()

        tk.Label(
            card, text=label,
            font=self.font_stat_l,
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG3
        ).pack()

        def _update(*_):
            raw = var.get()
            if fmt == "money":
                val_lbl.config(text=f"{config.CURRENCY} {raw:,.0f}")
            else:
                val_lbl.config(text=str(raw))

        var.trace_add("write", _update)
        _update()

    # ── Body (Sidebar + Content) ──────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=config.COLOR_BG)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._build_sidebar(body)

        # Content area — dashboard will be injected here in 1C
        self.content_frame = tk.Frame(body, bg=config.COLOR_BG)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Placeholder label until dashboard loads
        self._placeholder = tk.Label(
            self.content_frame,
            text="Loading dashboard...",
            font=self.font_body,
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── Sidebar ───────────────────────────────────────────────

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(
            parent, bg=config.COLOR_BG2,
            width=SIDEBAR_W
        )
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # Red accent line on right side of sidebar
        tk.Frame(sidebar, bg=config.COLOR_RED, width=2).pack(
            side=tk.RIGHT, fill=tk.Y
        )

        inner = tk.Frame(sidebar, bg=config.COLOR_BG2)
        inner.pack(fill=tk.BOTH, expand=True)

        nav_items = [
            ("🖥️  Dashboard",   self._show_dashboard),
            ("👥  Members",     self._show_members),
            ("📋  Sessions",    self._show_sessions),
            ("💰  Reports",     self._show_reports),
            ("🏷️  Pricing",    self._show_pricing),
            ("⚙️  Settings",   self._show_settings),
        ]

        tk.Frame(inner, bg=config.COLOR_BG2, height=12).pack()

        self._nav_buttons = {}
        self._active_nav  = None

        for label, cmd in nav_items:
            btn = self._nav_button(inner, label, cmd)
            self._nav_buttons[label] = btn

        # Bottom: version
        tk.Label(
            inner,
            text=f"v{config.APP_VERSION}",
            font=self.font_stat_l,
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        ).pack(side=tk.BOTTOM, pady=8)

    def _nav_button(self, parent, label, command):
        """Sidebar navigation button with active/hover states."""
        btn = tk.Label(
            parent, text=label,
            font=self.font_nav,
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2,
            anchor="w", padx=20,
            cursor="hand2", height=2
        )
        btn.pack(fill=tk.X, pady=1)

        def _on_click(e=None):
            self._set_active_nav(label)
            command()

        def _on_enter(e):
            if self._active_nav != label:
                btn.config(fg=config.COLOR_TEXT, bg=config.COLOR_BG3)

        def _on_leave(e):
            if self._active_nav != label:
                btn.config(fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)

        btn.bind("<Button-1>", _on_click)
        btn.bind("<Enter>",    _on_enter)
        btn.bind("<Leave>",    _on_leave)
        return btn

    def _set_active_nav(self, label):
        # Reset previous
        if self._active_nav and self._active_nav in self._nav_buttons:
            prev = self._nav_buttons[self._active_nav]
            prev.config(fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)

        # Set new active
        self._active_nav = label
        if label in self._nav_buttons:
            self._nav_buttons[label].config(
                fg=config.COLOR_RED_BRIGHT,
                bg=config.COLOR_BG3
            )

    # ── Status Bar ────────────────────────────────────────────

    def _build_statusbar(self):
        # Thin red line above statusbar
        tk.Frame(self, bg=config.COLOR_RED, height=1).pack(
            side=tk.BOTTOM, fill=tk.X
        )

        bar = tk.Frame(self, bg=config.COLOR_BG2, height=STATBAR_H)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)

        # Left: status message
        tk.Label(
            bar, textvariable=self.status_msg,
            font=self.font_status,
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2,
            anchor="w", padx=10
        ).pack(side=tk.LEFT, fill=tk.Y)

        # Right: server info
        tk.Label(
            bar,
            text=f"Port: {config.SERVER_PORT}   |   AZ Cafe Admin",
            font=self.font_status,
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2,
            padx=10
        ).pack(side=tk.RIGHT, fill=tk.Y)

    # ── Navigation targets (stubs — filled in later phases) ──

    def _show_dashboard(self):
        self.set_status("Dashboard")
        self._clear_content()
        from server.dashboard import Dashboard
        self.dashboard = Dashboard(
            self.content_frame,
            server=self.server,
            app=self
        )
        self.dashboard.pack(fill=tk.BOTH, expand=True)

    def _show_members(self):
        self.set_status("Members")
        self._clear_content()
        from server.members_panel import MembersPanel
        panel = MembersPanel(self.content_frame, app=self)
        panel.pack(fill=tk.BOTH, expand=True)

    def _show_sessions(self):
        self.set_status("Active Sessions")
        self._clear_content()
        from server.sessions_panel import SessionsPanel
        panel = SessionsPanel(self.content_frame, app=self)
        panel.pack(fill=tk.BOTH, expand=True)

    def _show_reports(self):
        self.set_status("Reports")
        self._clear_content()
        from server.reports_panel import ReportsPanel
        panel = ReportsPanel(self.content_frame, app=self)
        panel.pack(fill=tk.BOTH, expand=True)

    def _show_pricing(self):
        self.set_status("Pricing & Packages")
        self._clear_content()
        from server.pricing_panel import PricingPanel
        panel = PricingPanel(self.content_frame, app=self)
        panel.pack(fill=tk.BOTH, expand=True)

    def _show_settings(self):
        self.set_status("Settings")
        self._clear_content()
        from server.settings_panel import SettingsPanel
        panel = SettingsPanel(self.content_frame, app=self)
        panel.pack(fill=tk.BOTH, expand=True)

    def _coming_soon(self, text):
        tk.Label(
            self.content_frame,
            text=f"⚙  {text}",
            font=self.font_body,
            fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG
        ).place(relx=0.5, rely=0.5, anchor="center")

    # ── Thread-safe UI plumbing ───────────────────────────────

    def post_to_ui(self, func, *args, **kwargs):
        """Queue a callable to run on the Tk main thread."""
        self._ui_queue.put((func, args, kwargs))

    def _drain_ui_queue(self):
        while True:
            try:
                func, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args, **kwargs)
            except Exception as exc:                           # noqa: BLE001
                try:
                    self.set_status(f"UI error: {exc}")
                except Exception:                              # noqa: BLE001
                    pass
        self.after(50, self._drain_ui_queue)

    # ── Server events ─────────────────────────────────────────

    def on_session_event(self, kind: str, payload: dict):
        """Called from the server thread for session lifecycle events."""
        self.post_to_ui(self._handle_session_event, kind, dict(payload or {}))

    def _handle_session_event(self, kind: str, payload: dict):
        if kind == "settled":
            self.refresh_revenue()
            dashboard = getattr(self, "dashboard", None)
            if dashboard is not None:
                dashboard.show_receipt(payload)
            if dashboard is not None:
                dashboard.on_pc_update(self.server.get_clients_snapshot()
                                       if self.server else {})
        elif kind in ("suspended", "recovered", "started", "add_time"):
            self.refresh_revenue()

    # ── Public helpers ────────────────────────────────────────

    def set_status(self, msg: str):
        if str(msg).startswith("SERVER FAILED"):
            messagebox.showerror("Server error", msg)
        return self._set_status(msg)

    def _set_status(self, msg: str):
        self.status_msg.set(f"●  {msg}")

    def _clear_content(self):
        for w in self.content_frame.winfo_children():
            w.destroy()

    def update_stats(self, active: int, total: int):
        """Called by server thread when PC count changes."""
        self.active_pcs.set(active)
        self.total_pcs.set(total)

    def refresh_revenue(self):
        """6A — one canonical revenue number (settled sessions only)."""
        self.today_rev.set(db.get_today_revenue())
        self.today_sess.set(db.get_today_sessions())

    # ── Clock ─────────────────────────────────────────────────

    def _tick_clock(self):
        now = datetime.now().strftime("%A  %d %b %Y   %I:%M:%S %p")
        self.clock_var.set(now)
        self.after(1000, self._tick_clock)

    # ── Stats refresh ─────────────────────────────────────────

    def _refresh_stats(self):
        self.refresh_revenue()
        if self.server:
            try:
                self.dashboard_update_from_server()
            except Exception:                                  # noqa: BLE001
                pass
        self.after(5_000, self._refresh_stats)

    def dashboard_update_from_server(self):
        """Keep the grid honest even when no client event arrived."""
        if self.server and getattr(self, "dashboard", None) is not None:
            self.dashboard.on_pc_update(self.server.get_clients_snapshot())

    # ── Close ─────────────────────────────────────────────────

    def _on_close(self):
        if self.server:
            self.server.stop()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────

def run():
    app = AdminApp()
    # Auto-navigate to dashboard on startup
    app._set_active_nav("🖥️  Dashboard")
    app._show_dashboard()
    app.set_status("Server starting...")
    app.mainloop()


if __name__ == "__main__":
    run()
