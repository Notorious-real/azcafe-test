import tkinter as tk
from tkinter import ttk
import config
import database as db

class SessionsPanel(tk.Frame):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app = app
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # Toolbar
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=config.COLOR_RED, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  ACTIVE SESSIONS", font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        tk.Button(bar, text="Refresh", command=self._refresh,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 8),
                  relief=tk.FLAT, padx=10, pady=4, cursor="hand2", bd=0).pack(side=tk.RIGHT, padx=10)

        # Content
        container = tk.Frame(self, bg=config.COLOR_BG, padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        cols = ["PC Name", "User", "Start Time", "Duration (mins)", "Charge", "Payment", "Status"]
        self.tree = ttk.Treeview(container, columns=cols, show="headings", style="Custom.Treeview")
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Custom.Treeview", background=config.COLOR_BG, foreground=config.COLOR_TEXT,
                        fieldbackground=config.COLOR_BG, borderwidth=0, rowheight=30)
        style.map("Custom.Treeview", background=[("selected", config.COLOR_RED)])
        style.configure("Custom.Treeview.Heading", background=config.COLOR_BG3, foreground=config.COLOR_TEXT_DIM,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)

        widths = [100, 150, 150, 100, 100, 100, 100]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=tk.W)
        
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        
        conn = db.get_connection()
        rows = conn.execute("SELECT * FROM sessions WHERE status='active' ORDER BY start_time DESC").fetchall()
        conn.close()

        for s in rows:
            user = s.get("guest_name") or f"Member #{s.get('member_id','?')}"
            time_str = s["start_time"][11:19] if s["start_time"] else "—"
            charge = f"{config.CURRENCY} {s['amount_charged']:.0f}"
            self.tree.insert("", tk.END, values=(
                s["pc_name"], user, time_str, s["duration_mins"], charge, s["payment_type"].capitalize(), s["status"].upper()
            ))
