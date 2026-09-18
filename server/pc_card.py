# ============================================================
#  AZ Cafe - PC Card Widget
#  Individual PC card shown on the dashboard grid
# ============================================================

import tkinter as tk
import sys
import os

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
import config

CARD_W = 160
CARD_H = 140


class PCCard(tk.Frame):
    """
    One PC card on the dashboard.
    Shows: PC name, status, user, remaining time, indicator dot.
    Right-click opens context menu.
    Supports drag to reposition.
    """

    STATUS_COLORS = {
        config.STATUS_FREE:    config.COLOR_TEXT_DIM,
        config.STATUS_ACTIVE:  config.COLOR_GREEN,
        config.STATUS_LOCKED:  config.COLOR_RED,
        config.STATUS_OFFLINE: "#444444",
        config.STATUS_PAUSED:  config.COLOR_YELLOW,
    }

    STATUS_BG = {
        config.STATUS_FREE:    config.COLOR_BG2,
        config.STATUS_ACTIVE:  "#0d1f0d",
        config.STATUS_LOCKED:  "#1a0000",
        config.STATUS_OFFLINE: "#111111",
        config.STATUS_PAUSED:  "#1a1400",
    }

    def __init__(self, parent, pc_name: str, on_command, **kwargs):
        super().__init__(
            parent,
            bg=config.COLOR_BG2,
            width=CARD_W, height=CARD_H,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            **kwargs
        )
        self.pack_propagate(False)

        self.pc_name    = pc_name
        self.on_command = on_command   # callback(pc_name, command, **kwargs)

        self.status          = config.STATUS_OFFLINE
        self.session_user    = ""
        self.remaining_secs  = 0
        self.paused          = False
        self.suspended       = False
        self.display_name    = pc_name

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._bind_events()

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top strip: colored status bar ────────────────────
        self._top_strip = tk.Frame(self, height=4, bg=config.COLOR_BORDER)
        self._top_strip.pack(fill=tk.X)

        # ── Status dot + PC name ─────────────────────────────
        header = tk.Frame(self, bg=config.COLOR_BG2)
        header.pack(fill=tk.X, padx=8, pady=(6, 0))

        self._dot = tk.Label(
            header, text="●", font=("Segoe UI", 10),
            fg="#444444", bg=config.COLOR_BG2
        )
        self._dot.pack(side=tk.LEFT)

        self._name_lbl = tk.Label(
            header,
            text=self.pc_name,
            font=("Segoe UI", 9, "bold"),
            fg=config.COLOR_TEXT,
            bg=config.COLOR_BG2,
            anchor="w"
        )
        self._name_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # ── Status text ───────────────────────────────────────
        self._status_lbl = tk.Label(
            self,
            text="OFFLINE",
            font=("Segoe UI", 8, "bold"),
            fg="#444444",
            bg=config.COLOR_BG2
        )
        self._status_lbl.pack(pady=(4, 0))

        # ── User name ─────────────────────────────────────────
        self._user_lbl = tk.Label(
            self,
            text="—",
            font=("Segoe UI", 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        )
        self._user_lbl.pack()

        # ── Timer ─────────────────────────────────────────────
        self._timer_lbl = tk.Label(
            self,
            text="00:00:00",
            font=("Segoe UI", 16, "bold"),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG2
        )
        self._timer_lbl.pack(pady=(2, 0))

        # ── Bottom hint ───────────────────────────────────────
        self._hint_lbl = tk.Label(
            self,
            text="Right-click for options",
            font=("Segoe UI", 7),
            fg="#333333",
            bg=config.COLOR_BG2
        )
        self._hint_lbl.pack(pady=(0, 4))

    # ── Events ────────────────────────────────────────────────

    def _bind_events(self):
        widgets = [
            self, self._dot, self._name_lbl,
            self._status_lbl, self._user_lbl,
            self._timer_lbl, self._hint_lbl,
            self._top_strip
        ]
        for w in widgets:
            w.bind("<Button-3>",        self._show_context_menu)
            w.bind("<Double-Button-1>", self._on_double_click)
            w.bind("<Enter>",           self._on_enter)
            w.bind("<Leave>",           self._on_leave)
            # Drag
            w.bind("<ButtonPress-1>",   self._drag_start)
            w.bind("<B1-Motion>",       self._drag_motion)
            w.bind("<ButtonRelease-1>", self._drag_end)

    def _on_enter(self, e=None):
        if self.status != config.STATUS_OFFLINE:
            self.config(highlightbackground=config.COLOR_RED_DARK)
            self._hint_lbl.config(fg=config.COLOR_TEXT_DIM)

    def _on_leave(self, e=None):
        self.config(highlightbackground=config.COLOR_BORDER)
        self._hint_lbl.config(fg="#333333")

    # ── Drag ──────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y
        self.lift()

    def _drag_motion(self, e):
        dx = e.x - self._drag_x
        dy = e.y - self._drag_y
        x  = self.winfo_x() + dx
        y  = self.winfo_y() + dy
        self.place(x=x, y=y)

    def _drag_end(self, e):
        # Notify parent dashboard to snap to grid and save position
        if hasattr(self.master, "on_card_dropped"):
            self.master.on_card_dropped(self)

    # ── Context Menu ──────────────────────────────────────────

    def _show_context_menu(self, e):
        menu = tk.Menu(
            self, tearoff=0,
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT,
            activebackground=config.COLOR_RED,
            activeforeground=config.COLOR_TEXT,
            font=("Segoe UI", 9),
            bd=0, relief=tk.FLAT
        )

        st = self.status

        # ── Session commands ──────────────────────────────────
        if st == config.STATUS_FREE:
            menu.add_command(
                label="▶  Start Session",
                command=lambda: self.on_command(self.pc_name, "start_session")
            )
        elif st == config.STATUS_ACTIVE:
            menu.add_command(
                label="⏸  Pause Session",
                command=lambda: self.on_command(self.pc_name, "pause_session")
            )
            menu.add_command(
                label="⏹  Stop Session",
                command=lambda: self.on_command(self.pc_name, "stop_session")
            )
            menu.add_command(
                label="⏱  Add Time",
                command=lambda: self.on_command(self.pc_name, "add_time")
            )
        elif st == config.STATUS_PAUSED:
            menu.add_command(
                label="▶  Resume Session",
                command=lambda: self.on_command(self.pc_name, "resume_session")
            )
            menu.add_command(
                label="⏹  Stop Session",
                command=lambda: self.on_command(self.pc_name, "stop_session")
            )

        menu.add_separator()

        # ── Lock / Unlock ─────────────────────────────────────
        if st == config.STATUS_LOCKED:
            menu.add_command(
                label="🔓  Unlock PC",
                command=lambda: self.on_command(self.pc_name, "unlock")
            )
        else:
            menu.add_command(
                label="🔒  Lock PC",
                command=lambda: self.on_command(self.pc_name, "lock")
            )

        menu.add_separator()

        # ── Messaging ─────────────────────────────────────────
        menu.add_command(
            label="💬  Send Message",
            command=lambda: self.on_command(self.pc_name, "send_message")
        )

        menu.add_separator()

        # ── Power ─────────────────────────────────────────────
        menu.add_command(
            label="🔄  Restart PC",
            command=lambda: self.on_command(self.pc_name, "restart")
        )
        menu.add_command(
            label="⏻   Shutdown PC",
            command=lambda: self.on_command(self.pc_name, "shutdown")
        )

        menu.add_separator()

        # ── Card options ──────────────────────────────────────
        menu.add_command(
            label="🏷️  Assign Plan",
            command=lambda: self.on_command(self.pc_name, "assign_plan")
        )
        menu.add_command(
            label="📁  Change Group",
            command=lambda: self.on_command(self.pc_name, "change_group")
        )
        menu.add_command(
            label="✏️  Rename PC",
            command=lambda: self.on_command(self.pc_name, "rename")
        )
        menu.add_command(
            label="🧹  Force close stale session",
            command=lambda: self.on_command(self.pc_name, "force_close")
        )

        # Offline cards keep the maintenance options (rename, groups, plan,
        # force-close) but lose the live session/power commands.
        if st == config.STATUS_OFFLINE:
            for i in range(menu.index("end") + 1):
                try:
                    menu.entryconfig(i, state=tk.DISABLED)
                except tk.TclError:
                    pass
            if self.suspended:
                for index, opts in (
                        (menu.index("🧹  Force close stale session"), {}),
                        ):
                    if index is not None:
                        try:
                            menu.entryconfig(index, state=tk.NORMAL)
                        except tk.TclError:
                            pass

        menu.tk_popup(e.x_root, e.y_root)

    def _on_double_click(self, e):
        """Double-click: start session if free, show info if active."""
        if self.status == config.STATUS_FREE:
            self.on_command(self.pc_name, "start_session")
        elif self.status == config.STATUS_ACTIVE:
            self.on_command(self.pc_name, "session_info")

    # ── Update ────────────────────────────────────────────────

    def set_display_name(self, name: str):
        self.display_name = name or self.pc_name
        self._name_lbl.config(text=self.display_name)

    def update_data(self, status: str, user: str = "",
                    remaining_secs: int = 0, paused: bool = False,
                    suspended: bool = False):
        """Called by dashboard when the server sends an update."""
        self.status         = status
        self.session_user   = user
        self.remaining_secs = remaining_secs
        self.paused         = paused
        self.suspended      = suspended

        color  = self.STATUS_COLORS.get(status, "#444444")
        bg     = self.STATUS_BG.get(status, config.COLOR_BG2)

        # Update background
        self.config(bg=bg)
        for w in self.winfo_children():
            try:
                w.config(bg=bg)
            except tk.TclError:
                pass

        # Top strip color
        self._top_strip.config(bg=color)

        # Dot color
        self._dot.config(fg=color, bg=bg)

        # Status label — a PC that dropped mid-session says so
        label = status
        status_color = color
        if status == config.STATUS_OFFLINE and suspended:
            label = "SESSION HELD"
            status_color = config.COLOR_YELLOW
        self._status_lbl.config(text=label, fg=status_color, bg=bg)

        # User
        self._user_lbl.config(
            text=user if user else "—",
            fg=config.COLOR_TEXT if user else config.COLOR_TEXT_DIM,
            bg=bg
        )

        # Timer color
        timer_color = color if status == config.STATUS_ACTIVE else config.COLOR_TEXT_DIM
        if remaining_secs > 0 and remaining_secs <= 300:   # last 5 mins
            timer_color = config.COLOR_RED_BRIGHT
        self._timer_lbl.config(fg=timer_color, bg=bg)

        # Highlight border
        border = color if status != config.STATUS_OFFLINE else config.COLOR_BORDER
        self.config(highlightbackground=border)

        # Update timer display
        self._update_timer_display()

    def tick(self):
        """
        Called every second by the dashboard. Only refreshes the hints —
        the countdown itself comes from the server (one clock, one truth).
        """
        if self.status == config.STATUS_ACTIVE and not self.paused:
            self._update_timer_display()

            secs = self.remaining_secs
            if 0 < secs <= 60:
                # Last minute — flash between red and dark
                self._timer_lbl.config(fg=config.COLOR_RED_BRIGHT)
                self._hint_lbl.config(
                    text="⚠ LAST MINUTE",
                    fg=config.COLOR_RED_BRIGHT
                )
            elif 0 < secs <= 300:
                # Last 5 minutes — solid red
                self._timer_lbl.config(fg=config.COLOR_RED_BRIGHT)
                self._hint_lbl.config(
                    text="⚠ Time running low",
                    fg=config.COLOR_YELLOW
                )
            else:
                self._hint_lbl.config(
                    text="Right-click for options",
                    fg="#333333"
                )
        elif self.status == config.STATUS_OFFLINE and self.suspended:
            self._hint_lbl.config(
                text="Paid time held — resumes on reconnect",
                fg=config.COLOR_YELLOW
            )

    def _update_timer_display(self):
        secs  = max(0, self.remaining_secs)
        h     = secs // 3600
        m     = (secs % 3600) // 60
        s     = secs % 60
        self._timer_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}")
