# ============================================================
#  AZ Cafe - Client Entry Point
#  Kiosk shell for one gaming PC:
#    lock screen → member session (game launcher + timer) → locked
#  Server has the final say on time, money and locking.
# ============================================================

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import applog                                              # noqa: E402
import config                                              # noqa: E402
import client_config                                       # noqa: E402
import games as games_store                                # noqa: E402
from client import sounds                                  # noqa: E402
from client.client_core import AZCafeClient                # noqa: E402
from client.kiosk import KioskGuard                        # noqa: E402
from client.lock_screen import LockScreen                  # noqa: E402
from client.session_screen import SessionOverlay           # noqa: E402

log = applog.get_logger("client")


class ClientApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.connection = client_config.load_client_config()
        self._state = "LOCKED"
        self._overlay = None
        self._launcher = None
        self._admin_unlocked = False
        self._settings = {}
        self._kiosk = KioskGuard(on_blocked=lambda vk: None)

        self._setup_window()
        self._build_ui()

        self.client = AZCafeClient(on_event=self._on_event)
        self.client.start()

        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self._bind_hotkeys()
        self._start_kiosk()
        self._start_server_watchdog()

    # ── window ──────────────────────────────────────────────
    def _setup_window(self):
        self.title(config.APP_NAME)
        self.configure(bg=config.COLOR_BG)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)

        logo_path = os.path.join(ROOT_DIR, "assets", "logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(logo_path).resize((32, 32), Image.LANCZOS)
                self._icon = ImageTk.PhotoImage(img)
                self.iconphoto(True, self._icon)
            except Exception as exc:                           # noqa: BLE001
                log.debug("Icon load failed: %s", exc)

    def _bind_hotkeys(self):
        self.bind("<Alt-F4>", lambda e: "break")
        self.bind("<Escape>", lambda e: "break")

    def _start_kiosk(self):
        if not self.connection.get("kiosk_mode", True):
            log.info("Kiosk mode disabled in client_config.json")
            return
        if self._kiosk.enable():
            self._kiosk.watch_window(self)
            log.info("Kiosk guard active")

    def _start_server_watchdog(self):
        """Re-check the connection every few seconds and say so on screen."""
        self.after(4000, self._watchdog)

    def _watchdog(self):
        connected = self.client.connected
        self._lock_screen.set_connected(connected)
        if not connected and self._state == "ACTIVE":
            self._lock_screen.set_connected(False)
        self.after(4000, self._watchdog)

    def _build_ui(self):
        self._lock_screen = LockScreen(
            self,
            on_admin_unlock=self._admin_unlock,
            on_member_login_attempt=self._on_member_login_attempt,
            on_admin_unlock_attempt=self._on_admin_unlock_attempt,
        )
        self._lock_screen.place(x=0, y=0, relwidth=1, relheight=1)
        self._lock_screen.fade_in()

    # ── events from the client core (worker thread) ─────────
    def _on_event(self, event: str, **data):
        self.after(0, lambda: self._handle_event(event, **data))

    def _handle_event(self, event: str, **data):
        if event == "connected":
            self._lock_screen.set_connected(True)

        elif event == "disconnected":
            self._lock_screen.set_connected(False)

        elif event == "config_missing":
            self._show_config_help()

        elif event == "config":
            self._apply_config(data)

        elif event == "login_result":
            success = data.get("success", False)
            if success:
                sounds.play("start")
                user = data.get("member_name", "Member")
                balance = data.get("balance_left", 0)
                self._lock_screen.show_member_result(
                    True, f"Welcome {user}! ({config.CURRENCY} {balance:.0f} left)")
            else:
                sounds.play("error")
                self._lock_screen.show_member_result(
                    False, data.get("reason", "Login failed"))

        elif event == "session_started":
            sounds.play("start")
            self._start_session(data.get("user", "Guest"),
                                data.get("duration_secs", 3600))

        elif event == "session_stopped":
            self._do_lock()

        elif event == "session_expired":
            sounds.play("expire")
            messagebox.showinfo("Session Ended",
                               "Your session time is over.\n"
                               "Please see the counter to continue.")
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
            if self._launcher:
                self._launcher.update_time(remaining)

        elif event == "low_time_warning":
            minutes = data.get("minutes", 0)
            sounds.play("warning")
            if self._overlay:
                self._overlay.update_remaining(data.get("remaining", 0))
                self._overlay.flash_warning(minutes)
            self._show_time_warning(minutes)

        elif event == "message":
            sounds.play("message")
            messagebox.showinfo("Message from the counter", data.get("text", ""))

        elif event == "admin_unlock_result":
            self._lock_screen.show_admin_result(
                data.get("success", False), data.get("reason", ""))

        elif event == "shutdown":
            messagebox.showinfo("Shutting Down", "This PC will shut down in 5 seconds.")
            self._kiosk.disable()
            threading.Thread(target=lambda: os.system("shutdown /s /t 5"),
                             daemon=True).start()

        elif event == "restart":
            messagebox.showinfo("Restarting", "This PC will restart in 5 seconds.")
            self._kiosk.disable()
            threading.Thread(target=lambda: os.system("shutdown /r /t 5"),
                             daemon=True).start()

    def _apply_config(self, data: dict):
        self._settings = dict(data)
        pushed_games = data.get("games")
        if pushed_games:
            # The counter decides which games appear — keep a local copy so
            # the launcher works even if the client restarts offline.
            try:
                games_store.save_games(pushed_games)
            except OSError as exc:
                log.warning("Could not store the game list: %s", exc)
        sounds.set_enabled(data.get("sound_enabled", True))
        self._lock_screen.set_shop_name(data.get("shop_name", config.APP_NAME))
        self._kiosk.set_task_manager_locked(bool(data.get("lock_task_manager")))
        if not data.get("kiosk_mode", True):
            self._kiosk.disable()

    # ── member / admin actions ──────────────────────────────
    def _on_member_login_attempt(self, username, password):
        if not self.client.send_member_login(username, password):
            self._lock_screen.show_member_result(
                False, "Cannot reach the server. Please tell the counter.")

    def _on_admin_unlock_attempt(self, password) -> bool:
        return self.client.send_admin_unlock(password)

    def _show_config_help(self):
        """First run on a fresh PC: tell the operator what to do."""
        path = client_config.client_config_path()
        messagebox.showwarning(
            "Server not configured",
            "This PC does not know the admin PC's address yet.\n\n"
            f"Open:\n{path}\n\n"
            'and set  "server_ip": "192.168.x.x"  — or set the '
            "AZCAFE_SERVER_IP environment variable.")
        log.warning("Client started without a server_ip (%s)", path)

    # ── session lifecycle ───────────────────────────────────
    def _start_session(self, user: str, duration_secs: int):
        self._state = "ACTIVE"
        self._lock_screen.place_forget()

        if self._launcher:
            try:
                self._launcher.kill_launched_games()
                self._launcher.destroy()
            except tk.TclError:
                pass
            self._launcher = None
        if self._overlay:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None

        from client.game_launcher import GameLauncherScreen

        self.deiconify()
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", False)

        games_store.load_games()      # pick up edits without a restart
        self._launcher = GameLauncherScreen(
            self, user_name=user, on_end_session=self.client.report_session_ended)
        self._launcher.place(x=0, y=0, relwidth=1, relheight=1)
        self._launcher.update_time(duration_secs)

        self._overlay = SessionOverlay(self, user=user, duration_secs=duration_secs)
        self._overlay.slide_in()

    def _do_lock(self):
        self._state = "LOCKED"
        self._admin_unlocked = False

        if self._launcher:
            try:
                self._launcher.kill_launched_games()
                self._launcher.destroy()
            except tk.TclError:
                pass
            self._launcher = None
        if self._overlay:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None

        if hasattr(self._lock_screen, "hide_member_login"):
            self._lock_screen.hide_member_login()

        self.deiconify()
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self._lock_screen.place(x=0, y=0, relwidth=1, relheight=1)
        self._lock_screen.lift()
        self._lock_screen.fade_in()
        self.focus_force()
        if self._kiosk.active:
            self._kiosk.set_task_manager_locked(
                bool(self._settings.get("lock_task_manager")))
        self.client.send_status("LOCKED")

    def _do_unlock_admin(self):
        self._state = "UNLOCKED"
        self._admin_unlocked = True
        sounds.play("unlock")

        if self._launcher:
            try:
                self._launcher.kill_launched_games()
                self._launcher.destroy()
            except tk.TclError:
                pass
            self._launcher = None

        self._lock_screen.place_forget()
        self._kiosk.disable()                 # let the technician work
        self.attributes("-fullscreen", False)
        self.attributes("-topmost", False)
        self.iconify()
        self.client.send_status("UNLOCKED")

    def _admin_unlock(self):
        """Called by the lock screen once the server approved the password."""
        self._do_unlock_admin()

    def _show_time_warning(self, minutes: int):
        warn = tk.Toplevel(self)
        warn.title("Time Warning")
        warn.configure(bg=config.COLOR_BG)
        warn.attributes("-topmost", True)
        warn.resizable(False, False)
        warn.overrideredirect(True)

        width, height = 360, 150
        screen_w, screen_h = warn.winfo_screenwidth(), warn.winfo_screenheight()
        warn.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")

        tk.Frame(warn, bg=config.COLOR_RED, height=4).pack(fill=tk.X)
        tk.Label(warn, text="⚠  TIME WARNING", font=("Segoe UI", 11, "bold"),
                 fg=config.COLOR_RED_BRIGHT, bg=config.COLOR_BG, pady=12).pack()
        unit = "minute" if minutes == 1 else "minutes"
        tk.Label(warn, text=f"Only {minutes} {unit} remaining!",
                 font=("Segoe UI", 13), fg=config.COLOR_TEXT,
                 bg=config.COLOR_BG).pack()
        tk.Label(warn, text="Please ask the counter to add time.",
                 font=("Segoe UI", 9), fg=config.COLOR_TEXT_DIM,
                 bg=config.COLOR_BG, pady=6).pack()

        warn.after(8000, warn.destroy)
        warn.bind("<Button-1>", lambda e: warn.destroy())

    # ── shutdown ────────────────────────────────────────────
    def destroy(self):
        try:
            self._kiosk.disable()
            self.client.stop()
        except Exception:                                      # noqa: BLE001
            pass
        super().destroy()


def run():
    applog.setup_logging("azcafe-client")
    config_data = client_config.load_client_config()
    log.info("Starting client as %s (server %s:%s)",
             config_data["pc_name"], config_data["server_ip"] or "-", config_data["server_port"])
    app = ClientApp()
    app.mainloop()


if __name__ == "__main__":
    run()
