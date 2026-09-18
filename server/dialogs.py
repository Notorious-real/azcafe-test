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
from server import printer


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
            text="🖨  Preview Receipt",
            command=lambda: self._show_receipt(user, used_mins,
                                               used_secs_r, actual_amt,
                                               total_mins, amount),
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

    def _show_receipt(self, user, used_mins, used_secs_r, amount,
                      total_mins=0, prepaid=None):
        """Estimate before the stop is confirmed; the final receipt comes
        from the server once the session is settled."""
        prepaid = amount if prepaid is None else prepaid
        ReceiptWindow(self, {
            "session_id": self.session_info.get("session_id", "-"),
            "pc_name": self.pc_name,
            "user": user,
            "payment_type": self._payment_var.get(),
            "booked_mins": total_mins,
            "used_secs": used_mins * 60 + used_secs_r,
            "prepaid": prepaid,
            "charged": amount,
            "refund": max(0.0, float(prepaid) - float(amount)),
            "balance_left": None,
        })


# ============================================================
#  Receipt Window — Phase 2C
# ============================================================

class ReceiptWindow(tk.Toplevel):
    """
    On-screen receipt for a settled session (2F / 7B).

    Takes the payload produced by AZCafeServer._settle so the numbers are
    the server's, not a guess, and can send the same text to the printer.
    """

    def __init__(self, parent, payload: dict):
        super().__init__(parent)
        self.payload = payload or {}
        self.title("Receipt")
        self.configure(bg="white")
        self.resizable(False, False)

        width, height = 320, 470
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self._build()

    def _build(self):
        from datetime import datetime

        payload = self.payload
        shop = db.get_setting("shop_name", config.APP_NAME)
        pad = tk.Frame(self, bg="white", padx=20, pady=16)
        pad.pack(fill=tk.BOTH, expand=True)

        def _center(text, size=10, bold=False, color="black"):
            tk.Label(pad, text=text, font=("Courier", size, "bold" if bold else "normal"),
                     fg=color, bg="white", justify=tk.CENTER).pack()

        def _divider():
            tk.Label(pad, text="-" * 34, font=("Courier", 9),
                     fg="gray", bg="white").pack()

        def _row(label, value, color="black"):
            row = tk.Frame(pad, bg="white")
            row.pack(fill=tk.X)
            tk.Label(row, text=label, font=("Courier", 9), fg="black",
                     bg="white", anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, font=("Courier", 9), fg=color,
                     bg="white", anchor="e").pack(side=tk.RIGHT)

        used = int(payload.get("used_secs") or 0)
        hours, rest = divmod(used, 3600)
        minutes, seconds = divmod(rest, 60)
        charged = float(payload.get("charged") or 0)
        refund = float(payload.get("refund") or 0)
        prepaid = float(payload.get("prepaid") or 0)

        _center(shop, 14, bold=True)
        _center("SESSION RECEIPT", 11, bold=True)
        _center(datetime.now().strftime("%d-%m-%Y  %I:%M %p"), 9)
        _divider()
        _row("Receipt #", str(payload.get("session_id", "-")))
        _row("PC:", str(payload.get("pc_name", "-")))
        _row("Customer:", str(payload.get("user", "Guest")))
        _row("Payment:", str(payload.get("payment_type", "cash")).title())
        _divider()
        _row("Time booked:", f"{payload.get('booked_mins', 0)} min")
        _row("Time used:", f"{hours}h {minutes:02d}m {seconds:02d}s")
        _divider()
        _row("Prepaid:", f"{config.CURRENCY} {prepaid:.0f}")
        _row("TOTAL:", f"{config.CURRENCY} {charged:.0f}", config.COLOR_RED)
        if refund > 0:
            _row("Refund:", f"{config.CURRENCY} {refund:.0f}", "#008000")
        balance_left = payload.get("balance_left")
        if balance_left is not None:
            _row("Balance left:", f"{config.CURRENCY} {float(balance_left):.0f}")
        _divider()
        _center("Thank you!  Please visit again", 9, bold=True)

        buttons = tk.Frame(pad, bg="white")
        buttons.pack(pady=(14, 0))
        tk.Button(buttons, text="🖨  Print", command=self._print,
                  bg=config.COLOR_RED, fg="white", font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=6, cursor="hand2", bd=0).pack(side=tk.LEFT)
        tk.Button(buttons, text="Close", command=self.destroy,
                  bg="#dddddd", fg="black", font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=14, pady=6, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=(8, 0))

    def _print(self):
        shop = db.get_setting("shop_name", config.APP_NAME)
        printer_name = db.get_setting("receipt_printer", "")
        ok, message = printer.print_receipt(self.payload, shop_name=shop,
                                            currency=config.CURRENCY,
                                            printer_name=printer_name)
        if ok:
            messagebox.showinfo("Receipt", message, parent=self)
        else:
            messagebox.showwarning("Receipt", message, parent=self)


# ============================================================
#  Add Time dialog — Phase 5D
#  Time is charged for and persisted; it is no longer memory-only.
# ============================================================

class AddTimeDialog(tk.Toplevel):

    def __init__(self, parent, pc_name: str, rate_per_hour: float,
                 member_id=None, payment_type: str = "cash", on_add=None):
        super().__init__(parent)
        self.pc_name = pc_name
        self.rate_per_hour = float(rate_per_hour or 0)
        self.member_id = member_id
        self.on_add = on_add or (lambda mins, amount, pay: None)

        self.title(f"Add Time — {pc_name}")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        width, height = 380, 420
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        self._mins_var = tk.StringVar(value="30")
        self._amount_var = tk.StringVar(value="")
        self._payment_var = tk.StringVar(value=payment_type or "cash")
        self._build()
        self._recalc()

    def _build(self):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(self, text=f"  ⏱  Add Time  —  {self.pc_name}",
                 font=("Segoe UI", 11, "bold"), fg=config.COLOR_TEXT,
                 bg=config.COLOR_BG2, anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=22, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text=f"Rate: {config.CURRENCY} {self.rate_per_hour:.0f} / hour",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, anchor="w").pack(fill=tk.X)

        tk.Label(body, text="Extra minutes", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(12, 2))
        entry = tk.Entry(body, textvariable=self._mins_var, font=("Segoe UI", 11),
                         bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                         insertbackground=config.COLOR_TEXT, relief=tk.FLAT, bd=5)
        entry.pack(fill=tk.X)
        entry.bind("<KeyRelease>", lambda e: self._recalc())
        entry.focus_set()

        quick = tk.Frame(body, bg=config.COLOR_BG)
        quick.pack(fill=tk.X, pady=(6, 0))
        for minutes in (15, 30, 60, 120):
            tk.Button(quick, text=f"+{minutes}m",
                      command=lambda m=minutes: (self._mins_var.set(str(m)), self._recalc()),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 8), relief=tk.FLAT, padx=8, pady=3,
                      cursor="hand2", bd=0,
                      activebackground=config.COLOR_RED,
                      activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=2)

        tk.Label(body, text=f"Amount ({config.CURRENCY})", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(12, 2))
        amount_entry = tk.Entry(body, textvariable=self._amount_var,
                                font=("Segoe UI", 11), bg=config.COLOR_BG3,
                                fg=config.COLOR_TEXT, insertbackground=config.COLOR_TEXT,
                                relief=tk.FLAT, bd=5)
        amount_entry.pack(fill=tk.X)

        tk.Label(body, text="Payment", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(12, 2))
        pay_row = tk.Frame(body, bg=config.COLOR_BG)
        pay_row.pack(fill=tk.X)
        options = [("Cash", "cash")]
        if self.member_id:
            options.append(("Member balance", "balance"))
        for text, value in options:
            tk.Radiobutton(pay_row, text=text, variable=self._payment_var,
                           value=value, bg=config.COLOR_BG, fg=config.COLOR_TEXT,
                           selectcolor=config.COLOR_BG3, activebackground=config.COLOR_BG,
                           font=("Segoe UI", 9), cursor="hand2").pack(side=tk.LEFT, padx=(0, 12))

        self._note_var = tk.StringVar()
        tk.Label(body, textvariable=self._note_var, font=("Segoe UI", 8),
                 fg=config.COLOR_YELLOW, bg=config.COLOR_BG, anchor="w",
                 wraplength=320, justify=tk.LEFT).pack(fill=tk.X, pady=(10, 0))

        buttons = tk.Frame(self, bg=config.COLOR_BG2, pady=10, padx=20)
        buttons.pack(fill=tk.X)
        tk.Button(buttons, text="➕  Add Time", command=self._confirm,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT,
                  padx=18, pady=7, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT)
        tk.Button(buttons, text="Cancel", command=self.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=14, pady=7,
                  cursor="hand2", bd=0).pack(side=tk.RIGHT, padx=(0, 8))

    def _recalc(self):
        try:
            minutes = float(self._mins_var.get() or 0)
        except ValueError:
            minutes = 0
        amount = round((minutes / 60.0) * self.rate_per_hour, 2)
        self._amount_var.set(f"{amount:.0f}")
        if self.member_id and self._payment_var.get() == "balance":
            member = db.get_member_by_id(self.member_id)
            if member:
                self._note_var.set(f"Member balance: {config.CURRENCY} "
                                   f"{member['balance']:.0f}")
        else:
            self._note_var.set("Cash is collected at the counter; the session "
                               "and the ledger are updated either way.")

    def _confirm(self):
        try:
            minutes = int(float(self._mins_var.get()))
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number of minutes.", parent=self)
            return
        if minutes <= 0:
            messagebox.showerror("Error", "Minutes must be at least 1.", parent=self)
            return
        try:
            amount = round(float(self._amount_var.get() or 0), 2)
        except ValueError:
            messagebox.showerror("Error", "Enter a valid amount.", parent=self)
            return
        if amount < 0:
            messagebox.showerror("Error", "Amount cannot be negative.", parent=self)
            return
        self.on_add(minutes, amount, self._payment_var.get())
        self.destroy()


# ============================================================
#  Manage Groups dialog — Phase 5F
#  Create, rename and delete groups (previously you could only
#  assign a name that already existed somewhere).
# ============================================================

class ManageGroupsDialog(tk.Toplevel):

    def __init__(self, parent, on_changed=None):
        super().__init__(parent)
        self.on_changed = on_changed or (lambda: None)
        self.title("Manage PC Groups")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        width, height = 460, 480
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        self._new_var = tk.StringVar()
        self._list = None
        self._build()
        self._refresh()

    def _build(self):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(self, text="  📁  PC Groups", font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2, anchor="w",
                 pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        self._list = tk.Listbox(body, font=("Segoe UI", 10),
                                bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                selectbackground=config.COLOR_RED,
                                selectforeground=config.COLOR_TEXT,
                                relief=tk.FLAT, bd=0, height=10)
        self._list.pack(fill=tk.BOTH, expand=True)

        row = tk.Frame(body, bg=config.COLOR_BG)
        row.pack(fill=tk.X, pady=(12, 0))
        tk.Label(row, text="New group", font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)
        entry = tk.Entry(row, textvariable=self._new_var, font=("Segoe UI", 10),
                         bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                         insertbackground=config.COLOR_TEXT, relief=tk.FLAT, bd=4)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        entry.bind("<Return>", lambda e: self._create())
        tk.Button(row, text="Create", command=self._create,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=10, pady=4, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT)

        buttons = tk.Frame(body, bg=config.COLOR_BG)
        buttons.pack(fill=tk.X, pady=(12, 0))
        tk.Button(buttons, text="✏️  Rename", command=self._rename,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=5, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT)
        tk.Button(buttons, text="🗑  Delete", command=self._delete,
                  bg=config.COLOR_BG3, fg=config.COLOR_RED_BRIGHT,
                  font=("Segoe UI", 9), relief=tk.FLAT, padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Close", command=self.destroy,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=14, pady=5,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT)

        tk.Label(body, text="Deleting a group moves its PCs back to “Default”.",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, anchor="w").pack(fill=tk.X, pady=(10, 0))

    def _selected_group(self):
        selection = self._list.curselection()
        if not selection:
            return None
        return self._list.get(selection[0]).split("  (")[0].strip()

    def _refresh(self):
        self._list.delete(0, tk.END)
        counts = db.get_group_counts()
        for group in db.get_all_pc_groups():
            self._list.insert(tk.END, f"{group}  ({counts.get(group, 0)} PCs)")

    def _create(self):
        name = self._new_var.get().strip()
        if not name:
            return
        db.create_pc_group(name)
        self._new_var.set("")
        self._refresh()
        self.on_changed()

    def _rename(self):
        old = self._selected_group()
        if not old:
            messagebox.showinfo("Groups", "Select a group first.", parent=self)
            return
        from tkinter import simpledialog
        new = simpledialog.askstring("Rename group", f"New name for “{old}”:",
                                     parent=self)
        if not new or not new.strip() or new.strip() == old:
            return
        moved = db.rename_pc_group(old, new.strip())
        self._refresh()
        self.on_changed()
        messagebox.showinfo("Groups", f"Renamed to “{new.strip()}” ({moved} PCs).",
                            parent=self)

    def _delete(self):
        group = self._selected_group()
        if not group:
            messagebox.showinfo("Groups", "Select a group first.", parent=self)
            return
        if group == "Default":
            messagebox.showinfo("Groups", "The Default group cannot be deleted.",
                                parent=self)
            return
        if not messagebox.askyesno("Delete group",
                                   f"Delete “{group}”?\nIts PCs move to Default.",
                                   parent=self):
            return
        db.delete_pc_group(group)
        self._refresh()
        self.on_changed()
