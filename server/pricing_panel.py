# ============================================================
#  AZ Cafe - Pricing & Packages Panel (Phase 4)
#  Comprehensive manager for hourly rates and time packages
# ============================================================

import tkinter as tk
from tkinter import messagebox
import sys
import os

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config
import database as db
from server.settings_panel import PlanDialog


class PricingPanel(tk.Frame):
    """
    Dedicated Pricing & Packages screen (Phase 4).
    Contains two sub-views:
      1. Hourly Pricing Plans (4A)
      2. Time Packages / Fixed Bundles (4B)
    """

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app = app
        self._active_tab = "plans"
        self._build_ui()

    def _build_ui(self):
        # ── Toolbar ───────────────────────────────────────────
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Frame(bar, bg=config.COLOR_RED, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  PRICING & PACKAGES",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        # ── Tabs ──────────────────────────────────────────────
        tab_bar = tk.Frame(self, bg=config.COLOR_BG2)
        tab_bar.pack(fill=tk.X)
        self._tab_btns = {}

        tabs = [
            ("plans",    "🏷️  Hourly Pricing Plans"),
            ("packages", "📦  Time Packages & Bundles"),
        ]
        for key, label in tabs:
            btn = tk.Label(tab_bar, text=label,
                           font=("Segoe UI", 9),
                           fg=config.COLOR_TEXT_DIM,
                           bg=config.COLOR_BG2,
                           padx=18, pady=8,
                           cursor="hand2")
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            self._tab_btns[key] = btn

        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        self._content = tk.Frame(self, bg=config.COLOR_BG)
        self._content.pack(fill=tk.BOTH, expand=True)

        self._show_tab("plans")

    def _show_tab(self, key: str):
        if self._active_tab and self._active_tab in self._tab_btns:
            self._tab_btns[self._active_tab].config(
                fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)
        self._active_tab = key
        self._tab_btns[key].config(
            fg=config.COLOR_RED_BRIGHT, bg=config.COLOR_BG3)

        for w in self._content.winfo_children():
            w.destroy()

        if key == "plans":
            self._build_plans_view()
        elif key == "packages":
            self._build_packages_view()

    # ============================================================
    #  View 1: Hourly Pricing Plans (4A)
    # ============================================================

    def _build_plans_view(self):
        ctrl = tk.Frame(self._content, bg=config.COLOR_BG, padx=24, pady=12)
        ctrl.pack(fill=tk.X)

        tk.Label(ctrl, text="Configure standard hourly billing rates and default plans.",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        tk.Button(ctrl, text="+ Add Plan",
                  command=self._add_plan,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=5,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT)

        self._plans_table = tk.Frame(self._content, bg=config.COLOR_BG, padx=24)
        self._plans_table.pack(fill=tk.BOTH, expand=True)
        self._render_plans()

    def _render_plans(self):
        for w in self._plans_table.winfo_children():
            w.destroy()

        plans = db.get_all_pricing_plans()
        if not plans:
            tk.Label(self._plans_table, text="No pricing plans found. Click + Add Plan.",
                     font=("Segoe UI", 10), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG, pady=20).pack()
            return

        hdr = tk.Frame(self._plans_table, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X, pady=(0, 4))
        for text, w in [("Plan Name", 22), ("Rate/Hour", 14), ("Min Duration", 14), ("Default", 10), ("Actions", 20)]:
            tk.Label(hdr, text=text, font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG3,
                     width=w, anchor="w", padx=8, pady=6).pack(side=tk.LEFT)

        for plan in plans:
            row = tk.Frame(self._plans_table, bg=config.COLOR_BG2)
            row.pack(fill=tk.X, pady=1)

            is_default = "★ Default" if plan["is_default"] else ""
            def_color  = config.COLOR_GREEN if plan["is_default"] else config.COLOR_TEXT_DIM

            for text, w, color in [
                (plan["name"], 22, config.COLOR_TEXT),
                (f"{config.CURRENCY} {plan['rate_per_hour']:.0f}/hr", 14, config.COLOR_RED_BRIGHT),
                (f"{plan['min_minutes']} mins", 14, config.COLOR_TEXT_DIM),
                (is_default, 10, def_color),
            ]:
                tk.Label(row, text=text, font=("Segoe UI", 9),
                         fg=color, bg=config.COLOR_BG2,
                         width=w, anchor="w", padx=8, pady=7).pack(side=tk.LEFT)

            btn_frame = tk.Frame(row, bg=config.COLOR_BG2)
            btn_frame.pack(side=tk.LEFT)

            if not plan["is_default"]:
                tk.Button(btn_frame, text="Set Default",
                          command=lambda p=plan: self._set_default_plan(p["id"]),
                          bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                          font=("Segoe UI", 7), relief=tk.FLAT,
                          padx=6, pady=3, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

            tk.Button(btn_frame, text="Edit",
                      command=lambda p=plan: self._edit_plan(p),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 7), relief=tk.FLAT,
                      padx=6, pady=3, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

            tk.Button(btn_frame, text="Delete",
                      command=lambda p=plan: self._delete_plan(p["id"], p["name"]),
                      bg=config.COLOR_BG3, fg="#cc4444",
                      font=("Segoe UI", 7), relief=tk.FLAT,
                      padx=6, pady=3, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

    def _add_plan(self):
        PlanDialog(self, plan=None, on_save=self._on_plan_saved)

    def _edit_plan(self, plan: dict):
        PlanDialog(self, plan=plan, on_save=self._on_plan_saved)

    def _on_plan_saved(self):
        self._render_plans()
        self.app.set_status("Pricing plan saved")

    def _set_default_plan(self, plan_id: int):
        db.set_default_plan(plan_id)
        self._render_plans()
        self.app.set_status("Default pricing plan updated")

    def _delete_plan(self, plan_id: int, name: str):
        if messagebox.askyesno("Delete Plan", f"Delete pricing plan '{name}'?", parent=self):
            db.delete_pricing_plan(plan_id)
            self._render_plans()
            self.app.set_status(f"Deleted plan {name}")

    # ============================================================
    #  View 2: Time Packages & Bundles (4B)
    # ============================================================

    def _build_packages_view(self):
        ctrl = tk.Frame(self._content, bg=config.COLOR_BG, padx=24, pady=12)
        ctrl.pack(fill=tk.X)

        tk.Label(ctrl, text="Fixed bundles & passes (e.g. 1hr, 2hr, 5hr) available on start session.",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG).pack(side=tk.LEFT)

        tk.Button(ctrl, text="+ Add Package",
                  command=self._add_package,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=5,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT)

        self._packages_table = tk.Frame(self._content, bg=config.COLOR_BG, padx=24)
        self._packages_table.pack(fill=tk.BOTH, expand=True)
        self._render_packages()

    def _render_packages(self):
        for w in self._packages_table.winfo_children():
            w.destroy()

        packages = db.get_all_time_packages()
        if not packages:
            tk.Label(self._packages_table, text="No time packages defined. Click + Add Package.",
                     font=("Segoe UI", 10), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG, pady=20).pack()
            return

        hdr = tk.Frame(self._packages_table, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X, pady=(0, 4))
        for text, w in [("Package Name", 22), ("Duration", 14), ("Price", 14), ("Description", 26), ("Actions", 16)]:
            tk.Label(hdr, text=text, font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG3,
                     width=w, anchor="w", padx=8, pady=6).pack(side=tk.LEFT)

        for pkg in packages:
            row = tk.Frame(self._packages_table, bg=config.COLOR_BG2)
            row.pack(fill=tk.X, pady=1)

            dur_str = f"{pkg['duration_mins']} mins" if pkg['duration_mins'] < 60 else f"{pkg['duration_mins']//60} hrs"
            desc_str = pkg.get("description") or "—"

            for text, w, color in [
                (pkg["name"], 22, config.COLOR_TEXT),
                (dur_str, 14, config.COLOR_YELLOW),
                (f"{config.CURRENCY} {pkg['price']:.0f}", 14, config.COLOR_RED_BRIGHT),
                (desc_str, 26, config.COLOR_TEXT_DIM),
            ]:
                tk.Label(row, text=text, font=("Segoe UI", 9),
                         fg=color, bg=config.COLOR_BG2,
                         width=w, anchor="w", padx=8, pady=7).pack(side=tk.LEFT)

            btn_frame = tk.Frame(row, bg=config.COLOR_BG2)
            btn_frame.pack(side=tk.LEFT)

            tk.Button(btn_frame, text="Edit",
                      command=lambda p=pkg: self._edit_package(p),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                      font=("Segoe UI", 7), relief=tk.FLAT,
                      padx=6, pady=3, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

            tk.Button(btn_frame, text="Delete",
                      command=lambda p=pkg: self._delete_package(p["id"], p["name"]),
                      bg=config.COLOR_BG3, fg="#cc4444",
                      font=("Segoe UI", 7), relief=tk.FLAT,
                      padx=6, pady=3, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

    def _add_package(self):
        PackageDialog(self, package=None, on_save=self._on_package_saved)

    def _edit_package(self, pkg: dict):
        PackageDialog(self, package=pkg, on_save=self._on_package_saved)

    def _on_package_saved(self):
        self._render_packages()
        self.app.set_status("Time package saved")

    def _delete_package(self, pkg_id: int, name: str):
        if messagebox.askyesno("Delete Package", f"Delete package '{name}'?", parent=self):
            db.delete_time_package(pkg_id)
            self._render_packages()
            self.app.set_status(f"Deleted package {name}")


# ============================================================
#  Time Package Dialog (Phase 4B)
# ============================================================

class PackageDialog(tk.Toplevel):

    def __init__(self, parent, package, on_save):
        super().__init__(parent)
        self.package = package
        self.on_save = on_save

        is_new = package is None
        self.title("Add Time Package" if is_new else "Edit Time Package")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        w, h = 360, 320
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build(is_new)

    def _build(self, is_new: bool):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        title = "Add Time Package" if is_new else "Edit Time Package"
        tk.Label(self, text=f"  📦  {title}",
                 font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        lbl_cfg = dict(font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG, anchor="w")
        ent_cfg = dict(font=("Segoe UI", 10), bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                       insertbackground=config.COLOR_TEXT, relief=tk.FLAT, bd=4)

        self._name_var = tk.StringVar(value=self.package["name"] if self.package else "")
        self._dur_var  = tk.StringVar(value=str(self.package["duration_mins"]) if self.package else "60")
        self._price_var= tk.StringVar(value=str(self.package["price"]) if self.package else "60")
        self._desc_var = tk.StringVar(value=self.package.get("description", "") if self.package else "")

        tk.Label(body, text="Package Name (e.g. 2 Hour Pass)", **lbl_cfg).pack(fill=tk.X, pady=(0, 2))
        tk.Entry(body, textvariable=self._name_var, **ent_cfg).pack(fill=tk.X)

        tk.Label(body, text="Duration in Minutes (e.g. 60, 120, 300)", **lbl_cfg).pack(fill=tk.X, pady=(8, 2))
        tk.Entry(body, textvariable=self._dur_var, **ent_cfg).pack(fill=tk.X)

        tk.Label(body, text=f"Bundle Price ({config.CURRENCY})", **lbl_cfg).pack(fill=tk.X, pady=(8, 2))
        tk.Entry(body, textvariable=self._price_var, **ent_cfg).pack(fill=tk.X)

        tk.Label(body, text="Description / Note", **lbl_cfg).pack(fill=tk.X, pady=(8, 2))
        tk.Entry(body, textvariable=self._desc_var, **ent_cfg).pack(fill=tk.X)

        btn_bar = tk.Frame(self, bg=config.COLOR_BG2, pady=10, padx=20)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="Save Package", command=self._save,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT, font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=16, pady=6, cursor="hand2",
                  activebackground=config.COLOR_RED_DARK, activeforeground=config.COLOR_TEXT, bd=0).pack(side=tk.RIGHT)
        tk.Button(btn_bar, text="Cancel", command=self.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=6, cursor="hand2", bd=0).pack(side=tk.RIGHT, padx=(0, 8))

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Package name is required.", parent=self)
            return
        try:
            dur = int(self._dur_var.get())
            price = float(self._price_var.get())
            if dur <= 0 or price < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Enter valid numbers for duration and price.", parent=self)
            return

        desc = self._desc_var.get().strip()
        if self.package:
            db.update_time_package(self.package["id"], name, dur, price, desc)
        else:
            db.create_time_package(name, dur, price, desc)

        self.on_save()
        self.destroy()
