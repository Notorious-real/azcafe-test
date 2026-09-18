# ============================================================
#  AZ Cafe - Dashboard
#  PC grid — cards appear automatically when PCs connect
# ============================================================

import tkinter as tk
from tkinter import simpledialog, messagebox
import sys
import os

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
import config
import database as db
from server.pc_card import PCCard, CARD_W, CARD_H
from server.dialogs import StartSessionDialog, StopSessionDialog

GRID_PAD_X = 18
GRID_PAD_Y = 18
GRID_GAP_X = 14
GRID_GAP_Y = 14


class Dashboard(tk.Frame):
    def __init__(self, parent, server, app, **kwargs):
        super().__init__(parent, bg=config.COLOR_BG, **kwargs)
        self.server = server
        self.app    = app
        self.cards     = {}
        self.positions = {}
        self._cols_per_row = 7
        self._build_ui()
        self._start_tick()
        self._load_remembered_pcs()

    def _build_ui(self):
        self._build_toolbar()
        container = tk.Frame(self, bg=config.COLOR_BG)
        container.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(container, bg=config.COLOR_BG,
                                highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(container, orient=tk.VERTICAL,
                           command=self.canvas.yview,
                           bg=config.COLOR_BG2,
                           troughcolor=config.COLOR_BG,
                           activebackground=config.COLOR_RED)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.config(yscrollcommand=vsb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.grid_frame = tk.Frame(self.canvas, bg=config.COLOR_BG)
        self._canvas_window = self.canvas.create_window(
            (0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", self._on_grid_resize)
        self.canvas.bind("<Configure>",     self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>",    self._on_mousewheel)
        self._empty_lbl = tk.Label(
            self.grid_frame,
            text="No PCs connected yet.\n\nStart the client app on your gaming PCs\nand they will appear here automatically.",
            font=("Segoe UI", 11),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG, justify=tk.CENTER)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=config.COLOR_BG2, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=config.COLOR_RED, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(bar, text="  DASHBOARD", font=("Segoe UI", 9, "bold"),
                 fg=config.COLOR_RED, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=8)

        # ── Group Filter (Phase 5F) ───────────────────────────
        tk.Label(bar, text="Group:", font=("Segoe UI", 8),
                 fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2).pack(side=tk.LEFT, padx=(12, 4))

        self._filter_group_var = tk.StringVar(value="All Groups")
        groups = ["All Groups"] + db.get_all_pc_groups()
        self._group_menu = tk.OptionMenu(bar, self._filter_group_var, *groups,
                                         command=lambda _: self._apply_group_filter())
        self._group_menu.config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                font=("Segoe UI", 8), relief=tk.FLAT, bd=0,
                                activebackground=config.COLOR_RED,
                                activeforeground=config.COLOR_TEXT, cursor="hand2")
        self._group_menu["menu"].config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                                        activebackground=config.COLOR_RED,
                                        activeforeground=config.COLOR_TEXT)
        self._group_menu.pack(side=tk.LEFT, padx=2)

        btn_cfg = dict(font=("Segoe UI", 8, "bold"), bg=config.COLOR_BG3,
                       fg=config.COLOR_TEXT, relief=tk.FLAT, padx=10, pady=4,
                       cursor="hand2", activebackground=config.COLOR_RED,
                       activeforeground=config.COLOR_TEXT, bd=0)

        tk.Button(bar, text="Shutdown All", command=self._shutdown_all, **btn_cfg).pack(side=tk.RIGHT, padx=4, pady=5)
        tk.Button(bar, text="Restart All",  command=self._restart_all,  **btn_cfg).pack(side=tk.RIGHT, padx=4, pady=5)
        tk.Button(bar, text="Stop All",     command=self._stop_all_sessions, **btn_cfg).pack(side=tk.RIGHT, padx=4, pady=5)
        tk.Button(bar, text="Lock All",     command=self._lock_all,           **btn_cfg).pack(side=tk.RIGHT, padx=4, pady=5)
        tk.Button(bar, text="Msg All",      command=self._message_all,        **btn_cfg).pack(side=tk.RIGHT, padx=4, pady=5)

        self._count_lbl = tk.Label(bar, text="0 PCs",
                                   font=("Segoe UI", 8),
                                   fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG2)
        self._count_lbl.pack(side=tk.RIGHT, padx=12)

    def _refresh_group_menu(self):
        """Update group filter dropdown options dynamically."""
        menu = self._group_menu["menu"]
        menu.delete(0, "end")
        groups = ["All Groups"] + db.get_all_pc_groups()
        for g in groups:
            menu.add_command(label=g, command=lambda val=g: (self._filter_group_var.set(val), self._apply_group_filter()))

    def _apply_group_filter(self):
        """Show only cards belonging to the selected group, repositioning them."""
        chosen = self._filter_group_var.get()
        all_pcs = {p["pc_name"]: p.get("group_name") or "Default" for p in db.get_all_pcs()}

        visible_col = 0
        visible_row = 0

        for pc_name, card in self.cards.items():
            pc_group = all_pcs.get(pc_name, "Default")
            if chosen == "All Groups" or pc_group == chosen:
                orig_pos = self.positions.get(pc_name, (visible_col, visible_row))
                if chosen == "All Groups":
                    col, row = orig_pos
                else:
                    col, row = visible_col, visible_row
                    visible_col += 1
                    if visible_col >= self._cols_per_row:
                        visible_col = 0
                        visible_row += 1

                x = GRID_PAD_X + col * (CARD_W + GRID_GAP_X)
                y = GRID_PAD_Y + row * (CARD_H + GRID_GAP_Y)
                card.place(x=x, y=y, width=CARD_W, height=CARD_H)
            else:
                card.place_forget()

        self._update_canvas_size()

    def on_pc_update(self, clients: dict):
        for name, card in self.cards.items():
            if name not in clients:
                card.update_data(config.STATUS_OFFLINE)
        for pc_name, client in clients.items():
            if pc_name not in self.cards:
                self._add_card(pc_name)
            self.cards[pc_name].update_data(
                status=client.status,
                user=client.session_user or "",
                remaining_secs=client.remaining_secs,
                paused=client.paused)
        total  = len(self.cards)
        active = sum(1 for c in clients.values() if c.status == config.STATUS_ACTIVE)
        self._count_lbl.config(text=f"{active} active / {total} total")
        if total == 0:
            self._empty_lbl.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self._empty_lbl.place_forget()

    def _load_remembered_pcs(self):
        remembered = db.get_all_pcs()
        for pc in remembered:
            self._add_card(pc["pc_name"], col=pc["grid_x"], row=pc["grid_y"])
        if not remembered:
            self._empty_lbl.place(relx=0.5, rely=0.4, anchor="center")

    def _add_card(self, pc_name: str, col: int = None, row: int = None):
        if pc_name in self.cards:
            return
        if col is None or row is None:
            col, row = self._next_position()
        self.positions[pc_name] = (col, row)
        card = PCCard(self.grid_frame, pc_name=pc_name,
                      on_command=self._handle_command)
        x = GRID_PAD_X + col * (CARD_W + GRID_GAP_X)
        y = GRID_PAD_Y + row * (CARD_H + GRID_GAP_Y)
        card.place(x=x, y=y, width=CARD_W, height=CARD_H)
        self.cards[pc_name] = card
        self._update_canvas_size()

    def _next_position(self) -> tuple:
        used = set(self.positions.values())
        col, row = 0, 0
        while (col, row) in used:
            col += 1
            if col >= self._cols_per_row:
                col = 0
                row += 1
        return col, row

    def on_card_dropped(self, card: PCCard):
        x = card.winfo_x()
        y = card.winfo_y()
        col = round((x - GRID_PAD_X) / (CARD_W + GRID_GAP_X))
        row = round((y - GRID_PAD_Y) / (CARD_H + GRID_GAP_Y))
        col = max(0, min(col, self._cols_per_row - 1))
        row = max(0, row)
        snap_x = GRID_PAD_X + col * (CARD_W + GRID_GAP_X)
        snap_y = GRID_PAD_Y + row * (CARD_H + GRID_GAP_Y)
        card.place(x=snap_x, y=snap_y)
        self.positions[card.pc_name] = (col, row)
        db.update_pc_position(card.pc_name, col, row)
        self._update_canvas_size()

    def _on_grid_resize(self, e):
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self.canvas.itemconfig(self._canvas_window, width=e.width)

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _update_canvas_size(self):
        # Calculate max height manually since place() doesn't auto-expand the parent frame
        max_h = 0
        for card in self.cards.values():
            info = card.place_info()
            if info:  # card is placed
                try:
                    y = int(info.get('y', 0))
                    if y + CARD_H > max_h:
                        max_h = y + CARD_H
                except ValueError:
                    pass
        
        # Add bottom padding
        required_height = max(max_h + GRID_PAD_Y, self.canvas.winfo_height())
        self.grid_frame.config(height=required_height)
        
        self.grid_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _start_tick(self):
        self._tick()

    def _tick(self):
        for card in self.cards.values():
            card.tick()
        self.after(1000, self._tick)

    def _handle_command(self, pc_name: str, command: str, **kwargs):
        srv = self.server
        if command == "start_session":
            self._dialog_start_session(pc_name)
        elif command == "stop_session":
            self._confirm_stop(pc_name)
        elif command == "pause_session":
            srv.pause_session(pc_name)
            self.app.set_status(f"Paused — {pc_name}")
        elif command == "resume_session":
            srv.resume_session(pc_name)
            self.app.set_status(f"Resumed — {pc_name}")
        elif command == "lock":
            srv.lock_pc(pc_name)
            self.app.set_status(f"Locked — {pc_name}")
        elif command == "unlock":
            srv.unlock_pc(pc_name)
            self.app.set_status(f"Unlocked — {pc_name}")
        elif command == "send_message":
            self._dialog_send_message(pc_name)
        elif command == "restart":
            if messagebox.askyesno("Restart PC", f"Restart {pc_name}?", icon="warning"):
                srv.restart_pc(pc_name)
        elif command == "shutdown":
            if messagebox.askyesno("Shutdown PC", f"Shutdown {pc_name}?", icon="warning"):
                srv.shutdown_pc(pc_name)
        elif command == "add_time":
            self._dialog_add_time(pc_name)
        elif command == "rename":
            self._dialog_rename(pc_name)
        elif command == "change_group":
            self._dialog_change_group(pc_name)
        elif command == "assign_plan":
            self._dialog_assign_plan(pc_name)
        elif command == "session_info":
            self._show_session_info(pc_name)

    def _dialog_start_session(self, pc_name: str):
        def _on_start(pc_name, user, duration_mins, amount,
                      member_id=None, payment_type="cash",
                      discount_pct=0.0, discount_amount=0.0):
            self.server.start_session(
                pc_name=pc_name, user=user,
                duration_mins=duration_mins, amount=amount,
                member_id=member_id, payment_type=payment_type,
                discount_pct=discount_pct, discount_amount=discount_amount
            )
            if member_id and payment_type == "balance":
                db.deduct_member_balance(member_id, amount)
            self.app.set_status(f"Session started — {pc_name} ({user})")
            self.app.refresh_revenue()

        StartSessionDialog(self, pc_name=pc_name, on_start=_on_start)

    def _confirm_stop(self, pc_name: str):
        card = self.cards.get(pc_name)
        if not card:
            return
        session = db.get_active_session(pc_name)
        session_info = {
            "user":         card.session_user or "Guest",
            "duration_mins":session["duration_mins"] if session else 0,
            "remaining_secs": card.remaining_secs,
            "amount":       session["amount_charged"] if session else 0,
            "payment_type": session["payment_type"] if session else "cash",
            "member_id":    session["member_id"] if session else None,
        }

        def _on_confirm(payment_type="cash", actual_amount=None):
            self.server.stop_session(pc_name, actual_amount=actual_amount)
            self.app.set_status(f"Session stopped — {pc_name}")
            self.app.refresh_revenue()

        StopSessionDialog(self, pc_name=pc_name,
                          session_info=session_info,
                          on_confirm=_on_confirm)

    def _dialog_send_message(self, pc_name: str):
        msg = simpledialog.askstring("Send Message",
                                     f"Message to show on {pc_name}:",
                                     parent=self)
        if msg:
            self.server.send_message(pc_name, msg)
            self.app.set_status(f"Message sent to {pc_name}")

    def _dialog_add_time(self, pc_name: str):
        mins = simpledialog.askinteger("Add Time",
                                       f"Add how many minutes to {pc_name}?",
                                       minvalue=1, maxvalue=300, parent=self)
        if mins:
            self.server.add_time(pc_name, mins)
            self.app.set_status(f"+{mins} min added to {pc_name}")

    def _dialog_rename(self, pc_name: str):
        new_name = simpledialog.askstring("Rename PC",
                                          f"New display name for {pc_name}:",
                                          parent=self)
        if new_name and new_name.strip():
            card = self.cards.get(pc_name)
            if card:
                card._name_lbl.config(text=new_name.strip())
            self.app.set_status(f"PC renamed to {new_name.strip()}")

    def _dialog_assign_plan(self, pc_name: str):
        """Phase 4C — Assign a specific pricing plan to this PC."""
        plans = db.get_all_pricing_plans()
        if not plans:
            messagebox.showinfo("Assign Plan", "No pricing plans found. Create one in Pricing settings first.", parent=self)
            return

        pc = db.get_pc_by_name(pc_name)
        curr_plan_id = pc.get("pricing_plan_id") if pc else None

        # Build selection window
        top = tk.Toplevel(self)
        top.title(f"Assign Plan — {pc_name}")
        top.configure(bg=config.COLOR_BG)
        top.resizable(False, False)
        top.grab_set()

        w, h = 320, 240
        top.geometry(f"{w}x{h}")
        top.update_idletasks()
        x = (top.winfo_screenwidth() - w) // 2
        y = (top.winfo_screenheight() - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")

        tk.Frame(top, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(top, text=f"  🏷️  Assign Plan to {pc_name}",
                 font=("Segoe UI", 10, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(top, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(top, bg=config.COLOR_BG, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="Select standard hourly rate for this PC:",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(0, 8))

        plan_map = {f"{p['name']} (Rs {p['rate_per_hour']:.0f}/hr)": p["id"] for p in plans}
        plan_names = list(plan_map.keys())

        default_str = plan_names[0]
        if curr_plan_id:
            for p in plans:
                if p["id"] == curr_plan_id:
                    default_str = f"{p['name']} (Rs {p['rate_per_hour']:.0f}/hr)"
                    break

        sel_var = tk.StringVar(value=default_str)
        menu = tk.OptionMenu(body, sel_var, *plan_names)
        menu.config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT, font=("Segoe UI", 9),
                    relief=tk.FLAT, bd=0, activebackground=config.COLOR_RED,
                    activeforeground=config.COLOR_TEXT, cursor="hand2")
        menu["menu"].config(bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                            activebackground=config.COLOR_RED,
                            activeforeground=config.COLOR_TEXT)
        menu.pack(fill=tk.X, pady=(0, 16))

        def _save():
            selected_name = sel_var.get()
            chosen_id = plan_map.get(selected_name)
            if chosen_id:
                db.set_pc_pricing_plan(pc_name, chosen_id)
                self.app.set_status(f"Assigned plan '{selected_name}' to {pc_name}")
                messagebox.showinfo("Success", f"Plan assigned to {pc_name}.", parent=top)
            top.destroy()

        btn_row = tk.Frame(body, bg=config.COLOR_BG)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="Save Plan", command=_save,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT, font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=16, pady=6, cursor="hand2",
                  activebackground=config.COLOR_RED_DARK, activeforeground=config.COLOR_TEXT, bd=0).pack(side=tk.RIGHT)
        tk.Button(btn_row, text="Cancel", command=top.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=12, pady=6, cursor="hand2", bd=0).pack(side=tk.RIGHT, padx=(0, 8))

    def _show_session_info(self, pc_name: str):
        card = self.cards.get(pc_name)
        if not card:
            return
        secs = card.remaining_secs
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        messagebox.showinfo(f"Session Info — {pc_name}",
                            f"PC:        {pc_name}\n"
                            f"User:      {card.session_user}\n"
                            f"Time left: {h:02d}:{m:02d}:{s:02d}")

    def _stop_all_sessions(self):
        active = [n for n, c in self.cards.items()
                  if c.status == config.STATUS_ACTIVE]
        if not active:
            messagebox.showinfo("Stop All", "No active sessions.")
            return
        if messagebox.askyesno("Stop All Sessions",
                               f"Stop all {len(active)} active sessions?",
                               icon="warning"):
            for name in active:
                self.server.stop_session(name)
            self.app.set_status(f"Stopped {len(active)} sessions")
            self.app.refresh_revenue()

    def _lock_all(self):
        if messagebox.askyesno("Lock All", "Lock all connected PCs?"):
            for name in self.cards:
                self.server.lock_pc(name)
            self.app.set_status("All PCs locked")

    def _message_all(self):
        msg = simpledialog.askstring("Message All PCs",
                                     "Broadcast message to all PCs:",
                                     parent=self)
        if msg:
            self.server.send_message_all(msg)
            self.app.set_status("Message broadcast to all PCs")

    def _dialog_change_group(self, pc_name: str):
        """Phase 5F — Assign PC to a group (e.g. VIP, Console, Floor 1)."""
        existing_groups = db.get_all_pc_groups()
        pc = db.get_pc_by_name(pc_name)
        curr_group = pc.get("group_name") if pc else "Default"

        top = tk.Toplevel(self)
        top.title(f"Change Group — {pc_name}")
        top.configure(bg=config.COLOR_BG)
        top.resizable(False, False)
        top.grab_set()

        w, h = 320, 220
        top.geometry(f"{w}x{h}")
        top.update_idletasks()
        x = (top.winfo_screenwidth() - w) // 2
        y = (top.winfo_screenheight() - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")

        tk.Frame(top, bg=config.COLOR_RED, height=3).pack(fill=tk.X)
        tk.Label(top, text=f"  📁  Change Group for {pc_name}",
                 font=("Segoe UI", 10, "bold"),
                 fg=config.COLOR_TEXT, bg=config.COLOR_BG2,
                 anchor="w", pady=10).pack(fill=tk.X)
        tk.Frame(top, bg=config.COLOR_BORDER, height=1).pack(fill=tk.X)

        body = tk.Frame(top, bg=config.COLOR_BG, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text=f"Current: {curr_group}\nEnter or select group name:",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM, bg=config.COLOR_BG,
                 anchor="w").pack(fill=tk.X, pady=(0, 6))

        group_var = tk.StringVar(value=curr_group)
        entry = tk.Entry(body, textvariable=group_var, font=("Segoe UI", 10),
                         bg=config.COLOR_BG3, fg=config.COLOR_TEXT,
                         insertbackground=config.COLOR_TEXT, relief=tk.FLAT, bd=4)
        entry.pack(fill=tk.X, pady=(0, 8))

        btn_bar_presets = tk.Frame(body, bg=config.COLOR_BG)
        btn_bar_presets.pack(fill=tk.X, pady=(0, 10))
        for g in ["Default", "VIP", "Console"]:
            tk.Button(btn_bar_presets, text=g, command=lambda val=g: group_var.set(val),
                      bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM, font=("Segoe UI", 8),
                      relief=tk.FLAT, padx=6, pady=2, cursor="hand2", bd=0).pack(side=tk.LEFT, padx=2)

        def _save():
            new_grp = group_var.get().strip() or "Default"
            db.update_pc_group(pc_name, new_grp)
            self._refresh_group_menu()
            self._apply_group_filter()
            self.app.set_status(f"Moved {pc_name} to group '{new_grp}'")
            top.destroy()

        btn_row = tk.Frame(body, bg=config.COLOR_BG)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="Save Group", command=_save,
                  bg=config.COLOR_RED, fg=config.COLOR_TEXT, font=("Segoe UI", 9, "bold"),
                  relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
                  activebackground=config.COLOR_RED_DARK, activeforeground=config.COLOR_TEXT, bd=0).pack(side=tk.RIGHT)
        tk.Button(btn_row, text="Cancel", command=top.destroy,
                  bg=config.COLOR_BG3, fg=config.COLOR_TEXT_DIM, font=("Segoe UI", 9),
                  relief=tk.FLAT, padx=10, pady=6, cursor="hand2", bd=0).pack(side=tk.RIGHT, padx=(0, 8))

    def _restart_all(self):
        """Phase 5B — Restart all connected PCs."""
        if not self.cards:
            messagebox.showinfo("Restart All", "No PCs connected.")
            return
        if messagebox.askyesno("Restart All PCs",
                               f"Are you sure you want to restart ALL {len(self.cards)} PCs?",
                               icon="warning"):
            self.server.restart_all()
            self.app.set_status("Sent restart command to all PCs")

    def _shutdown_all(self):
        """Phase 5B — Shutdown all connected PCs."""
        if not self.cards:
            messagebox.showinfo("Shutdown All", "No PCs connected.")
            return
        if messagebox.askyesno("Shutdown All PCs",
                               f"Are you sure you want to SHUTDOWN ALL {len(self.cards)} PCs?",
                               icon="warning"):
            self.server.shutdown_all()
            self.app.set_status("Sent shutdown command to all PCs")

