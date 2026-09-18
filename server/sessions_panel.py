# ============================================================
#  AZ Cafe - Live Sessions panel
#  Every running/held session with a live countdown, plus the
#  money actions the counter actually needs (stop, add time,
#  force-close a stale row).
#
#  Fixed here: the panel used to crash with
#  "AttributeError: 'sqlite3.Row' object has no attribute 'get'"
#  the moment any session was active.
# ============================================================

import tkinter as tk
from tkinter import messagebox, ttk

import config
import database as db

COLUMNS = [("PC", 120), ("Customer", 170), ("Started", 130), ("Booked", 90),
           ("Remaining", 110), ("Charge", 100), ("Payment", 100), ("State", 110)]


class SessionsPanel(tk.Frame):

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app = app
        self._rows = {}
        self._build_ui()
        self.refresh()
        self._auto_refresh()

    # ── UI ──────────────────────────────────────────────────
    def _build_ui(self):
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=config.COLOR_RED, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  LIVE SESSIONS", font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        button_cfg = dict(font=("Segoe UI", 8, "bold"), bg=config.COLOR_BG3,
                          fg=config.COLOR_TEXT, relief=tk.FLAT, padx=10, pady=4,
                          cursor="hand2", bd=0,
                          activebackground=config.COLOR_RED,
                          activeforeground=config.COLOR_TEXT)
        tk.Button(bar, text="Refresh", command=self.refresh, **button_cfg).pack(side=tk.RIGHT, padx=6)
        tk.Button(bar, text="⏹ Stop session", command=self._stop_selected,
                  **button_cfg).pack(side=tk.RIGHT, padx=6)
        tk.Button(bar, text="⏱ Add time", command=self._add_time_selected,
                  **button_cfg).pack(side=tk.RIGHT, padx=6)
        tk.Button(bar, text="🧹 Force close", command=self._force_close_selected,
                  **button_cfg).pack(side=tk.RIGHT, padx=6)

        self._summary = tk.Label(bar, text="", font=("Segoe UI", 8),
                                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)
        self._summary.pack(side=tk.RIGHT, padx=12)

        container = tk.Frame(self, bg=config.COLOR_BG, padx=16, pady=14)
        container.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure("Sessions.Treeview", background=config.COLOR_BG,
                        foreground=config.COLOR_TEXT,
                        fieldbackground=config.COLOR_BG, borderwidth=0, rowheight=28)
        style.map("Sessions.Treeview", background=[("selected", config.COLOR_RED)])
        style.configure("Sessions.Treeview.Heading", background=config.COLOR_BG3,
                        foreground=config.COLOR_TEXT_DIM,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)

        self.tree = ttk.Treeview(container, columns=[c[0] for c in COLUMNS],
                                 show="headings", style="Sessions.Treeview")
        for title, width in COLUMNS:
            self.tree.heading(title, text=title)
            self.tree.column(title, width=width, anchor=tk.W)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._empty = tk.Label(container, text="No sessions running.",
                               font=("Segoe UI", 10), fg=config.COLOR_TEXT_DIM,
                               bg=config.COLOR_BG)

    # ── data ────────────────────────────────────────────────
    def _auto_refresh(self):
        if not self.winfo_exists():
            return
        self.refresh()
        self.after(3000, self._auto_refresh)

    def _live_remaining(self, pc_name: str, session: dict):
        server = getattr(self.app, "server", None)
        if server:
            client = server.get_clients_snapshot().get(pc_name)
            if client and client.session_id == session["id"]:
                return client.remaining_secs, client.status
        return int(session.get("remaining_secs") or 0), session.get("status", "")

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows.clear()

        sessions = db.get_open_sessions_all()
        names = {p["pc_name"]: (p.get("display_name") or p["pc_name"])
                 for p in db.get_all_pcs()}
        open_amount = 0.0

        for session in sessions:
            remaining, state = self._live_remaining(session["pc_name"], session)
            remaining = max(0, remaining)
            hours, rest = divmod(remaining, 3600)
            minutes, seconds = divmod(rest, 60)

            user = (session.get("guest_name")
                    or self._member_name(session.get("member_id"))
                    or "Guest")
            amount = float(session.get("amount_charged") or 0)
            open_amount += amount

            item = self.tree.insert("", tk.END, values=(
                names.get(session["pc_name"], session["pc_name"]),
                user,
                (session.get("start_time") or "")[11:16],
                f"{session.get('duration_mins', 0)} min",
                f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                f"{config.CURRENCY} {amount:.0f}",
                str(session.get("payment_type", "cash")).title(),
                "PAUSED" if session.get("paused") else str(state).upper(),
            ))
            self._rows[item] = session

        if not sessions:
            self._empty.pack()
        else:
            self._empty.pack_forget()
        self._summary.config(
            text=f"{len(sessions)} open · {config.CURRENCY} {open_amount:.0f} prepaid")

    @staticmethod
    def _member_name(member_id):
        if not member_id:
            return None
        member = db.get_member_by_id(member_id)
        return member["name"] if member else f"Member #{member_id}"

    def _selected_session(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Sessions", "Select a session first.", parent=self)
            return None, None
        item = selection[0]
        return self._rows.get(item), item

    # ── actions ─────────────────────────────────────────────
    def _stop_selected(self):
        session, _ = self._selected_session()
        if not session:
            return
        server = getattr(self.app, "server", None)
        if not server:
            return
        if not messagebox.askyesno(
                "Stop session",
                f"Stop the session on {session['pc_name']}?\n"
                "The PC is locked and the customer is charged for time used.",
                parent=self):
            return
        result = server.stop_session(session["pc_name"])
        if result.get("ok"):
            self.app.set_status(f"Stopped {session['pc_name']} — charged "
                                f"{config.CURRENCY} {result['charged']:.0f}")
            self.refresh()
            self.app.refresh_revenue()
        else:
            messagebox.showwarning("Stop session", result.get("error", ""), parent=self)

    def _add_time_selected(self):
        session, _ = self._selected_session()
        if not session:
            return
        from tkinter import simpledialog
        minutes = simpledialog.askinteger(
            "Add time", f"Minutes to add on {session['pc_name']}?",
            minvalue=1, maxvalue=600, parent=self)
        if not minutes:
            return
        from server.server_core import implied_rate
        amount = round((minutes / 60.0) * implied_rate(session), 2)
        server = getattr(self.app, "server", None)
        result = server.add_time(session["pc_name"], minutes, amount)
        if result.get("ok"):
            self.app.set_status(f"+{minutes} min on {session['pc_name']} "
                                f"({config.CURRENCY} {amount:.0f})")
            self.refresh()
        else:
            messagebox.showwarning("Add time", result.get("error", ""), parent=self)

    def _force_close_selected(self):
        session, _ = self._selected_session()
        if not session:
            return
        server = getattr(self.app, "server", None)
        if not messagebox.askyesno(
                "Force close",
                f"Close the session on {session['pc_name']} without a connected PC?\n"
                "Prepaid money for the booking is kept.", parent=self):
            return
        result = server.force_close_session(session["pc_name"], keep_prepaid=True)
        if result.get("ok"):
            self.app.set_status(f"Force-closed {session['pc_name']}")
            self.refresh()
            self.app.refresh_revenue()
        else:
            messagebox.showwarning("Force close", result.get("error", ""), parent=self)
