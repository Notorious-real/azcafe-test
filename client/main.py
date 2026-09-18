# ============================================================
#  AZ Cafe - Client Entry Point
# ============================================================

import sys
import os

# ── PyInstaller-safe path setup ───────────────────────────────
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, ROOT_DIR)

import tkinter as tk
from tkinter import messagebox
import threading

import config
from client.client_core    import AZCafeClient
from client.lock_screen    import LockScreen
from client.session_screen import SessionOverlay


class ClientApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self._state          = "LOCKED"
        self._overlay        = None
        self._admin_unlocked = False

        self._setup_window()
        self._build_ui()

        self._client = AZCafeClient(on_event=self._on_event)
        self._client.start()

        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self._bind_hotkeys()

    def _setup_window(self):
        self.title(config.APP_NAME)
        self.configure(bg=config.COLOR_BG)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost",    True)
        self.state("zoomed")

        logo_path = os.path.join(ROOT_DIR, "assets", "logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(logo_path).resize((32, 32), Image.LANCZOS)
                self._icon = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._icon)
            except Exception:
                pass

    def _bind_hotkeys(self):
        self.bind("<Alt-F4>",  lambda e: "break")
        self.bind("<Escape>",  lambda e: "break")

    def _build_ui(self):
        self._lock_screen = LockScreen(
            self,
            on_admin_unlock=self._admin_unlock,
            on_member_login_attempt=self._on_member_login_attempt
        )
        self._lock_screen.place(x=0, y=0, relwidth=1, relheight=1)

    def _on_member_login_attempt(self, username, password):
        if not self._client.send_member_login(username, password):
            if hasattr(self._lock_screen, "_member_panel"):
                self._lock_screen._member_panel.show_result(
                    False, "Cannot connect to server. Check network."
                )

    def _on_event(self, event: str, **data):
        self.after(0, lambda: self._handle_event(event, **data))

    def _handle_event(self, event: str, **data):
        if event == "connected":
            self._lock_screen.set_connected(True)

        elif event == "disconnected":
            self._lock_screen.set_connected(False)
            if self._state == "ACTIVE":
                self._do_lock()

        elif event == "login_result":
            success = data.get("success", False)
            if success:
                user = data.get("member_name", "Member")
                dur_secs = data.get("duration_secs", 3600)
                bal_left = data.get("balance_left", 0)
                if hasattr(self._lock_screen, "_member_panel"):
                    self._lock_screen._member_panel.show_result(
                        True, f"Welcome {user}! (Balance left: Rs {bal_left:.0f})"
                    )
                self.after(800, lambda: self._start_session(user, dur_secs))
            else:
                reason = data.get("reason", "Login failed")
                if hasattr(self._lock_screen, "_member_panel"):
                    self._lock_screen._member_panel.show_result(False, reason)

        elif event == "session_started":
            self._start_session(
                data.get("user", "Guest"),
                data.get("duration_secs", 3600)
            )

        elif event == "session_stopped":
            self._do_lock()

        elif event == "session_expired":
            messagebox.showinfo(
                "Session Ended",
                "Your session time has ended.\nPlease ask the cashier to continue."
            )
            self._do_lock()

        elif event == "session_paused":
            if self._overlay:
                self._overlay.set_paused(True)

        elif event == "session_resumed":
            if self._overlay:
                self._overlay.set_paused(False)

        elif event == "locked":
            self._do_lock()

        elif event == "unlocked":
            self._do_unlock_admin()

        elif event == "time_update":
            remaining = data.get("remaining", 0)
            if self._overlay:
                self._overlay.update_remaining(remaining)
            if hasattr(self, "_launcher") and self._launcher:
                self._launcher.update_time(remaining)

        elif event == "low_time_warning":
            mins      = data.get("minutes", 0)
            remaining = data.get("remaining", 0)
            if self._overlay:
                self._overlay.update_remaining(remaining)
                self._overlay.flash_warning(mins)
            # Show warning popup on client screen
            self._show_time_warning(mins)

        elif event == "message":
            messagebox.showinfo("Message from Admin", data.get("text", ""))

        elif event == "shutdown":
            messagebox.showinfo("Shutting Down",
                                "This PC will shut down in 5 seconds.")

        elif event == "restart":
            messagebox.showinfo("Restarting",
                                "This PC will restart in 5 seconds.")

    def _start_session(self, user: str, duration_secs: int):
        self._state = "ACTIVE"
        self._lock_screen.place_forget()
        
        # Clean up old launcher or overlay if present
        if hasattr(self, "_launcher") and self._launcher:
            try:
                self._launcher.kill_launched_games()
                self._launcher.destroy()
            except Exception:
                pass
            self._launcher = None

        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass
            self._overlay = None

        # Create Game Launcher UI (6.5 C)
        from client.game_launcher import GameLauncherScreen
        self.deiconify()
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", False)
        
        self._launcher = GameLauncherScreen(
            self, user_name=user,
            on_end_session=self._client.report_session_ended
        )
        self._launcher.place(x=0, y=0, relwidth=1, relheight=1)
        self._launcher.update_time(duration_secs)

        # Also create small floating overlay indicator
        self._overlay = SessionOverlay(self, user=user, duration_secs=duration_secs)

    def _do_lock(self):
        self._state          = "LOCKED"
        self._admin_unlocked = False

        if hasattr(self, "_launcher") and self._launcher:
            try:
                self._launcher.kill_launched_games()
                self._launcher.destroy()
            except Exception:
                pass
            self._launcher = None

        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass
            self._overlay = None

        if hasattr(self._lock_screen, "hide_member_login"):
            self._lock_screen.hide_member_login()

        self.deiconify()
        self.attributes("-fullscreen", True)
        self.attributes("-topmost",    True)
        self._lock_screen.place(x=0, y=0, relwidth=1, relheight=1)
        self._lock_screen.lift()
        self.focus_force()

    def _do_unlock_admin(self):
        self._state          = "UNLOCKED"
        self._admin_unlocked = True
        
        if hasattr(self, "_launcher") and self._launcher:
            try:
                self._launcher.destroy()
            except Exception:
                pass
            self._launcher = None

        self._lock_screen.place_forget()
        self.attributes("-fullscreen", False)
        self.attributes("-topmost",    False)
        self.iconify()

    def _show_time_warning(self, minutes: int):
        """Show a non-blocking warning popup that auto-closes."""
        warn = tk.Toplevel(self)
        warn.title("Time Warning")
        warn.configure(bg=config.COLOR_BG)
        warn.attributes("-topmost", True)
        warn.resizable(False, False)
        warn.overrideredirect(True)

        # Center on screen
        w, h = 340, 140
        sw = warn.winfo_screenwidth()
        sh = warn.winfo_screenheight()
        warn.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Frame(warn, bg=config.COLOR_RED, height=4).pack(fill=tk.X)

        tk.Label(
            warn,
            text="⚠  TIME WARNING",
            font=("Segoe UI", 11, "bold"),
            fg=config.COLOR_RED_BRIGHT,
            bg=config.COLOR_BG,
            pady=12
        ).pack()

        unit = "minute" if minutes == 1 else "minutes"
        tk.Label(
            warn,
            text=f"Only {minutes} {unit} remaining!",
            font=("Segoe UI", 13),
            fg=config.COLOR_TEXT,
            bg=config.COLOR_BG
        ).pack()

        tk.Label(
            warn,
            text="Please ask the cashier to add time.",
            font=("Segoe UI", 9),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG,
            pady=6
        ).pack()

        # Auto-close after 8 seconds
        warn.after(8000, warn.destroy)

        # Click to dismiss
        warn.bind("<Button-1>", lambda e: warn.destroy())

    def _admin_unlock(self):
        self._admin_unlocked = True
        self._state          = "UNLOCKED"
        self.attributes("-fullscreen", False)
        self.attributes("-topmost",    False)
        self._lock_screen.place_forget()
        self.iconify()


def run():
    app = ClientApp()
    app.mainloop()


if __name__ == "__main__":
    run()
