# ============================================================
#  AZ Cafe - Client kiosk hardening  (Phase 6.5B)
#
#  Windows: installs a low-level keyboard hook that swallows the
#  keys that let a customer leave the café shell — Win, Alt+Tab,
#  Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc and Alt+F4 — while the PC is
#  locked or the "keep on top" guard is active. Optionally flips the
#  per-user DisableTaskMgr policy.
#
#  Honest limits (see DEPLOY.md): Ctrl+Alt+Del and the Secure
#  Desktop cannot be blocked from user mode, and anything running as
#  Administrator can remove the hook. This is a deterrent plus a
#  focus watchdog, not a kernel-level kiosk.
# ============================================================

import ctypes
import sys
import threading
import time

import applog

log = applog.get_logger("kiosk")

IS_WINDOWS = sys.platform.startswith("win")

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_TAB, VK_ESCAPE, VK_F4 = 0x09, 0x1B, 0x73
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_CONTROL, VK_ALT = 0x11, 0x12
VK_SHIFT = 0x10

BLOCKED_COMBOS = {
    (VK_ALT, VK_TAB), (VK_ALT, VK_ESCAPE), (VK_CONTROL, VK_ESCAPE),
    (VK_CONTROL, VK_SHIFT, VK_ESCAPE), (VK_ALT, VK_F4),
}


class KioskGuard:
    """Blocks escape hotkeys and keeps our window focused."""

    def __init__(self, on_blocked=None):
        self.on_blocked = on_blocked
        self.active = False
        self.supported = IS_WINDOWS
        self._hook = None
        self._thread = None
        self._callback = None
        self._window = None
        self._window_watch = False

    # ── hotkeys ─────────────────────────────────────────────
    def enable(self):
        if not self.supported or self.active:
            return False
        self.active = True
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()
        return True

    def disable(self):
        self.active = False
        if self._hook and self.supported:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception as exc:                          # noqa: BLE001
                log.debug("Unhook failed: %s", exc)
            self._hook = None
        self.set_task_manager_locked(False)

    def _hook_loop(self):
        """The hook must live on the thread that owns a message loop."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        def handler(n_code, w_param, l_param):
            if n_code == 0 and self.active and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                try:
                    vk = ctypes.cast(l_param, ctypes.POINTER(ctypes.c_ulong))[0]
                    if self._should_block(vk, user32):
                        if self.on_blocked:
                            self.on_blocked(vk)
                        return 1                              # swallow the key
                except Exception:                             # noqa: BLE001
                    pass
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int,
                                   ctypes.c_ulong, ctypes.c_void_p)
        self._callback = proto(handler)          # keep a reference!
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback,
                                              kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.warning("Keyboard hook could not be installed")
            self.supported = False
            return

        message = ctypes.create_string_buffer(28)
        while self.active:
            got = user32.PeekMessageW(message, 0, 0, 0, 1)   # PM_REMOVE
            if got:
                user32.TranslateMessage(message)
                user32.DispatchMessageW(message)
            else:
                time.sleep(0.02)

    def _should_block(self, vk: int, user32) -> bool:
        if vk in (VK_LWIN, VK_RWIN):
            return True
        pressed = {VK_ALT, VK_CONTROL, VK_SHIFT} & {
            key for key in (VK_ALT, VK_CONTROL, VK_SHIFT)
            if user32.GetAsyncKeyState(key) & 0x8000
        }
        for combo in BLOCKED_COMBOS:
            if vk in combo and (set(combo) - {vk}) <= pressed:
                return True
        return False

    # ── window focus ────────────────────────────────────────
    def watch_window(self, window, enabled: bool = True):
        """Re-assert fullscreen/topmost if the window loses focus."""
        self._window = window
        if enabled and not self._window_watch:
            self._window_watch = True
            threading.Thread(target=self._focus_loop, daemon=True).start()

    def _focus_loop(self):
        while self._window_watch and self._window is not None:
            time.sleep(2.0)
            try:
                if not self._window.winfo_exists():
                    break
                self._window.deiconify()
                self._window.attributes("-fullscreen", True)
                self._window.attributes("-topmost", True)
            except Exception:                                  # noqa: BLE001
                break

    # ── Task Manager policy ─────────────────────────────────
    def set_task_manager_locked(self, locked: bool):
        if not self.supported:
            return False
        try:
            import winreg
            path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                     winreg.KEY_SET_VALUE)
            try:
                if locked:
                    winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
                else:
                    try:
                        winreg.DeleteValue(key, "DisableTaskMgr")
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            return True
        except OSError as exc:
            log.warning("Task Manager policy failed: %s", exc)
            return False


def capabilities() -> str:
    if IS_WINDOWS:
        return ("Blocks Win/Alt+Tab/Alt+F4/Ctrl+Esc while locked, keeps the "
                "window fullscreen, optional Task Manager policy. "
                "Ctrl+Alt+Del cannot be blocked from a normal app.")
    return "Kiosk hardening is Windows-only (running on a dev machine)."
