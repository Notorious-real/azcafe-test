# ============================================================
#  AZ Cafe - Members Panel (Phase 2D)
#  Full member management — add, edit, delete, top up balance
# ============================================================

import tkinter as tk
from tkinter import messagebox, simpledialog
import sys
import os


if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config
import database as db
from server import member_import


class MembersPanel(tk.Frame):
    """
    Full members management panel.
    Left: searchable member list
    Right: member detail / edit form
    """

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.app            = app
        self._selected_id   = None
        self._members       = []
        self._build_ui()
        self._load_members()

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        # Toolbar
        self._build_toolbar()

        # Body — split left/right
        body = tk.Frame(self, bg=config.COLOR_BG)
        body.pack(fill=tk.BOTH, expand=True)

        self._build_list(body)
        tk.Frame(body, bg=config.COLOR_BORDER,
                 width=1).pack(side=tk.LEFT, fill=tk.Y)
        self._build_detail(body)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Frame(bar, bg=config.COLOR_RED,
                 width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  MEMBERS",
                 font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED,
                 bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        btn_cfg = dict(font=("Segoe UI", 8, "bold"),
                       bg=config.COLOR_RED,
                       fg=config.COLOR_TEXT,
                       relief=tk.FLAT, padx=12, pady=4,
                       cursor="hand2",
                       activebackground=config.COLOR_RED_DARK,
                       activeforeground=config.COLOR_TEXT, bd=0)

        tk.Button(bar, text="+ Add Member",
                  command=self._open_add_dialog,
                  **btn_cfg).pack(side=tk.RIGHT, padx=8, pady=5)

        tk.Button(bar, text="📄 Import CSV",
                  command=self._import_csv,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 8, "bold"),
                  relief=tk.FLAT, padx=12, pady=4,
                  cursor="hand2", bd=0,
                  activebackground=config.COLOR_RED,
                  activeforeground=config.COLOR_TEXT).pack(side=tk.RIGHT, padx=8, pady=5)

    # ── Left: Member List ─────────────────────────────────────

    def _build_list(self, parent):
        frame = tk.Frame(parent, bg=config.COLOR_BG, width=280)
        frame.pack(side=tk.LEFT, fill=tk.Y)
        frame.pack_propagate(False)

        # Search bar
        search_row = tk.Frame(frame, bg=config.COLOR_BG2, padx=8, pady=6)
        search_row.pack(fill=tk.X)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_members())

        tk.Entry(
            search_row,
            textvariable=self._search_var,
            font=("Segoe UI", 9),
            bg=config.COLOR_BG3,
            fg=config.COLOR_TEXT,
            insertbackground=config.COLOR_TEXT,
            relief=tk.FLAT, bd=4
        ).pack(fill=tk.X)

        tk.Label(search_row, text="Search members...",
                 font=("Segoe UI", 7),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2).pack(anchor="w")

        # Member listbox
        list_frame = tk.Frame(frame, bg=config.COLOR_BG)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  bg=config.COLOR_BG2,
                                  troughcolor=config.COLOR_BG,
                                  activebackground=config.COLOR_RED)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(
            list_frame,
            font=("Segoe UI", 9),
            bg=config.COLOR_BG,
            fg=config.COLOR_TEXT,
            selectbackground=config.COLOR_RED,
            selectforeground=config.COLOR_TEXT,
            relief=tk.FLAT, bd=0,
            activestyle="none",
            yscrollcommand=scrollbar.set
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # Member count
        self._count_var = tk.StringVar(value="0 members")
        tk.Label(frame, textvariable=self._count_var,
                 font=("Segoe UI", 8),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2,
                 pady=4).pack(fill=tk.X)

    # ── Right: Member Detail ──────────────────────────────────

    def _build_detail(self, parent):
        self._detail_frame = tk.Frame(parent, bg=config.COLOR_BG)
        self._detail_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Show placeholder until a member is selected
        self._placeholder = tk.Label(
            self._detail_frame,
            text="Select a member to view details\nor click + Add Member",
            font=("Segoe UI", 10),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _show_detail(self, member: dict):
        """Show member detail/edit panel."""
        for w in self._detail_frame.winfo_children():
            w.destroy()

        self._selected_id = member["id"]

        # ── Header ────────────────────────────────────────────
        header = tk.Frame(self._detail_frame, bg=config.COLOR_BG2,
                          padx=20, pady=12)
        header.pack(fill=tk.X)

        tk.Label(header,
                 text=member["name"],
                 font=("Segoe UI", 14, "bold"),
                 fg=config.COLOR_TEXT,
                 bg=config.COLOR_BG2).pack(anchor="w")

        tk.Label(header,
                 text=f"@{member['username']}",
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2).pack(anchor="w")

        joined = member.get("created_at", "")[:10]
        tk.Label(header,
                 text=f"Member since: {joined}",
                 font=("Segoe UI", 8),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2).pack(anchor="w")

        tk.Frame(self._detail_frame,
                 bg=config.COLOR_RED, height=2).pack(fill=tk.X)

        body = tk.Frame(self._detail_frame, bg=config.COLOR_BG,
                        padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Balance card ──────────────────────────────────────
        bal_card = tk.Frame(body, bg=config.COLOR_BG3, padx=16, pady=12)
        bal_card.pack(fill=tk.X, pady=(0, 16))

        bal_row = tk.Frame(bal_card, bg=config.COLOR_BG3)
        bal_row.pack(fill=tk.X)

        tk.Label(bal_row, text="Current Balance",
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG3).pack(side=tk.LEFT)

        self._bal_var = tk.StringVar(
            value=f"{config.CURRENCY} {member['balance']:.0f}"
        )
        tk.Label(bal_row,
                 textvariable=self._bal_var,
                 font=("Segoe UI", 18, "bold"),
                 fg=config.COLOR_GREEN,
                 bg=config.COLOR_BG3).pack(side=tk.RIGHT)

        # Total spent
        tk.Label(bal_card,
                 text=f"Total spent: {config.CURRENCY} {member['total_spent']:.0f}",
                 font=("Segoe UI", 8),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG3).pack(anchor="e")

        # Balance action buttons
        btn_frame = tk.Frame(bal_card, bg=config.COLOR_BG3)
        btn_frame.pack(anchor="w", pady=(10, 0))

        tk.Button(
            btn_frame, text="+ Top Up",
            command=lambda: self._topup(member),
            bg=config.COLOR_GREEN, fg="black",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", bd=0,
            activebackground="#009933",
            activeforeground="white"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            btn_frame, text="- Remove Balance",
            command=lambda: self._remove_balance(member),
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.LEFT)

        # ── Edit fields ───────────────────────────────────────
        def _lbl(text):
            tk.Label(body, text=text,
                     font=("Segoe UI", 9),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     anchor="w").pack(fill=tk.X, pady=(8, 2))

        def _ent(var):
            e = tk.Entry(body, textvariable=var,
                         font=("Segoe UI", 10),
                         bg=config.COLOR_BG3,
                         fg=config.COLOR_TEXT,
                         insertbackground=config.COLOR_TEXT,
                         relief=tk.FLAT, bd=4)
            e.pack(fill=tk.X)
            return e

        _lbl("Full Name")
        name_var = tk.StringVar(value=member["name"])
        _ent(name_var)

        _lbl("Username")
        uname_var = tk.StringVar(value=member["username"])
        _ent(uname_var)

        _lbl("Notes")
        notes_var = tk.StringVar(value=member.get("notes") or "")
        _ent(notes_var)

        _lbl("New Password (leave blank to keep current)")
        pwd_var = tk.StringVar()
        pwd_ent = tk.Entry(body, textvariable=pwd_var,
                           show="●",
                           font=("Segoe UI", 10),
                           bg=config.COLOR_BG3,
                           fg=config.COLOR_TEXT,
                           insertbackground=config.COLOR_TEXT,
                           relief=tk.FLAT, bd=4)
        pwd_ent.pack(fill=tk.X)

        # ── Action buttons ────────────────────────────────────
        btn_row = tk.Frame(body, bg=config.COLOR_BG)
        btn_row.pack(fill=tk.X, pady=(16, 0))

        tk.Button(
            btn_row, text="💾  Save Changes",
            command=lambda: self._save_member(
                member["id"], name_var.get(),
                uname_var.get(), notes_var.get(),
                pwd_var.get()
            ),
            bg=config.COLOR_RED, fg=config.COLOR_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", bd=0,
            activebackground=config.COLOR_RED_DARK,
            activeforeground=config.COLOR_TEXT
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_row, text="🕒  Session History",
            command=lambda: self._show_history(member),
            bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", bd=0
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(
            btn_row, text="🗑  Delete",
            command=lambda: self._delete_member(member["id"], member["name"]),
            bg=config.COLOR_BG3, fg="#cc4444",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", bd=0
        ).pack(side=tk.RIGHT)

    # ── Load / Filter ─────────────────────────────────────────

    def _load_members(self):
        self._members = db.get_all_members()
        self._render_list(self._members)

    def _filter_members(self):
        q = self._search_var.get().strip().lower()
        if not q:
            self._render_list(self._members)
        else:
            filtered = [
                m for m in self._members
                if q in m["name"].lower() or q in m["username"].lower()
            ]
            self._render_list(filtered)

    def _render_list(self, members: list):
        self._listbox.delete(0, tk.END)
        self._filtered = members
        for m in members:
            bal = f"Rs {m['balance']:.0f}"
            self._listbox.insert(
                tk.END,
                f"  {m['name']}  |  {bal}"
            )
        n = len(members)
        self._count_var.set(f"{n} member{'s' if n != 1 else ''}")

    def _on_select(self, e):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if hasattr(self, "_filtered") and idx < len(self._filtered):
            member = db.get_member_by_id(self._filtered[idx]["id"])
            if member:
                self._show_detail(member)

    # ── Actions ───────────────────────────────────────────────

    def _open_add_dialog(self):
        AddMemberDialog(self, on_added=self._on_member_added)

    def _on_member_added(self):
        self._load_members()
        self.app.set_status("New member added")

    def _save_member(self, member_id, name, username, notes, new_password):
        if not name.strip():
            messagebox.showerror("Error", "Name cannot be empty.", parent=self)
            return
        if not username.strip():
            messagebox.showerror("Error", "Username cannot be empty.", parent=self)
            return
        db.update_member(member_id, name.strip(), username.strip(),
                         notes.strip(), new_password or None)
        self._load_members()
        self.app.set_status(f"Member updated: {name}")
        messagebox.showinfo("Saved", f"{name}'s details updated.", parent=self)

    def _import_csv(self):
        """
        6.5D — bulk member import.
        Understands both the simple AZ Cafe CSV (name,username,password,balance)
        and the 46-column Cyber Cafe Pro export. Always previews first.
        """
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import Members CSV",
            filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")],
            parent=self)
        if not path:
            return

        try:
            preview = member_import.import_csv(path, dry_run=True)
        except OSError as exc:
            messagebox.showerror("Import Members", f"Could not read the file:\n{exc}",
                                 parent=self)
            return

        preview_text = member_import.format_report(preview)
        if preview["format"] == "unknown" or (preview["added"] == 0 and preview["errors"]):
            messagebox.showerror("Import Members",
                                 preview_text +
                                 "\n\nExpected a 'username' column, or a Cyber Cafe Pro "
                                 "members export.", parent=self)
            return
        if preview["added"] == 0:
            messagebox.showinfo("Import Members", preview_text +
                                "\n\nNothing new to import.", parent=self)
            return
        if not messagebox.askyesno(
                "Import Members",
                preview_text + f"\n\nImport {preview['added']} member(s) now?",
                parent=self):
            return

        report = member_import.import_csv(path)
        self._load_members()
        self.after(100, self.app.refresh_revenue)
        self.app.set_status(f"Imported {report['added']} member(s) from CSV")
        messagebox.showinfo(
            "Import Complete",
            member_import.format_report(report) +
            ("\n\nTemporary passwords are listed in the member notes — "
             "reset them on first login." if report.get("temp_passwords") else ""),
            parent=self)

    def _topup(self, member: dict):
        amount = simpledialog.askfloat(
            "Top Up Balance",
            f"Add how much to {member['name']}'s balance?\n"
            f"Current balance: {config.CURRENCY} {member['balance']:.0f}",
            minvalue=1, maxvalue=100000,
            parent=self
        )
        if amount:
            db.topup_member_balance(member["id"], amount)
            self._load_members()
            # Refresh detail view
            updated = db.get_member_by_id(member["id"])
            if updated:
                self._show_detail(updated)
                self._bal_var.set(
                    f"{config.CURRENCY} {updated['balance']:.0f}"
                )
            self.app.set_status(
                f"Topped up {member['name']}: +{config.CURRENCY} {amount:.0f}"
            )

    def _remove_balance(self, member: dict):
        amount = simpledialog.askfloat(
            "Remove Balance",
            f"Remove how much from {member['name']}'s balance?\n"
            f"Current balance: {config.CURRENCY} {member['balance']:.0f}",
            minvalue=1, maxvalue=member['balance'],
            parent=self
        )
        if amount:
            db.remove_member_balance(member["id"], amount)
            self._load_members()
            # Refresh detail view
            updated = db.get_member_by_id(member["id"])
            if updated:
                self._show_detail(updated)
                self._bal_var.set(
                    f"{config.CURRENCY} {updated['balance']:.0f}"
                )
            self.app.set_status(
                f"Removed balance from {member['name']}: -{config.CURRENCY} {amount:.0f}"
            )

    def _delete_member(self, member_id: int, name: str):
        if messagebox.askyesno(
            "Delete Member",
            f"Delete {name}?\nThis cannot be undone.",
            icon="warning", parent=self
        ):
            db.delete_member(member_id)
            self._load_members()
            # Clear detail panel
            for w in self._detail_frame.winfo_children():
                w.destroy()
            self._placeholder = tk.Label(
                self._detail_frame,
                text="Select a member to view details\nor click + Add Member",
                font=("Segoe UI", 10),
                fg=config.COLOR_TEXT_DIM,
                bg=config.COLOR_BG
            )
            self._placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.app.set_status(f"Member deleted: {name}")

    def _show_history(self, member: dict):
        MemberHistoryWindow(self, member)


# ============================================================
#  Add Member Dialog
# ============================================================

class AddMemberDialog(tk.Toplevel):

    def __init__(self, parent, on_added):
        super().__init__(parent)
        self.on_added = on_added
        self.title("Add New Member")
        self.configure(bg=config.COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        w, h = 360, 360
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build()

    def _build(self):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(self, text="  + Add New Member",
                 font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(self, bg=config.COLOR_BG, padx=20, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        lbl_cfg = dict(font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM,
                       bg=config.COLOR_BG, anchor="w")
        ent_cfg = dict(font=("Segoe UI", 10), bg=config.COLOR_BG3,
                       fg=config.COLOR_TEXT,
                       insertbackground=config.COLOR_TEXT,
                       relief=tk.FLAT, bd=4)

        def _field(label, var, show=None):
            tk.Label(body, text=label, **lbl_cfg).pack(
                fill=tk.X, pady=(8, 2))
            kw = dict(ent_cfg)
            if show:
                kw["show"] = show
            tk.Entry(body, textvariable=var, **kw).pack(fill=tk.X)

        self._name_var  = tk.StringVar()
        self._uname_var = tk.StringVar()
        self._pwd_var   = tk.StringVar()
        self._bal_var   = tk.StringVar(value="0")

        _field("Full Name",         self._name_var)
        _field("Username",          self._uname_var)
        _field("Password",          self._pwd_var,  show="●")
        _field(f"Starting Balance ({config.CURRENCY})", self._bal_var)

        # Buttons
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)
        btn_bar = tk.Frame(self, bg=config.COLOR_BG2, pady=10, padx=20)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="Add Member",
                  command=self._add,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT,
                  font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=16, pady=7,
                  cursor="hand2",
                  activebackground=config.COLOR_RED_DARK,
                  activeforeground=config.COLOR_TEXT,
                  bd=0).pack(side=tk.RIGHT)

        tk.Button(btn_bar, text="Cancel",
                  command=self.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM,
                  font=("Segoe UI", 9), relief=tk.FLAT,
                  padx=12, pady=7, cursor="hand2", bd=0
                  ).pack(side=tk.RIGHT, padx=(0, 8))

    def _add(self):
        name  = self._name_var.get().strip()
        uname = self._uname_var.get().strip()
        pwd   = self._pwd_var.get()

        if not name:
            messagebox.showerror("Error", "Name is required.", parent=self)
            return
        if not uname:
            messagebox.showerror("Error", "Username is required.", parent=self)
            return
        if not pwd:
            messagebox.showerror("Error", "Password is required.", parent=self)
            return

        try:
            bal = float(self._bal_var.get() or 0)
        except ValueError:
            bal = 0.0

        try:
            db.create_member(name, uname, pwd, balance=bal)
            self.on_added()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error",
                                 f"Could not add member.\n"
                                 f"Username may already exist.\n\n{e}",
                                 parent=self)


# ============================================================
#  Member Session History Window
# ============================================================

class MemberHistoryWindow(tk.Toplevel):

    def __init__(self, parent, member: dict):
        super().__init__(parent)
        self.title(f"Session History — {member['name']}")
        self.configure(bg=config.COLOR_BG)
        self.geometry("580x420")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 580) // 2
        y = (self.winfo_screenheight() - 420) // 2
        self.geometry(f"580x420+{x}+{y}")
        self._build(member)

    def _build(self, member: dict):
        tk.Frame(self, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(self,
                 text=f"  🕒  Session History — {member['name']}",
                 font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        # Header row
        cols  = ["Date", "PC", "Duration", "Amount", "Payment"]
        widths= [140,    80,   80,         80,        80]

        hdr = tk.Frame(self, bg=config.COLOR_BG3)
        hdr.pack(fill=tk.X, padx=0)
        for col, w in zip(cols, widths):
            tk.Label(hdr, text=col,
                     font=("Segoe UI", 8, "bold"),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG3,
                     width=w//8, anchor="w",
                     padx=8, pady=6).pack(side=tk.LEFT)

        # Scrollable list
        container = tk.Frame(self, bg=config.COLOR_BG)
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

        inner = tk.Frame(canvas, bg=config.COLOR_BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.config(
                       scrollregion=canvas.bbox("all")))

        sessions = db.get_member_sessions(member["id"])

        if not sessions:
            tk.Label(inner,
                     text="No sessions yet.",
                     font=("Segoe UI", 10),
                     fg=config.COLOR_TEXT_DIM,
                     bg=config.COLOR_BG,
                     pady=20).pack()
        else:
            for i, s in enumerate(sessions):
                row_bg = config.COLOR_BG if i % 2 == 0 else config.COLOR_BG2
                row = tk.Frame(inner, bg=row_bg)
                row.pack(fill=tk.X)

                date_str = s["start_time"][:16].replace("T", "  ")
                values = [
                    date_str,
                    s["pc_name"],
                    f"{s['duration_mins']}m",
                    f"Rs {s['amount_charged']:.0f}",
                    s["payment_type"]
                ]
                for val, w in zip(values, widths):
                    tk.Label(row, text=val,
                             font=("Segoe UI", 8),
                             fg=config.COLOR_TEXT,
                             bg=row_bg,
                             width=w//8, anchor="w",
                             padx=8, pady=5).pack(side=tk.LEFT)

        # Footer
        total = sum(s["amount_charged"] for s in sessions)
        tk.Frame(self, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)
        tk.Label(self,
                 text=f"Total sessions: {len(sessions)}   |   "
                      f"Total spent: {config.CURRENCY} {total:.0f}",
                 font=("Segoe UI", 9),
                 fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG2,
                 pady=6).pack(fill=tk.X, padx=10)
