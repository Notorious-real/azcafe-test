# ============================================================
#  AZ Cafe - Reports Panel (Phase 2E)
#  Daily report, session log, revenue summary, per-PC stats
# ============================================================

import tkinter as tk
from tkinter import messagebox
import sys
import os
from datetime import datetime, timedelta

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config
import database as db


class ReportsPanel(tk.Frame):
    """
    Reports panel with tabs:
    - Today
    - Daily (pick a date)
    - Per PC
    - Top Members
    """

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app = app
        self._active_tab = None
        self._build_ui()
        self._show_tab("today")

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_tabs()

        self._content = tk.Frame(self, bg=config.COLOR_BG)
        self._content.pack(fill=tk.BOTH, expand=True)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=config.COLOR_RED,
                 width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  REPORTS",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED,
                 bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        # Export buttons (Phase 6E)
        tk.Button(
            bar, text="📄  Export PDF/HTML",
            command=self._export_html_pdf,
            font=("Segoe UI", 8, "bold"),
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
            relief=tk.FLAT, padx=10, pady=4,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.RIGHT, padx=4, pady=5)

        tk.Button(
            bar, text="📋  Export CSV",
            command=self._export_csv,
            font=("Segoe UI", 8, "bold"),
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
            relief=tk.FLAT, padx=10, pady=4,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.RIGHT, padx=4, pady=5)

    def _build_tabs(self):
        tab_bar = tk.Frame(self, bg=config.COLOR_BG2)
        tab_bar.pack(fill=tk.X)

        self._tab_btns = {}
        tabs = [
            ("today",       "📅  Today"),
            ("daily",       "📆  By Date"),
            ("charts",      "📊  Revenue Chart"),
            ("per_pc",      "🖥️  Per PC"),
            ("top_members", "👥  Top Members"),
        ]
        for key, label in tabs:
            btn = tk.Label(
                tab_bar, text=label,
                font=("Segoe UI", 9),
                fg=config.COLOR_TEXT_DIM,
                bg=config.COLOR_BG2,
                padx=16, pady=8,
                cursor="hand2"
            )
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            self._tab_btns[key] = btn

        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

    def _show_tab(self, key: str):
        # Update tab button styles
        if self._active_tab and self._active_tab in self._tab_btns:
            self._tab_btns[self._active_tab].config(
                fg=config.COLOR_TEXT_DIM,
                bg=config.COLOR_BG2
            )
        self._active_tab = key
        self._tab_btns[key].config(
            fg=config.COLOR_RED_BRIGHT,
            bg=config.COLOR_BG3
        )

        # Clear content
        for w in self._content.winfo_children():
            w.destroy()

        if key == "today":
            self._build_today()
        elif key == "daily":
            self._build_daily()
        elif key == "charts":
            self._build_charts()
        elif key == "per_pc":
            self._build_per_pc()
        elif key == "top_members":
            self._build_top_members()

    # ── Today Tab ─────────────────────────────────────────────

    def _build_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self._build_day_report(self._content, today, "Today's Report")

    def _build_day_report(self, parent, date_str: str, title: str):
        sessions = db.get_sessions_by_date(date_str)
        revenue  = sum(s["amount_charged"] for s in sessions)
        total    = len(sessions)
        active   = sum(1 for s in sessions if s["status"] == "active")

        # ── Summary cards ─────────────────────────────────────
        summary = tk.Frame(parent, bg=config.COLOR_BG, padx=16, pady=12)
        summary.pack(fill=tk.X)

        stats = [
            ("TOTAL REVENUE",  f"{config.CURRENCY} {revenue:.0f}", config.COLOR_RED_BRIGHT),
            ("SESSIONS",       str(total),                         config.COLOR_TEXT),
            ("ACTIVE NOW",     str(active),                        config.COLOR_GREEN),
            ("AVG PER SESSION",
             f"{config.CURRENCY} {revenue/total:.0f}" if total else "—",
             config.COLOR_YELLOW),
        ]
        for label, value, color in stats:
            card = tk.Frame(summary, bg=config.COLOR_BG3,
                            padx=18, pady=10)
            card.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(card, text=value,
                     font=("Segoe UI", 20, "bold"),
                     fg=color, bg=config.COLOR_BG3).pack()
            tk.Label(card, text=label,
                     font=("Segoe UI", 7),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3).pack()

        # ── Title + date ──────────────────────────────────────
        tk.Label(parent, text=f"  {title}  —  {date_str}",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2,
                 anchor="w", pady=6).pack(fill=tk.X)
        tk.Frame(parent, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X)

        # ── Session table ─────────────────────────────────────
        self._build_session_table(parent, sessions)

    def _build_session_table(self, parent, sessions: list):
        # Header
        cols   = ["Time",  "PC",  "Customer", "Duration", "Amount", "Payment", "Status"]
        widths = [120,     80,    140,         80,         80,       80,        70]

        hdr = tk.Frame(parent, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X)
        for col, w in zip(cols, widths):
            tk.Label(hdr, text=col,
                     font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     width=w//8, anchor="w",
                     padx=8, pady=6).pack(side=tk.LEFT)

        # Scrollable rows
        container = tk.Frame(parent, bg=config.COLOR_BG)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=config.COLOR_BG,
                           highlightthickness=0)
        vsb    = tk.Scrollbar(container, orient=tk.VERTICAL,
                              command=canvas.yview,
                              bg=config.COLOR_BG2,
                              troughcolor=config.COLOR_BG,
                              activebackground=config.COLOR_RED)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.config(yscrollcommand=vsb.set)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(
                        int(-1*(e.delta/120)), "units"))

        inner = tk.Frame(canvas, bg=config.COLOR_BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.config(
                       scrollregion=canvas.bbox("all")))

        if not sessions:
            tk.Label(inner,
                     text="No sessions found.",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     pady=30).pack()
            return

        for i, s in enumerate(sessions):
            row_bg = config.COLOR_BG if i % 2 == 0 else config.COLOR_BG2
            row    = tk.Frame(inner, bg=row_bg)
            row.pack(fill=tk.X)

            time_str = s["start_time"][11:16] if s["start_time"] else "—"
            user     = s.get("guest_name") or f"Member #{s.get('member_id','?')}"
            status   = s["status"].upper()
            s_color  = (config.COLOR_GREEN  if status == "ACTIVE"
                        else config.COLOR_TEXT_DIM
                        if status == "COMPLETED" else config.COLOR_YELLOW)

            values = [
                time_str,
                s["pc_name"],
                user,
                f"{s['duration_mins']}m",
                f"{config.CURRENCY} {s['amount_charged']:.0f}",
                s["payment_type"],
                status
            ]
            colors = [config.COLOR_TEXT] * 6 + [s_color]

            for val, w, col in zip(values, widths, colors):
                tk.Label(row, text=val,
                         font=("Segoe UI", 8),
                         fg=col, bg=row_bg,
                         width=w//8, anchor="w",
                         padx=8, pady=5).pack(side=tk.LEFT)

        # Footer total
        total_rev = sum(s["amount_charged"] for s in sessions)
        tk.Frame(parent, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X)
        tk.Label(parent,
                 text=f"  {len(sessions)} sessions   |   "
                      f"Total: {config.CURRENCY} {total_rev:.0f}",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_TEXT,
                 bg=config.COLOR_BG2,
                 anchor="w", pady=6).pack(fill=tk.X)

    # ── Daily Tab ─────────────────────────────────────────────

    def _build_daily(self):
        top = tk.Frame(self._content, bg=config.COLOR_BG2,
                       padx=16, pady=10)
        top.pack(fill=tk.X)

        tk.Label(top, text="Select Date:",
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2).pack(side=tk.LEFT)

        # Simple date entry (YYYY-MM-DD)
        self._date_var = tk.StringVar(
            value=datetime.now().strftime("%Y-%m-%d")
        )
        tk.Entry(top, textvariable=self._date_var,
                 font=("Segoe UI", 10),
                 bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                 insertbackground=config.COLOR_TEXT,
                 relief=tk.FLAT, bd=4,
                 width=14).pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(top, text="Load",
                  command=self._load_daily,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=12, pady=4,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT
                  ).pack(side=tk.LEFT, padx=(8, 0))

        # Quick date buttons
        for label, delta in [("Yesterday", -1), ("Last 7 days", -7)]:
            d = (datetime.now() + timedelta(days=delta)).strftime("%Y-%m-%d")
            tk.Button(top, text=label,
                      command=lambda date=d: self._load_date(date),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 8),
                      relief=tk.FLAT, padx=10, pady=4,
                      cursor="hand2", bd=0,
                      activebackground=config.COLOR_BG2,
                      activeforeground=config.COLOR_TEXT
                      ).pack(side=tk.LEFT, padx=(6, 0))

        # Result area
        self._daily_result = tk.Frame(self._content, bg=config.COLOR_BG)
        self._daily_result.pack(fill=tk.BOTH, expand=True)
        self._load_daily()

    def _load_daily(self):
        date_str = self._date_var.get().strip()
        self._load_date(date_str)

    def _load_date(self, date_str: str):
        self._date_var.set(date_str)
        for w in self._daily_result.winfo_children():
            w.destroy()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            tk.Label(self._daily_result,
                     text="Invalid date format. Use YYYY-MM-DD",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_RED_BRIGHT,
                     bg=config.COLOR_BG,
                     pady=20).pack()
            return
        self._build_day_report(self._daily_result, date_str,
                               "Daily Report")

    # ── Per PC Tab ────────────────────────────────────────────

    def _build_per_pc(self):
        stats = db.get_per_pc_stats()

        if not stats:
            tk.Label(self._content,
                     text="No session data yet.",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     pady=40).pack()
            return

        # Header
        cols   = ["PC Name", "Total Sessions", "Total Time", "Revenue", "Last Used"]
        widths = [160,        120,               100,          120,       160]

        hdr = tk.Frame(self._content, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X)
        for col, w in zip(cols, widths):
            tk.Label(hdr, text=col,
                     font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     width=w//8, anchor="w",
                     padx=8, pady=8).pack(side=tk.LEFT)

        # Rows
        for i, s in enumerate(stats):
            row_bg = config.COLOR_BG if i % 2 == 0 else config.COLOR_BG2
            row    = tk.Frame(self._content, bg=row_bg)
            row.pack(fill=tk.X)

            last = s["last_used"][:10] if s["last_used"] else "Never"
            values = [
                s["pc_name"],
                str(s["total_sessions"]),
                f"{s['total_mins']}m",
                f"{config.CURRENCY} {s['total_revenue']:.0f}",
                last
            ]
            # Highlight top earner
            rev_color = (config.COLOR_RED_BRIGHT
                         if i == 0 else config.COLOR_TEXT)
            colors = ([config.COLOR_TEXT] * 3
                      + [rev_color]
                      + [config.COLOR_TEXT_DIM])

            for val, w, col in zip(values, widths, colors):
                tk.Label(row, text=val,
                         font=("Segoe UI", 9),
                         fg=col, bg=row_bg,
                         width=w//8, anchor="w",
                         padx=8, pady=6).pack(side=tk.LEFT)

    # ── Top Members Tab ───────────────────────────────────────

    def _build_top_members(self):
        members = db.get_top_members()

        if not members:
            tk.Label(self._content,
                     text="No member data yet.",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     pady=40).pack()
            return

        # Header
        cols   = ["Rank", "Member", "Username", "Sessions", "Total Spent", "Balance"]
        widths = [50,      160,      120,         80,         120,           100]

        hdr = tk.Frame(self._content, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X)
        for col, w in zip(cols, widths):
            tk.Label(hdr, text=col,
                     font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     width=w//8, anchor="w",
                     padx=8, pady=8).pack(side=tk.LEFT)

        for i, m in enumerate(members):
            row_bg = config.COLOR_BG if i % 2 == 0 else config.COLOR_BG2
            row    = tk.Frame(self._content, bg=row_bg)
            row.pack(fill=tk.X)

            rank_color = (config.COLOR_RED_BRIGHT if i == 0
                          else config.COLOR_YELLOW if i == 1
                          else config.COLOR_TEXT_DIM)

            values = [
                f"#{i+1}",
                m["name"],
                f"@{m['username']}",
                str(m["session_count"]),
                f"{config.CURRENCY} {m['total_spent']:.0f}",
                f"{config.CURRENCY} {m['balance']:.0f}"
            ]
            colors = ([rank_color]
                      + [config.COLOR_TEXT] * 3
                      + [config.COLOR_RED_BRIGHT,
                         config.COLOR_GREEN])

            for val, w, col in zip(values, widths, colors):
                tk.Label(row, text=val,
                         font=("Segoe UI", 9),
                         fg=col, bg=row_bg,
                         width=w//8, anchor="w",
                         padx=8, pady=6).pack(side=tk.LEFT)

    # ── Revenue Chart Tab (Phase 6C) ──────────────────────────

    def _build_charts(self):
        ctrl = tk.Frame(self._content, bg=config.COLOR_BG, padx=20, pady=10)
        ctrl.pack(fill=tk.X)

        tk.Label(ctrl, text="View:", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT, padx=(0, 6))

        self._chart_mode = tk.StringVar(value="weekly")

        for label, val in [("Past 7 Days", "weekly"), ("Past 30 Days", "monthly_daily"), ("Past 6 Months", "monthly")]:
            tk.Radiobutton(ctrl, text=label, variable=self._chart_mode, value=val,
                           command=self._render_active_chart,
                           bg=config.COLOR_BG, fg=config.COLOR_TEXT,
                           selectcolor=config.COLOR_BG3, activebackground=config.COLOR_BG,
                           font=("Segoe UI", 9), cursor="hand2").pack(side=tk.LEFT, padx=6)

        self._chart_container = tk.Frame(self._content, bg=config.COLOR_BG, padx=20, pady=10)
        self._chart_container.pack(fill=tk.BOTH, expand=True)

        self._render_active_chart()

    def _render_active_chart(self):
        for w in self._chart_container.winfo_children():
            w.destroy()

        mode = self._chart_mode.get()
        now = datetime.now()

        if mode == "weekly":
            start_date = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            raw_data = db.get_daily_revenue_range(start_date, end_date)
            data_dict = {r["day"]: r["revenue"] for r in raw_data}

            # Ensure all 7 days exist
            items = []
            for i in range(7):
                d = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
                d_short = datetime.strptime(d, "%Y-%m-%d").strftime("%a %d")
                items.append((d_short, data_dict.get(d, 0.0)))
            title = f"Past 7 Days Revenue ({start_date} to {end_date})"

        elif mode == "monthly_daily":
            start_date = (now - timedelta(days=29)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            raw_data = db.get_daily_revenue_range(start_date, end_date)
            data_dict = {r["day"]: r["revenue"] for r in raw_data}

            items = []
            for i in range(30):
                d = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
                d_short = datetime.strptime(d, "%Y-%m-%d").strftime("%d %b")
                items.append((d_short, data_dict.get(d, 0.0)))
            title = f"Past 30 Days Daily Revenue"

        else: # monthly
            raw_data = db.get_monthly_revenue_breakdown(6)
            items = [(r["month"], r["revenue"]) for r in raw_data]
            if not items:
                items = [(now.strftime("%Y-%m"), 0.0)]
            title = f"Past 6 Months Revenue"

        total_rev = sum(amt for _, amt in items)
        max_amt = max([amt for _, amt in items] + [100.0])

        # Title & Summary banner
        hdr = tk.Frame(self._chart_container, bg=config.COLOR_BG3, padx=16, pady=10)
        hdr.pack(fill=tk.X, pady=(0, 10))

        tk.Label(hdr, text=title, font=("Segoe UI", 10, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG3).pack(side=tk.LEFT)

        tk.Label(hdr, text=f"Total: {config.CURRENCY} {total_rev:.0f}",
                 font=("Segoe UI", 12, "bold"),
                 fg=config.COLOR_RED_BRIGHT, bg=config.COLOR_BG3).pack(side=tk.RIGHT)

        # Canvas Bar Chart
        canvas_h = 240
        canvas = tk.Canvas(self._chart_container, bg=config.COLOR_BG2, height=canvas_h,
                           highlightthickness=1, highlightbackground=config.COLOR_BORDER)
        canvas.pack(fill=tk.X, expand=True)

        self._draw_bar_chart(canvas, items, max_amt, canvas_h)

    def _draw_bar_chart(self, canvas, items, max_val, height):
        self.update_idletasks()
        c_width = canvas.winfo_width()
        if c_width <= 100:
            c_width = 700

        n = len(items)
        pad_left = 60
        pad_right = 20
        pad_bottom = 35
        pad_top = 25

        plot_w = c_width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        # Grid lines (0%, 50%, 100%)
        for pct, lbl in [(0.0, "0"), (0.5, f"{max_val*0.5:.0f}"), (1.0, f"{max_val:.0f}")]:
            y = height - pad_bottom - (plot_h * pct)
            canvas.create_line(pad_left, y, c_width - pad_right, y, fill=config.COLOR_BG3, dash=(2, 2))
            canvas.create_text(pad_left - 8, y, text=lbl, fill=config.COLOR_TEXT_DIM,
                               font=("Segoe UI", 7), anchor="e")

        bar_slot = plot_w / n
        bar_w = max(4, bar_slot * 0.65)

        for i, (label, val) in enumerate(items):
            x_center = pad_left + (i + 0.5) * bar_slot
            bar_height = (val / max_val) * plot_h if max_val > 0 else 0
            y1 = height - pad_bottom - bar_height
            y2 = height - pad_bottom

            color = config.COLOR_RED if val > 0 else config.COLOR_BG3
            canvas.create_rectangle(x_center - bar_w/2, y1, x_center + bar_w/2, y2,
                                    fill=color, outline="")

            if n <= 12 and val > 0:
                canvas.create_text(x_center, y1 - 8, text=f"{val:.0f}",
                                   fill=config.COLOR_TEXT, font=("Segoe UI", 7, "bold"))

            # X-axis label
            step = 1 if n <= 10 else (3 if n <= 20 else 5)
            if i % step == 0:
                canvas.create_text(x_center, height - pad_bottom + 14, text=label,
                                   fill=config.COLOR_TEXT_DIM, font=("Segoe UI", 7))

    # ── Export CSV ────────────────────────────────────────────

    def _export_csv(self):
        from tkinter import filedialog
        today    = datetime.now().strftime("%Y-%m-%d")
        sessions = db.get_sessions_by_date(today)

        if not sessions:
            messagebox.showinfo("Export", "No sessions today to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"azcafe_report_{today}.csv",
            parent=self
        )
        if not path:
            return

        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "PC", "Customer", "Duration(mins)", "Amount", "Payment", "Status"])
            for s in sessions:
                user = (s.get("guest_name") or f"Member #{s.get('member_id','?')}")
                writer.writerow([
                    s["start_time"][11:16],
                    s["pc_name"],
                    user,
                    s["duration_mins"],
                    f"{s['amount_charged']:.0f}",
                    s["payment_type"],
                    s["status"]
                ])

        messagebox.showinfo("Export", f"Saved to:\n{path}", parent=self)
        self.app.set_status(f"Report exported: {path}")

    # ── Export HTML / Printable PDF (Phase 6E) ────────────────

    def _export_html_pdf(self):
        """
        Phase 6E — Export a clean, styled HTML report with print CSS
        that opens directly in any browser and can be saved as PDF via Ctrl+P.
        """
        from tkinter import filedialog
        import webbrowser

        today = datetime.now().strftime("%Y-%m-%d")
        sessions = db.get_sessions_by_date(today)

        if not sessions:
            messagebox.showinfo("Export", "No sessions found today to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML / Printable PDF", "*.html"), ("All files", "*.*")],
            initialfile=f"azcafe_report_{today}.html",
            parent=self
        )
        if not path:
            return

        total_rev = sum(s["amount_charged"] for s in sessions)
        total_sessions = len(sessions)

        rows_html = ""
        for s in sessions:
            user = s.get("guest_name") or f"Member #{s.get('member_id','?')}"
            time_str = s["start_time"][11:16] if s["start_time"] else "—"
            rows_html += f"""
            <tr>
                <td>{time_str}</td>
                <td><b>{s['pc_name']}</b></td>
                <td>{user}</td>
                <td>{s['duration_mins']} mins</td>
                <td style="color:#e02424; font-weight:bold;">{config.CURRENCY} {s['amount_charged']:.0f}</td>
                <td>{s['payment_type'].capitalize()}</td>
                <td><span class="badge">{s['status'].upper()}</span></td>
            </tr>
            """

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AZ Cafe Report - {today}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 30px; background: #fff; color: #222; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c8102e; padding-bottom: 15px; margin-bottom: 20px; }}
        h1 {{ margin: 0; color: #c8102e; }}
        .stats-grid {{ display: flex; gap: 20px; margin-bottom: 25px; }}
        .card {{ background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 15px; flex: 1; }}
        .card h3 {{ margin: 0 0 8px 0; font-size: 13px; color: #6c757d; text-transform: uppercase; }}
        .card .value {{ font-size: 24px; font-weight: bold; color: #111; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 10px 12px; border-bottom: 1px solid #dee2e6; text-align: left; font-size: 14px; }}
        th {{ background: #f1f3f5; color: #495057; font-weight: 600; }}
        .badge {{ background: #e9ecef; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
        @media print {{
            .no-print {{ display: none; }}
            body {{ margin: 0; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>AZ CAFE — DAILY SESSION REPORT</h1>
            <p style="margin: 4px 0 0 0; color: #6c757d;">Generated on {today} | Gaming Center Management System</p>
        </div>
        <button class="no-print" onclick="window.print()" style="padding: 10px 18px; background: #c8102e; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">Print / Save as PDF</button>
    </div>

    <div class="stats-grid">
        <div class="card">
            <h3>Total Daily Revenue</h3>
            <div class="value" style="color: #c8102e;">{config.CURRENCY} {total_rev:.0f}</div>
        </div>
        <div class="card">
            <h3>Total Sessions</h3>
            <div class="value">{total_sessions}</div>
        </div>
        <div class="card">
            <h3>Average / Session</h3>
            <div class="value">{config.CURRENCY} {total_rev/total_sessions:.0f}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>PC</th>
                <th>Customer</th>
                <th>Duration</th>
                <th>Amount Charged</th>
                <th>Payment</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

        self.app.set_status(f"Exported printable report: {path}")
        if messagebox.askyesno("Open Report", f"Report saved to:\n{path}\n\nOpen in browser now to view/print to PDF?", parent=self):
            webbrowser.open(f"file:///{path.replace(os.sep, '/')}")

