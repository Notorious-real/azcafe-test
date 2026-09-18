# ============================================================
#  AZ Cafe - Settings Panel (Phase 2F)
#  Admin password, shop info, pricing plans, network config
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
import games as games_store
import paths
from server import printer


class SettingsPanel(tk.Frame):

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app         = app
        self._active_tab = None
        self._build_ui()
        self._show_tab("general")

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_tabs()
        self._content = tk.Frame(self, bg=config.COLOR_BG)
        self._content.pack(fill=tk.BOTH, expand=True, padx=0)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=config.COLOR_RED,
                 width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  SETTINGS",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED,
                 bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

    def _build_tabs(self):
        tab_bar = tk.Frame(self, bg=config.COLOR_BG2)
        tab_bar.pack(fill=tk.X)
        self._tab_btns = {}
        tabs = [
            ("general",  "🏪  General"),
            ("security", "🔐  Security"),
            ("pricing",  "💰  Pricing"),
            ("printer",  "🖨  Printer"),
            ("games",    "🎮  Games"),
            ("data",     "💾  Data & Backup"),
            ("network",  "🌐  Network"),
        ]
        for key, label in tabs:
            btn = tk.Label(tab_bar, text=label,
                           font=("Segoe UI", 9),
                           fg=config.COLOR_TEXT_DIM,
                           bg=config.COLOR_BG2,
                           padx=16, pady=8,
                           cursor="hand2")
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda e, k=key: self._show_tab(k))
            self._tab_btns[key] = btn
        tk.Frame(self, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X)

    def _show_tab(self, key: str):
        if self._active_tab and self._active_tab in self._tab_btns:
            self._tab_btns[self._active_tab].config(
                fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)
        self._active_tab = key
        self._tab_btns[key].config(
            fg=config.COLOR_RED_BRIGHT, bg=config.COLOR_BG3)
        for w in self._content.winfo_children():
            w.destroy()
        if key == "general":
            self._build_general()
        elif key == "security":
            self._build_security()
        elif key == "pricing":
            self._build_pricing()
        elif key == "printer":
            self._build_printer()
        elif key == "games":
            self._build_games()
        elif key == "data":
            self._build_data()
        elif key == "network":
            self._build_network()

    # ── Shared helpers ────────────────────────────────────────

    def _section(self, title: str):
        tk.Label(self._content, text=title,
                 font=("Segoe UI", 10, "bold"),
                 fg=config.COLOR_RED,
                 bg=config.COLOR_BG,
                 anchor="w", padx=24, pady=(12)).pack(fill=tk.X)
        tk.Frame(self._content, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X, padx=24)

    def _field(self, parent, label: str, var,
               show=None, width=28, readonly=False):
        row = tk.Frame(parent, bg=config.COLOR_BG, padx=24, pady=4)
        row.pack(fill=tk.X)
        tk.Label(row, text=label,
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG,
                 width=22, anchor="w").pack(side=tk.LEFT)
        kw = dict(textvariable=var,
                  font=("Segoe UI", 10),
                  bg=config.COLOR_BG3 if not readonly else config.COLOR_BG2,
                  fg=config.COLOR_TEXT,
                  insertbackground=config.COLOR_TEXT,
                  relief=tk.FLAT, bd=4, width=width)
        if show:
            kw["show"] = show
        if readonly:
            kw["state"] = "readonly"
        tk.Entry(row, **kw).pack(side=tk.LEFT)
        return row

    def _save_btn(self, parent, command):
        tk.Button(parent, text="💾  Save",
                  command=command,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=20, pady=7,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT
                  ).pack(anchor="w", padx=24, pady=(12, 0))

    # ── General Tab ───────────────────────────────────────────

    def _build_general(self):
        self._section("Shop Information")

        body = tk.Frame(self._content, bg=config.COLOR_BG)
        body.pack(fill=tk.X, pady=8)

        self._shop_name  = tk.StringVar(
            value=db.get_setting("shop_name", config.APP_NAME))
        self._low_time   = tk.StringVar(
            value=db.get_setting("low_time_warning", "5"))
        self._currency   = tk.StringVar(value=config.CURRENCY)
        self._sound      = tk.BooleanVar(value=db.get_bool_setting("sound_enabled", True))
        self._kiosk      = tk.BooleanVar(value=db.get_bool_setting("kiosk_mode", True))
        self._taskmgr    = tk.BooleanVar(value=db.get_bool_setting("lock_task_manager", False))

        self._field(body, "Shop Name",              self._shop_name)
        self._field(body, "Low Time Warning (min)", self._low_time)
        self._field(body, "Currency Symbol",        self._currency, readonly=True)

        flags = tk.Frame(body, bg=config.COLOR_BG, padx=24, pady=4)
        flags.pack(fill=tk.X)
        for text, var in (
                ("Play sounds on client PCs (start, low time, time up, messages)", self._sound),
                ("Kiosk mode: block Windows/Alt-Tab keys while locked", self._kiosk),
                ("Also disable Task Manager on client PCs (per-user policy)", self._taskmgr)):
            tk.Checkbutton(flags, text=text, variable=var, bg=config.COLOR_BG,
                           fg=config.COLOR_TEXT, selectcolor=config.COLOR_BG3,
                           activebackground=config.COLOR_BG, font=("Segoe UI", 9),
                           cursor="hand2").pack(anchor="w")

        tk.Label(body,
                 text="  The currency symbol lives in config.py (one place for the whole "
                      "system, receipts included).",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, anchor="w", padx=24).pack(fill=tk.X)
        tk.Label(body,
                 text="  Low-time warnings, sounds and kiosk mode are pushed to clients "
                      "the next time they connect.",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, anchor="w", padx=24).pack(fill=tk.X)

        self._save_btn(body, self._save_general)

        # ── App info ──────────────────────────────────────────
        self._section("App Information")

        info_frame = tk.Frame(self._content, bg=config.COLOR_BG,
                              padx=24, pady=8)
        info_frame.pack(fill=tk.X)

        infos = [
            ("App Name",    config.APP_NAME),
            ("Version",     config.APP_VERSION),
            ("Server Port", str(config.SERVER_PORT)),
            ("Database",    "azcafe.db  (SQLite)"),
        ]
        for label, value in infos:
            row = tk.Frame(info_frame, bg=config.COLOR_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label,
                     font=("Segoe UI", 9),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     width=22, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value,
                     font=("Segoe UI", 9, "bold"),
                     fg=config.COLOR_TEXT,
                     bg=config.COLOR_BG).pack(side=tk.LEFT)

    def _save_general(self):
        db.set_setting("shop_name", self._shop_name.get().strip())
        db.set_setting("low_time_warning", self._low_time.get().strip())
        db.set_setting("sound_enabled", "1" if self._sound.get() else "0")
        db.set_setting("kiosk_mode", "1" if self._kiosk.get() else "0")
        db.set_setting("lock_task_manager", "1" if self._taskmgr.get() else "0")
        self._reload_server_settings()
        messagebox.showinfo("Saved", "General settings saved.\n\n"
                                     "These are applied to PCs as they connect.",
                            parent=self)
        self.app.set_status("Settings saved")

    def _reload_server_settings(self):
        server = getattr(self.app, "server", None)
        if server and hasattr(server, "reload_settings"):
            server.reload_settings()

    # ── Security Tab ──────────────────────────────────────────

    def _build_security(self):
        self._section("Change Admin Password")

        body = tk.Frame(self._content, bg=config.COLOR_BG)
        body.pack(fill=tk.X, pady=8)

        self._cur_pwd  = tk.StringVar()
        self._new_pwd  = tk.StringVar()
        self._conf_pwd = tk.StringVar()

        self._field(body, "Current Password",  self._cur_pwd,  show="●")
        self._field(body, "New Password",      self._new_pwd,  show="●")
        self._field(body, "Confirm Password",  self._conf_pwd, show="●")

        self._save_btn(body, self._save_password)

        # ── Auto-lock ─────────────────────────────────────────
        self._section("Client Security")

        sec_body = tk.Frame(self._content, bg=config.COLOR_BG,
                            padx=24, pady=8)
        sec_body.pack(fill=tk.X)

        self._auto_lock = tk.BooleanVar(
            value=db.get_setting("auto_lock", "1") == "1"
        )
        tk.Checkbutton(
            sec_body,
            text="Auto-lock client screen when session ends",
            variable=self._auto_lock,
            bg=config.COLOR_BG,
            fg=config.COLOR_TEXT,
            selectcolor=config.COLOR_BG3,
            activebackground=config.COLOR_BG,
            font=("Segoe UI", 9),
            cursor="hand2"
        ).pack(anchor="w")

        tk.Button(
            sec_body, text="💾  Save Security Settings",
            command=self._save_security,
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=20, pady=7,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT
        ).pack(anchor="w", pady=(12, 0))

    def _save_password(self):
        cur  = self._cur_pwd.get()
        new  = self._new_pwd.get()
        conf = self._conf_pwd.get()

        if not db.verify_admin_password(cur):
            messagebox.showerror("Error",
                                 "Current password is incorrect.",
                                 parent=self)
            return
        if not new:
            messagebox.showerror("Error",
                                 "New password cannot be empty.",
                                 parent=self)
            return
        if new != conf:
            messagebox.showerror("Error",
                                 "Passwords do not match.",
                                 parent=self)
            return

        db.set_admin_password(new)          # salted scrypt hash
        self._cur_pwd.set("")
        self._new_pwd.set("")
        self._conf_pwd.set("")
        messagebox.showinfo("Saved",
                            "Admin password changed successfully.\n"
                            "It applies to this admin app and to client unlocks.",
                            parent=self)
        self.app.set_status("Admin password changed")

    def _save_security(self):
        db.set_setting("auto_lock",
                       "1" if self._auto_lock.get() else "0")
        self._reload_server_settings()
        messagebox.showinfo("Saved",
                            "Security settings saved.",
                            parent=self)


    # ── Printer Tab (7B) ──────────────────────────────────────

    def _build_printer(self):
        self._section("Receipt Printer")

        body = tk.Frame(self._content, bg=config.COLOR_BG, padx=24, pady=8)
        body.pack(fill=tk.X)

        if not printer.is_supported():
            tk.Label(body, text="Receipt printing is available on Windows only.",
                     font=("Segoe UI", 9), fg=config.COLOR_YELLOW,
                     bg=config.COLOR_BG, anchor="w").pack(fill=tk.X)
        else:
            tk.Label(body, text="Choose the printer used for session receipts:",
                     font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG, anchor="w").pack(fill=tk.X, pady=(0, 6))

        self._auto_print = tk.BooleanVar(
            value=db.get_bool_setting("auto_print_receipt", True))
        tk.Checkbutton(body,
                       text="Automatically print a receipt when a session ends",
                       variable=self._auto_print, bg=config.COLOR_BG,
                       fg=config.COLOR_TEXT, selectcolor=config.COLOR_BG3,
                       activebackground=config.COLOR_BG, font=("Segoe UI", 9),
                       cursor="hand2").pack(anchor="w", pady=(0, 8))

        current = db.get_setting("receipt_printer", "")
        self._printer_var = tk.StringVar(
            value=current or "(system default printer)")
        self._printer_names = []
        self._printer_menu = tk.OptionMenu(
            body, self._printer_var,
            *(["(system default printer)"] + self._printer_names))
        self._printer_menu.config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                  font=("Segoe UI", 9), relief=tk.FLAT, bd=0,
                                  activebackground=config.COLOR_RED,
                                  activeforeground=config.COLOR_TEXT,
                                  highlightthickness=0)
        self._printer_menu["menu"].config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                          activebackground=config.COLOR_RED,
                                          activeforeground=config.COLOR_TEXT)
        self._printer_menu.pack(anchor="w", fill=tk.X)

        buttons = tk.Frame(body, bg=config.COLOR_BG)
        buttons.pack(fill=tk.X, pady=(10, 0))

        tk.Button(buttons, text="🔄  Refresh printers", command=self._refresh_printers,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=5, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT)
        tk.Button(buttons, text="🧾  Test print", command=self._test_print,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=5, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="💾  Save printer", command=self._save_printer,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=14, pady=5,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=(8, 0))

        self._printer_status = tk.Label(body, text="", font=("Segoe UI", 8),
                                        fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                                        anchor="w", wraplength=620,
                                        justify=tk.LEFT)
        self._printer_status.pack(fill=tk.X, pady=(10, 0))
        self._refresh_printers(initial=True)

    def _refresh_printers(self, initial: bool = False):
        names = printer.list_printers()
        menu = self._printer_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="(system default printer)",
                         command=lambda: self._printer_var.set("(system default printer)"))
        for name in names:
            menu.add_command(label=name, command=lambda n=name: self._printer_var.set(n))

        default = printer.default_printer_name()
        message = f"Found {len(names)} printer(s)."
        if default:
            message += f"  Windows default: {default}"
        if not printer.is_supported():
            message = printer.platform_note()
        if initial and names and not db.get_setting("receipt_printer", ""):
            self._printer_var.set("(system default printer)")
        self._printer_status.config(text=message)

    def _save_printer(self):
        chosen = self._printer_var.get()
        printer_name = "" if chosen.startswith("(") else chosen
        db.set_setting("receipt_printer", printer_name)
        db.set_setting("auto_print_receipt", "1" if self._auto_print.get() else "0")
        self._reload_server_settings()
        messagebox.showinfo("Saved", "Printer settings saved.", parent=self)
        self.app.set_status("Printer settings saved")

    def _test_print(self):
        chosen = self._printer_var.get()
        printer_name = "" if chosen.startswith("(") else chosen
        shop = db.get_setting("shop_name", config.APP_NAME)
        ok, message = printer.print_text(
            printer.build_receipt_text(
                {"pc_name": "TEST", "user": "Test print", "session_id": "test",
                 "payment_type": "cash", "booked_mins": 60, "used_secs": 60,
                 "prepaid": 60, "charged": 60, "refund": 0},
                shop_name=shop, currency=db.get_setting("currency", config.CURRENCY)),
            printer_name=printer_name)
        if ok:
            messagebox.showinfo("Test print", message, parent=self)
        else:
            messagebox.showwarning("Test print", message, parent=self)

    # ── Games Tab (6.5C) ──────────────────────────────────────

    def _build_games(self):
        self._section("Game Launcher Titles")
        body = tk.Frame(self._content, bg=config.COLOR_BG, padx=24, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body,
                 text=f"Stored in {games_store.games_path()} — the client reads this file, "
                      "so no rebuild is needed.",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, anchor="w", wraplength=640,
                 justify=tk.LEFT).pack(fill=tk.X)

        self._games_list = tk.Listbox(body, font=("Consolas", 9),
                                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                      selectbackground=config.COLOR_RED,
                                      selectforeground=config.COLOR_TEXT,
                                      relief=tk.FLAT, bd=0, height=10)
        self._games_list.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        self._render_games()

        form = tk.Frame(body, bg=config.COLOR_BG)
        form.pack(fill=tk.X)
        self._game_name = tk.StringVar()
        self._game_cmd = tk.StringVar()
        self._game_cat = tk.StringVar(value="Other")
        for label, var in (("Name", self._game_name), ("Command / path", self._game_cmd)):
            row = tk.Frame(form, bg=config.COLOR_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, font=("Segoe UI", 9), width=16,
                     fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                     anchor="w").pack(side=tk.LEFT)
            tk.Entry(row, textvariable=var, font=("Segoe UI", 9),
                     bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                     insertbackground=config.COLOR_TEXT, relief=tk.FLAT,
                     bd=4).pack(side=tk.LEFT, fill=tk.X, expand=True)
        cat_row = tk.Frame(form, bg=config.COLOR_BG)
        cat_row.pack(fill=tk.X, pady=2)
        tk.Label(cat_row, text="Category", font=("Segoe UI", 9), width=16,
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(side=tk.LEFT)
        tk.OptionMenu(cat_row, self._game_cat, *games_store.CATEGORIES).pack(side=tk.LEFT)

        buttons = tk.Frame(body, bg=config.COLOR_BG)
        buttons.pack(fill=tk.X, pady=(10, 0))
        for text, command in (
                ("➕  Add", self._add_game),
                ("✏️  Update selected", self._update_game),
                ("🗑  Remove", self._remove_game),
                ("↺  Restore defaults", self._reset_games)):
            tk.Button(buttons, text=text, command=command,
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                      font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5,
                      cursor="hand2", bd=0,
                      activebackground=config.COLOR_RED,
                      activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(body, text="Steam titles can use  steam://rungameid/730  style commands.",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(8, 0))

    def _render_games(self):
        self._game_cache = games_store.load_games()
        self._games_list.delete(0, tk.END)
        for game in self._game_cache:
            available = "✓" if games_store.game_available(game) else "!"
            self._games_list.insert(tk.END,
                                    f" {available} {game.get('name','')}  ·  "
                                    f"{game.get('category','')}  ·  {game.get('cmd','')}")

    def _load_selected_game(self):
        selection = self._games_list.curselection()
        if not selection:
            return None
        game = self._game_cache[selection[0]]
        self._game_name.set(game.get("name", ""))
        self._game_cmd.set(game.get("cmd", ""))
        self._game_cat.set(game.get("category", "Other"))
        return game

    def _add_game(self):
        game = {"name": self._game_name.get().strip(),
                "cmd": self._game_cmd.get().strip(),
                "category": self._game_cat.get(), "icon": "🎮"}
        problem = games_store.validate_game(game)
        if problem:
            messagebox.showerror("Games", problem, parent=self)
            return
        self._game_cache.append(game)
        games_store.save_games(self._game_cache)
        self._render_games()
        self.app.set_status(f"Added {game['name']} to the launcher")

    def _update_game(self):
        game = self._load_selected_game()
        if not game:
            messagebox.showinfo("Games", "Select a game to update.", parent=self)
            return
        game.update({"name": self._game_name.get().strip(),
                     "cmd": self._game_cmd.get().strip(),
                     "category": self._game_cat.get()})
        problem = games_store.validate_game(game)
        if problem:
            messagebox.showerror("Games", problem, parent=self)
            return
        games_store.save_games(self._game_cache)
        self._render_games()
        self.app.set_status(f"Updated {game['name']}")

    def _remove_game(self):
        game = self._load_selected_game()
        if not game:
            messagebox.showinfo("Games", "Select a game to remove.", parent=self)
            return
        if not messagebox.askyesno("Games", f"Remove {game.get('name')}?", parent=self):
            return
        self._game_cache = [g for g in self._game_cache if g is not game]
        games_store.save_games(self._game_cache)
        self._render_games()
        self.app.set_status(f"Removed {game.get('name')}")

    def _reset_games(self):
        if not messagebox.askyesno("Games", "Restore the built-in game list?", parent=self):
            return
        games_store.reset_games()
        self._render_games()
        self.app.set_status("Game list restored to defaults")

    # ── Data & Backup Tab ─────────────────────────────────────

    def _build_data(self):
        self._section("Database")
        info = db.db_info()
        body = tk.Frame(self._content, bg=config.COLOR_BG, padx=24, pady=8)
        body.pack(fill=tk.X)

        rows = [
            ("Folder", info["path"].rsplit(os.sep, 1)[0]),
            ("Database file", os.path.basename(info["path"])),
            ("Size", f"{info['size_bytes'] / 1024:.0f} KB"),
            ("Members", str(info["counts"].get("members", 0))),
            ("PCs", str(info["counts"].get("pcs", 0))),
            ("Sessions", str(info["counts"].get("sessions", 0))),
            ("Ledger entries", str(info["counts"].get("transactions", 0))),
        ]
        for label, value in rows:
            row = tk.Frame(body, bg=config.COLOR_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, font=("Segoe UI", 9), width=18,
                     fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                     anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value, font=("Segoe UI", 9, "bold"),
                     fg=config.COLOR_TEXT, bg=config.COLOR_BG,
                     anchor="w").pack(side=tk.LEFT)

        buttons = tk.Frame(body, bg=config.COLOR_BG)
        buttons.pack(fill=tk.X, pady=(12, 0))
        tk.Button(buttons, text="💾  Back up now", command=self._backup_now,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=14, pady=6,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT)
        tk.Button(buttons, text="📂  Open data folder", command=self._open_data_folder,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=6, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="🧹  Prune old backups", command=self._prune_backups,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=6, cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(body,
                 text="Backups are written to the backups folder next to the database.\n"
                      "The data folder is %PROGRAMDATA%\\AZCafe on installed machines, "
                      "so updating the app never touches your data.",
                 font=("Segoe UI", 8), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w", justify=tk.LEFT).pack(fill=tk.X, pady=(12, 0))

    def _backup_now(self):
        try:
            path = db.backup_db()
        except OSError as exc:
            messagebox.showerror("Backup", f"Backup failed:\n{exc}", parent=self)
            return
        messagebox.showinfo("Backup", f"Backup written to:\n{path}", parent=self)
        self.app.set_status("Database backed up")

    def _open_data_folder(self):
        folder = paths.data_dir()
        try:
            os.startfile(folder)                               # type: ignore[attr-defined]
        except Exception:                                      # noqa: BLE001
            messagebox.showinfo("Data folder", folder, parent=self)

    def _prune_backups(self):
        db.prune_backups(keep=30)
        messagebox.showinfo("Backups", "Kept the 30 most recent backups.", parent=self)

    # ── Pricing Tab ───────────────────────────────────────────

    def _build_pricing(self):
        self._section("Pricing Plans")

        # Toolbar
        plan_bar = tk.Frame(self._content, bg=config.COLOR_BG,
                            padx=24, pady=8)
        plan_bar.pack(fill=tk.X)

        tk.Button(
            plan_bar, text="+ Add Plan",
            command=self._add_plan,
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.LEFT)

        # Plans list
        self._plans_frame = tk.Frame(self._content, bg=config.COLOR_BG)
        self._plans_frame.pack(fill=tk.BOTH, expand=True, padx=24)
        self._render_plans()

    def _render_plans(self):
        for w in self._plans_frame.winfo_children():
            w.destroy()

        plans = db.get_all_pricing_plans()

        if not plans:
            tk.Label(self._plans_frame,
                     text="No pricing plans. Click + Add Plan.",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     pady=20).pack()
            return

        # Header
        hdr = tk.Frame(self._plans_frame, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X, pady=(0, 4))
        for text, w in [("Plan Name", 20), ("Rate/Hour", 12),
                        ("Min Minutes", 12), ("Default", 8), ("", 10)]:
            tk.Label(hdr, text=text,
                     font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     width=w, anchor="w",
                     padx=8, pady=6).pack(side=tk.LEFT)

        for plan in plans:
            self._plan_row(plan)

    def _plan_row(self, plan: dict):
        row = tk.Frame(self._plans_frame, bg=config.COLOR_BG2)
        row.pack(fill=tk.X, pady=1)

        is_default = "✓ Default" if plan["is_default"] else ""
        def_color  = config.COLOR_GREEN if plan["is_default"] \
                     else config.COLOR_TEXT_DIM

        for text, w, color in [
            (plan["name"],              20, config.COLOR_TEXT),
            (f"{config.CURRENCY} {plan['rate_per_hour']:.0f}", 12, config.COLOR_RED_BRIGHT),
            (f"{plan['min_minutes']}m", 12, config.COLOR_TEXT_DIM),
            (is_default,                8,  def_color),
        ]:
            tk.Label(row, text=text,
                     font=("Segoe UI", 9),
                     fg=color, bg=config.COLOR_BG2,
                     width=w, anchor="w",
                     padx=8, pady=7).pack(side=tk.LEFT)

        # Action buttons
        btn_frame = tk.Frame(row, bg=config.COLOR_BG2)
        btn_frame.pack(side=tk.LEFT)

        if not plan["is_default"]:
            tk.Button(
                btn_frame, text="Set Default",
                command=lambda p=plan: self._set_default(p["id"]),
                bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                font=("Segoe UI", 7), relief=tk.FLAT,
                padx=6, pady=3, cursor="hand2", bd=0
            ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            btn_frame, text="Edit",
            command=lambda p=plan: self._edit_plan(p),
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 7), relief=tk.FLAT,
            padx=6, pady=3, cursor="hand2", bd=0
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            btn_frame, text="Delete",
            command=lambda p=plan: self._delete_plan(p["id"], p["name"]),
            bg=config.COLOR_BG3, fg="#cc4444",
            font=("Segoe UI", 7), relief=tk.FLAT,
            padx=6, pady=3, cursor="hand2", bd=0
        ).pack(side=tk.LEFT, padx=2)

    def _add_plan(self):
        PlanDialog(self, plan=None, on_save=self._on_plan_saved)

    def _edit_plan(self, plan: dict):
        PlanDialog(self, plan=plan, on_save=self._on_plan_saved)

    def _on_plan_saved(self):
        self._render_plans()
        self.app.set_status("Pricing plan saved")

    def _set_default(self, plan_id: int):
        db.set_default_plan(plan_id)
        self._render_plans()

    def _delete_plan(self, plan_id: int, name: str):
        if messagebox.askyesno("Delete Plan",
                               f"Delete plan '{name}'?",
                               parent=self):
            db.delete_pricing_plan(plan_id)
            self._render_plans()

    # ── Network Tab ───────────────────────────────────────────

    def _build_network(self):
        self._section("Server Network Info")

        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "Unknown"

        body = tk.Frame(self._content, bg=config.COLOR_BG,
                        padx=24, pady=12)
        body.pack(fill=tk.X)

        infos = [
            ("Server IP (LAN)",  local_ip),
            ("Port",             str(config.SERVER_PORT)),
            ("Max Clients",      "Unlimited"),
        ]
        for label, value in infos:
            row = tk.Frame(body, bg=config.COLOR_BG)
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=label,
                     font=("Segoe UI", 9),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     width=22, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=value,
                     font=("Segoe UI", 11, "bold"),
                     fg=config.COLOR_RED_BRIGHT,
                     bg=config.COLOR_BG).pack(side=tk.LEFT)

        # Instruction box
        self._section("Client Setup Instructions")

        inst = tk.Frame(self._content, bg=config.COLOR_BG3,
                        padx=16, pady=12)
        inst.pack(fill=tk.X, padx=24, pady=8)

        tk.Label(
            inst,
            text="Put this in the client's client_config.json (no rebuild needed):",
            font=("Segoe UI", 9),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG3
        ).pack(anchor="w")

        ip_row = tk.Frame(inst, bg=config.COLOR_BG3)
        ip_row.pack(fill=tk.X, pady=(4, 0))

        json_line = '{ "server_ip": "%s", "server_port": %s }' % (local_ip, config.SERVER_PORT)
        ip_lbl = tk.Label(
            ip_row,
            text=json_line,
            font=("Courier", 10, "bold"),
            fg=config.COLOR_GREEN,
            bg=config.COLOR_BG3
        )
        ip_lbl.pack(side=tk.LEFT)

        tk.Button(
            ip_row, text="Copy",
            command=lambda: self._copy(json_line),
            bg=config.COLOR_BG2, fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 8), relief=tk.FLAT,
            padx=8, pady=2, cursor="hand2", bd=0
        ).pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(
            inst,
            text="The installer writes this file automatically.\n"
                 "Clients also read the AZCAFE_SERVER_IP environment variable.\n"
                 "Make sure the port is allowed in Windows Firewall.",
            font=("Segoe UI", 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG3
        ).pack(anchor="w", pady=(8, 0))

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status("Copied to clipboard")


# ============================================================
#  Pricing Plan Dialog
# ============================================================

class PlanDialog(tk.Toplevel):

    def __init__(self, parent, plan, on_save):
        super().__init__(parent)
        self.plan    = plan
        self.on_save = on_save

        is_new = plan is None
        self.title("Add Pricing Plan" if is_new else "Edit Pricing Plan")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        w, h = 340, 280
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build(is_new)

    def _build(self, is_new: bool):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        title = "Add Pricing Plan" if is_new else "Edit Pricing Plan"
        tk.Label(self, text=f"  {title}",
                 font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=20, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        lbl_cfg = dict(font=("Segoe UI", 9),
                       fg=config.COLOR_TEXT_DIM,
                       bg=config.COLOR_BG, anchor="w")
        ent_cfg = dict(font=("Segoe UI", 10),
                       bg=config.COLOR_BG3,
                       fg=config.COLOR_TEXT,
                       insertbackground=config.COLOR_TEXT,
                       relief=tk.FLAT, bd=4)

        self._name_var = tk.StringVar(
            value=self.plan["name"] if self.plan else "")
        self._rate_var = tk.StringVar(
            value=str(self.plan["rate_per_hour"]) if self.plan else "60")
        self._min_var  = tk.StringVar(
            value=str(self.plan["min_minutes"])  if self.plan else "0")

        tk.Label(body, text="Plan Name", **lbl_cfg).pack(
            fill=tk.X, pady=(0, 2))
        tk.Entry(body, textvariable=self._name_var,
                 **ent_cfg).pack(fill=tk.X)

        tk.Label(body,
                 text=f"Rate per Hour ({config.CURRENCY})",
                 **lbl_cfg).pack(fill=tk.X, pady=(10, 2))
        tk.Entry(body, textvariable=self._rate_var,
                 **ent_cfg).pack(fill=tk.X)

        tk.Label(body, text="Minimum Minutes (0 = none)",
                 **lbl_cfg).pack(fill=tk.X, pady=(10, 2))
        tk.Entry(body, textvariable=self._min_var,
                 **ent_cfg).pack(fill=tk.X)

        # Buttons
        tk.Frame(self, bg=config.COLOR_BORDER,
                 height=1).pack(fill=tk.X)
        btn_bar = tk.Frame(self, bg=config.COLOR_BG2,
                           pady=10, padx=20)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="Save",
                  command=self._save,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=18, pady=7,
                  cursor="hand2",
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT,
                  bd=0).pack(side=tk.RIGHT)

        tk.Button(btn_bar, text="Cancel",
                  command=self.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=12, pady=7, cursor="hand2",
                  bd=0).pack(side=tk.RIGHT, padx=(0, 8))

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror("Error",
                                 "Plan name is required.",
                                 parent=self)
            return
        try:
            rate = float(self._rate_var.get())
            mins = int(self._min_var.get())
        except ValueError:
            messagebox.showerror("Error",
                                 "Enter valid numbers for rate and minutes.",
                                 parent=self)
            return

        if self.plan:
            db.update_pricing_plan(self.plan["id"], name, rate, mins)
        else:
            db.create_pricing_plan(name, rate, mins)

        self.on_save()
        self.destroy()
