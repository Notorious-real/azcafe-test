# ============================================================
#  AZ Cafe - Dialogs (Phase 2A)
#  Start Session dialog with guest/member, pricing, billing
# ============================================================

import tkinter as tk
from tkinter import messagebox
import sys, os

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config
import database as db


class StartSessionDialog(tk.Toplevel):

    def __init__(self, parent, pc_name: str, on_start):
        super().__init__(parent)
        self.pc_name  = pc_name
        self.on_start = on_start

        self.title(f"Start Session — {pc_name}")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        w, h = 440, 580
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._mode        = tk.StringVar(value="guest")
        self._dur_var     = tk.StringVar(value="60")
        self._plan_var    = tk.StringVar()
        self._amount_var  = tk.StringVar(value=f"{config.CURRENCY} 0")
        self._discount_var= tk.StringVar(value="0")  # Discount %
        self._payment_var = tk.StringVar(value="cash")
        self._plans       = db.get_all_pricing_plans()
        self._packages    = db.get_all_time_packages()
        self._pkg_var     = tk.StringVar(value="Custom")
        self._selected_pkg_price = None
        self._member      = None
        self._members_data= []

        # Phase 4C: Check if this PC has an assigned pricing plan
        self._pc_record   = db.get_pc_by_name(pc_name)

        self._build_ui()
        self._recalc()

    # ── Shared widget helpers ─────────────────────────────────

    def _lbl(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(6, 2))

    def _sep(self, parent):
        tk.Frame(parent, bg=config.COLOR_BORDER, height=1).pack(
            fill=tk.X, pady=8)

    def _entry_widget(self, parent, var):
        e = tk.Entry(parent, textvariable=var,
                     font=("Segoe UI", 10),
                     bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                     insertbackground=config.COLOR_TEXT,
                     relief=tk.FLAT, bd=4)
        e.pack(fill=tk.X)
        return e

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        # Title strip
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(self, text=f"  ▶  Start Session  —  {self.pc_name}",
                 font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=20, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Mode toggle ───────────────────────────────────────
        mode_row = tk.Frame(body, bg=config.COLOR_BG)
        mode_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(mode_row, text="Type:", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)
        for text, val in [("Guest", "guest"), ("Member", "member")]:
            tk.Radiobutton(mode_row, text=text,
                           variable=self._mode, value=val,
                           command=self._on_mode_change,
                           bg=config.COLOR_BG, fg=config.COLOR_TEXT,
                           selectcolor=config.COLOR_BG3,
                           activebackground=config.COLOR_BG,
                           font=("Segoe UI", 9, "bold"),
                           cursor="hand2").pack(side=tk.LEFT, padx=(10, 0))

        self._sep(body)

        # ── Guest fields ──────────────────────────────────────
        self._guest_frame = tk.Frame(body, bg=config.COLOR_BG)
        self._guest_frame.pack(fill=tk.X)
        self._lbl(self._guest_frame, "Customer Name")
        self._guest_name = tk.StringVar()
        self._entry_widget(self._guest_frame, self._guest_name)

        # ── Member fields (hidden initially) ─────────────────
        self._member_frame = tk.Frame(body, bg=config.COLOR_BG)
        self._lbl(self._member_frame, "Search Member (name or username)")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._entry_widget(self._member_frame, self._search_var)

        self._member_list = tk.Listbox(
            self._member_frame, font=("Segoe UI", 9),
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
            selectbackground=config.COLOR_RED,
            selectforeground=config.COLOR_TEXT,
            relief=tk.FLAT, bd=0, height=4)
        self._member_list.pack(fill=tk.X, pady=(4, 0))
        self._member_list.bind("<<ListboxSelect>>", self._on_member_select)

        self._member_info_var = tk.StringVar(value="No member selected")
        tk.Label(self._member_frame, textvariable=self._member_info_var,
                 font=("Segoe UI", 8), fg=config.COLOR_GREEN,
                 bg=config.COLOR_BG).pack(anchor="w", pady=(4, 0))

        # ── Time Packages (Phase 4B) ─────────────────────────
        if self._packages:
            self._sep(body)
            pkg_hdr = tk.Frame(body, bg=config.COLOR_BG)
            pkg_hdr.pack(fill=tk.X)
            tk.Label(pkg_hdr, text="Time Package (Bundles):", font=("Segoe UI", 9),
                     fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

            pkg_bar = tk.Frame(body, bg=config.COLOR_BG)
            pkg_bar.pack(fill=tk.X, pady=(4, 2))

            for pkg in self._packages:
                lbl = f"{pkg['name']} ({config.CURRENCY} {pkg['price']:.0f})"
                tk.Button(pkg_bar, text=lbl,
                          command=lambda p=pkg: self._select_package(p),
                          bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                          font=("Segoe UI", 8), relief=tk.FLAT, bd=0,
                          padx=6, pady=3, cursor="hand2",
                          activebackground=config.COLOR_RED,
                          activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=2, pady=1)

        # ── Duration ──────────────────────────────────────────
        self._sep(body)
        dur_row = tk.Frame(body, bg=config.COLOR_BG)
        dur_row.pack(fill=tk.X)
        tk.Label(dur_row, text="Duration", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        for mins in [30, 60, 120, 180]:
            lbl = f"{mins}m" if mins < 60 else f"{mins//60}h"
            tk.Button(dur_row, text=lbl,
                      command=lambda m=mins: self._set_dur(m),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 8), relief=tk.FLAT, bd=0,
                      padx=8, pady=2, cursor="hand2",
                      activebackground=config.COLOR_RED,
                      activeforeground=config.COLOR_TEXT
                      ).pack(side=tk.RIGHT, padx=2)

        dur_val_row = tk.Frame(body, bg=config.COLOR_BG)
        dur_val_row.pack(fill=tk.X, pady=(4, 0))
        tk.Entry(dur_val_row, textvariable=self._dur_var,
                 font=("Segoe UI", 12), bg=config.COLOR_BG3,
                 fg=config.COLOR_TEXT, insertbackground=config.COLOR_TEXT,
                 relief=tk.FLAT, bd=4, width=8).pack(side=tk.LEFT)
        tk.Label(dur_val_row, text="minutes",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG).pack(side=tk.LEFT, padx=(8, 0))
        self._dur_var.trace_add("write", lambda *_: self._on_dur_change())

        # ── Pricing plan (Phase 4A & 4C) ─────────────────────
        self._sep(body)
        plan_hdr = tk.Frame(body, bg=config.COLOR_BG)
        plan_hdr.pack(fill=tk.X)
        tk.Label(plan_hdr, text="Pricing Plan", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        # Auto-select plan assigned to this PC if available
        plan_names = [p["name"] for p in self._plans] or ["Standard"]
        initial_plan = plan_names[0]
        if self._pc_record and self._pc_record.get("pricing_plan_id"):
            for p in self._plans:
                if p["id"] == self._pc_record["pricing_plan_id"]:
                    initial_plan = p["name"]
                    tk.Label(plan_hdr, text=f" (Assigned to {self.pc_name})",
                             font=("Segoe UI", 8, "italic"),
                             fg=config.COLOR_GREEN, bg=config.COLOR_BG).pack(side=tk.LEFT)
                    break

        self._plan_var.set(initial_plan)
        plan_menu = tk.OptionMenu(body, self._plan_var, *plan_names,
                                  command=lambda _: self._on_plan_change())
        plan_menu.config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                         font=("Segoe UI", 9), relief=tk.FLAT, bd=0,
                         activebackground=config.COLOR_RED,
                         activeforeground=config.COLOR_TEXT,
                         cursor="hand2")
        plan_menu["menu"].config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                 activebackground=config.COLOR_RED,
                                 activeforeground=config.COLOR_TEXT)
        plan_menu.pack(anchor="w")

        # ── Discount System (Phase 4D) ────────────────────────
        self._sep(body)
        disc_row = tk.Frame(body, bg=config.COLOR_BG)
        disc_row.pack(fill=tk.X)
        tk.Label(disc_row, text="Discount (%):", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        for dpct in [0, 10, 20, 50]:
            tk.Button(disc_row, text=f"{dpct}%",
                      command=lambda p=dpct: self._set_discount(p),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 8), relief=tk.FLAT, bd=0,
                      padx=8, pady=2, cursor="hand2",
                      activebackground=config.COLOR_RED,
                      activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT, padx=2)

        disc_entry_row = tk.Frame(body, bg=config.COLOR_BG)
        disc_entry_row.pack(fill=tk.X, pady=(4, 0))
        tk.Entry(disc_entry_row, textvariable=self._discount_var,
                 font=("Segoe UI", 10), bg=config.COLOR_BG3,
                 fg=config.COLOR_TEXT, insertbackground=config.COLOR_TEXT,
                 relief=tk.FLAT, bd=4, width=6).pack(side=tk.LEFT)
        tk.Label(disc_entry_row, text="% off total charge",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG).pack(side=tk.LEFT, padx=(8, 0))
        self._discount_var.trace_add("write", lambda *_: self._recalc())

        # ── Payment type ──────────────────────────────────────
        self._sep(body)
        pay_row = tk.Frame(body, bg=config.COLOR_BG)
        pay_row.pack(fill=tk.X)
        tk.Label(pay_row, text="Payment:", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)
        for text, val in [("Cash", "cash"), ("Member Balance", "balance")]:
            tk.Radiobutton(pay_row, text=text,
                           variable=self._payment_var, value=val,
                           bg=config.COLOR_BG, fg=config.COLOR_TEXT,
                           selectcolor=config.COLOR_BG3,
                           activebackground=config.COLOR_BG,
                           font=("Segoe UI", 9), cursor="hand2"
                           ).pack(side=tk.LEFT, padx=(10, 0))

        # ── Amount due ────────────────────────────────────────
        amt_row = tk.Frame(body, bg=config.COLOR_BG)
        amt_row.pack(fill=tk.X, pady=(12, 0))
        tk.Label(amt_row, text="Amount Due:",
                 font=("Segoe UI", 10), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG).pack(side=tk.LEFT)
        tk.Label(amt_row, textvariable=self._amount_var,
                 font=("Segoe UI", 18, "bold"),
                 fg=config.COLOR_RED_BRIGHT,
                 bg=config.COLOR_BG).pack(side=tk.RIGHT)

        # ── Button bar ────────────────────────────────────────
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)
        btn_bar = tk.Frame(self, bg=config.COLOR_BG2, pady=10, padx=20)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="▶  Start Session",
                  command=self._confirm,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=20, pady=8, cursor="hand2",
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT, bd=0
                  ).pack(side=tk.RIGHT)

        tk.Button(btn_bar, text="Cancel", command=self.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=14, pady=8, cursor="hand2", bd=0
                  ).pack(side=tk.RIGHT, padx=(0, 8))

    # ── Callbacks ─────────────────────────────────────────────

    def _on_mode_change(self):
        if self._mode.get() == "guest":
            self._member_frame.pack_forget()
            self._guest_frame.pack(fill=tk.X)
        else:
            self._guest_frame.pack_forget()
            self._member_frame.pack(fill=tk.X)
        self._recalc()

    def _select_package(self, pkg: dict):
        self._selected_pkg_price = float(pkg["price"])
        self._dur_var.set(str(pkg["duration_mins"]))
        self._recalc()

    def _set_dur(self, mins):
        self._selected_pkg_price = None
        self._dur_var.set(str(mins))

    def _set_discount(self, pct):
        self._discount_var.set(str(pct))

    def _on_dur_change(self):
        self._recalc()

    def _on_plan_change(self):
        self._selected_pkg_price = None
        self._recalc()

    def _on_search(self, *_):
        q = self._search_var.get().strip()
        self._member_list.delete(0, tk.END)
        self._members_data = []
        if not q:
            return
        members = db.search_members(q)
        self._members_data = members
        for m in members:
            self._member_list.insert(
                tk.END,
                f"{m['name']}  (@{m['username']})  —  Rs {m['balance']:.0f}"
            )

    def _on_member_select(self, e):
        sel = self._member_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._members_data):
            self._member = self._members_data[idx]
            self._member_info_var.set(
                f"✓  {self._member['name']}  |  Balance: Rs {self._member['balance']:.0f}"
            )
            self._recalc()

    def _get_rate(self) -> float:
        name = self._plan_var.get()
        for p in self._plans:
            if p["name"] == name:
                return float(p["rate_per_hour"])
        return db.get_default_rate()

    def _recalc(self, *_):
        try:
            mins = float(self._dur_var.get())
            if self._selected_pkg_price is not None:
                base_amt = self._selected_pkg_price
            else:
                base_amt = (mins / 60.0) * self._get_rate()

            # Apply discount
            try:
                disc_pct = float(self._discount_var.get() or 0)
            except ValueError:
                disc_pct = 0.0

            disc_pct = max(0.0, min(disc_pct, 100.0))
            final_amt = base_amt * (1.0 - (disc_pct / 100.0))
            final_amt = max(0.0, final_amt)

            if disc_pct > 0:
                self._amount_var.set(f"{config.CURRENCY} {final_amt:.0f} (-{disc_pct:.0f}%)")
            else:
                self._amount_var.set(f"{config.CURRENCY} {final_amt:.0f}")
        except ValueError:
            self._amount_var.set("—")

    def _confirm(self):
        try:
            mins = int(self._dur_var.get())
            if mins <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Enter a valid duration.", parent=self)
            return

        try:
            disc_pct = float(self._discount_var.get() or 0)
        except ValueError:
            disc_pct = 0.0
        disc_pct = max(0.0, min(disc_pct, 100.0))

        if self._selected_pkg_price is not None:
            base_amt = self._selected_pkg_price
        else:
            base_amt = (mins / 60.0) * self._get_rate()

        disc_amount = round(base_amt * (disc_pct / 100.0), 2)
        amount = max(0.0, round(base_amt - disc_amount, 2))

        if self._mode.get() == "guest":
            user      = self._guest_name.get().strip() or "Guest"
            member_id = None
        else:
            if not self._member:
                messagebox.showerror("Error", "Select a member.", parent=self)
                return
            user      = self._member["name"]
            member_id = self._member["id"]
            if self._payment_var.get() == "balance":
                if self._member["balance"] < amount:
                    messagebox.showerror(
                        "Insufficient Balance",
                        f"Balance: Rs {self._member['balance']:.0f}\n"
                        f"Required: Rs {amount:.0f}", parent=self)
                    return

        self.on_start(
            pc_name        =self.pc_name,
            user           =user,
            duration_mins  =mins,
            amount         =amount,
            member_id      =member_id,
            payment_type   =self._payment_var.get(),
            discount_pct   =disc_pct,
            discount_amount=disc_amount
        )
        self.destroy()


# ============================================================
#  Stop Session Dialog — Phase 2C
#  Shows charge summary, collects payment, receipt option
# ============================================================

class StopSessionDialog(tk.Toplevel):
    """
    Shown when admin stops a session.
    Displays: user, time used, amount charged, payment method.
    Option to print/show receipt.
    """

    def __init__(self, parent, pc_name: str, session_info: dict, on_confirm):
        super().__init__(parent)
        self.pc_name      = pc_name
        self.session_info = session_info   # {user, duration_mins, remaining_secs, amount, member_id, payment_type}
        self.on_confirm   = on_confirm     # callback(payment_type)

        self.title(f"Stop Session — {pc_name}")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        w, h = 380, 420
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._payment_var = tk.StringVar(
            value=session_info.get("payment_type", "cash")
        )
        self._build_ui()

    def _build_ui(self):
        # ── Title strip ───────────────────────────────────────
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(
            self,
            text=f"  ⏹  Stop Session  —  {self.pc_name}",
            font=("Segoe UI", 11, "bold"),
            fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
            anchor="w", pady=10
        ).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=24, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Session summary ───────────────────────────────────
        si           = self.session_info
        user         = si.get("user", "Guest")
        total_mins   = si.get("duration_mins", 0)
        remaining    = si.get("remaining_secs", 0)
        used_secs    = max(0, total_mins * 60 - remaining)
        used_mins    = used_secs // 60
        used_secs_r  = used_secs % 60
        amount       = si.get("amount", 0.0)

        # 2E fix: derive rate from this session's own prepaid amount ÷ duration
        # so the stop charge always matches the plan that was chosen at start.
        # Fall back to the default rate only if the session has no cost data.
        if total_mins > 0 and amount > 0:
            rate = (amount / total_mins) * 60   # Rs per hour implied by this session
        else:
            rate = db.get_default_rate()
        actual_amt  = (used_secs / 3600.0) * rate
        actual_amt  = max(actual_amt, 0)

        # 2F fix: store so _confirm() can pass it to the server → DB
        self._actual_amt = actual_amt

        # Summary card
        card = tk.Frame(body, bg=config.COLOR_BG3, padx=16, pady=14)
        card.pack(fill=tk.X, pady=(0, 12))

        def _row(label, value, value_color=config.COLOR_TEXT):
            row = tk.Frame(card, bg=config.COLOR_BG3)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label,
                     font=("Segoe UI", 9),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     anchor="w", width=16).pack(side=tk.LEFT)
            tk.Label(row, text=value,
                     font=("Segoe UI", 9, "bold"),
                     fg=value_color,
                     bg=config.COLOR_BG3,
                     anchor="w").pack(side=tk.LEFT)

        _row("Customer:",  user)
        _row("PC:",        self.pc_name)
        _row("Time Booked:", f"{total_mins} minutes")
        _row("Time Used:",
             f"{used_mins}m {used_secs_r:02d}s",
             config.COLOR_YELLOW)

        # Divider
        tk.Frame(card, bg=config.COLOR_BORDER, height=1).pack(
            fill=tk.X, pady=8)

        # Amount row — large
        amt_row = tk.Frame(card, bg=config.COLOR_BG3)
        amt_row.pack(fill=tk.X)
        tk.Label(amt_row, text="Amount Charged:",
                 font=("Segoe UI", 10),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG3).pack(side=tk.LEFT)
        tk.Label(amt_row,
                 text=f"{config.CURRENCY} {actual_amt:.0f}",
                 font=("Segoe UI", 20, "bold"),
                 fg=config.COLOR_RED_BRIGHT,
                 bg=config.COLOR_BG3).pack(side=tk.RIGHT)

        # Prepaid note
        if amount > actual_amt:
            diff = amount - actual_amt
            tk.Label(card,
                     text=f"Prepaid: {config.CURRENCY} {amount:.0f}  |  "
                          f"Refund: {config.CURRENCY} {diff:.0f}",
                     font=("Segoe UI", 8),
                     fg=config.COLOR_GREEN,
                     bg=config.COLOR_BG3).pack(anchor="e", pady=(4, 0))

        # ── Payment type ──────────────────────────────────────
        tk.Frame(body, bg=config.COLOR_BORDER, height=1).pack(
            fill=tk.X, pady=(4, 8))

        pay_row = tk.Frame(body, bg=config.COLOR_BG)
        pay_row.pack(fill=tk.X)
        tk.Label(pay_row, text="Payment:",
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG).pack(side=tk.LEFT)
        for text, val in [("Cash", "cash"), ("Member Balance", "balance")]:
            tk.Radiobutton(
                pay_row, text=text,
                variable=self._payment_var, value=val,
                bg=config.COLOR_BG, fg=config.COLOR_TEXT,
                selectcolor=config.COLOR_BG3,
                activebackground=config.COLOR_BG,
                font=("Segoe UI", 9), cursor="hand2"
            ).pack(side=tk.LEFT, padx=(10, 0))

        # ── Receipt button ────────────────────────────────────
        tk.Button(
            body,
            text="🖨  View Receipt",
            command=lambda: self._show_receipt(user, used_mins,
                                               used_secs_r, actual_amt),
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=12, pady=4,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_BG2,
            activeforeground=config.COLOR_TEXT
        ).pack(anchor="w", pady=(8, 0))

        # ── Buttons ───────────────────────────────────────────
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)
        btn_bar = tk.Frame(self, bg=config.COLOR_BG2, pady=10, padx=20)
        btn_bar.pack(fill=tk.X)

        tk.Button(
            btn_bar, text="⏹  Confirm & Stop",
            command=self._confirm,
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=20, pady=8,
            cursor="hand2",
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT,
            bd=0
        ).pack(side=tk.RIGHT)

        tk.Button(
            btn_bar, text="Cancel",
            command=self.destroy,
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 9), relief=tk.FLAT,
            padx=14, pady=8, cursor="hand2", bd=0
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _confirm(self):
        # 2F fix: pass actual_amt so dashboard → server → DB can update amount_charged
        self.on_confirm(payment_type=self._payment_var.get(),
                        actual_amount=self._actual_amt)
        self.destroy()

    def _show_receipt(self, user, used_mins, used_secs_r, amount):
        ReceiptWindow(self, self.pc_name, user,
                      used_mins, used_secs_r, amount)


# ============================================================
#  Receipt Window — Phase 2C
# ============================================================

class ReceiptWindow(tk.Toplevel):
    """
    Simple receipt shown on screen.
    Can be printed via system print dialog.
    """

    def __init__(self, parent, pc_name, user,
                 used_mins, used_secs_r, amount):
        super().__init__(parent)
        self.title("Receipt")
        self.configure(bg="white")
        self.resizable(False, False)

        w, h = 300, 400
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build(pc_name, user, used_mins, used_secs_r, amount)

    def _build(self, pc_name, user, used_mins, used_secs_r, amount):
        from datetime import datetime
        now = datetime.now().strftime("%d-%m-%Y  %I:%M %p")

        pad = tk.Frame(self, bg="white", padx=20, pady=16)
        pad.pack(fill=tk.BOTH, expand=True)

        def _center(text, font_size=10, bold=False, color="black"):
            w = "bold" if bold else "normal"
            tk.Label(pad, text=text,
                     font=("Courier", font_size, w),
                     fg=color, bg="white",
                     justify=tk.CENTER).pack()

        def _divider():
            tk.Label(pad, text="-" * 34,
                     font=("Courier", 9),
                     fg="gray", bg="white").pack()

        shop = db.get_setting("shop_name", config.APP_NAME)

        _center(shop, 14, bold=True)
        _center("GAMING ZONE", 9)
        _center(now, 9)
        _divider()
        _center("RECEIPT", 11, bold=True)
        _divider()

        def _row(label, value):
            row = tk.Frame(pad, bg="white")
            row.pack(fill=tk.X)
            tk.Label(row, text=label,
                     font=("Courier", 9),
                     fg="black", bg="white",
                     anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value,
                     font=("Courier", 9),
                     fg="black", bg="white",
                     anchor="e").pack(side=tk.RIGHT)

        _row("Customer:", user)
        _row("PC:", pc_name)
        _row("Time Used:", f"{used_mins}m {used_secs_r:02d}s")
        _divider()
        _row("TOTAL:", f"{config.CURRENCY} {amount:.0f}")
        _divider()
        _center("Thank you!", 10, bold=True)
        _center("Please visit again", 9)

        tk.Button(
            pad,
            text="🖨  Print",
            command=self._print,
            bg=config.COLOR_RED, fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=16, pady=6,
            cursor="hand2", bd=0
        ).pack(pady=(16, 0))

    def _print(self):
        """
        Print via Windows notepad (simplest cross-version approach).
        For thermal printer support — add in Phase 7.
        """
        messagebox.showinfo(
            "Print",
            "Thermal printer support coming in Phase 7.\n\n"
            "For now, take a screenshot of this receipt.",
            parent=self
        )
