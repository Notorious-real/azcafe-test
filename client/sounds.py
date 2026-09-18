# ============================================================
#  AZ Cafe - Client sound cues  (Phase 7D)
#  Small, dependency-free chimes built from winsound.Beep so the
#  customer hears what is happening (session started, low time,
#  time up, message from the counter).
#
#  On non-Windows machines every call is a polite no-op, and cues
#  never block the UI thread (they play on a worker thread).
# ============================================================

import sys
import threading

try:                                    # Windows only
    import winsound
except ImportError:                     # pragma: no cover - dev machines
    winsound = None

CUES = {
    "start":    [(880, 90), (1320, 120)],
    "warning":  [(1200, 120), (0, 60), (1200, 120)],
    "expire":   [(600, 200), (400, 260)],
    "message":  [(1000, 80), (1000, 80)],
    "unlock":   [(700, 70), (900, 70), (1100, 110)],
    "error":    [(300, 220)],
    "click":    [(1400, 35)],
}

_enabled = True
_lock = threading.Lock()


def set_enabled(enabled: bool):
    """Driven by the server's `sound_enabled` setting (pushed on connect)."""
    global _enabled
    _enabled = bool(enabled)


def is_enabled() -> bool:
    return _enabled


def supported() -> bool:
    return winsound is not None


def play(cue: str):
    """Play a named cue. Returns immediately."""
    if not _enabled or winsound is None:
        return
    pattern = CUES.get(cue)
    if not pattern:
        return
    threading.Thread(target=_play_pattern, args=(pattern,), daemon=True).start()


def _play_pattern(pattern):
    with _lock:                          # Beep blocks; keep cues serialised
        for frequency, duration in pattern:
            try:
                if frequency <= 0:
                    winsound.Beep(40, duration)      # near-silent gap
                else:
                    winsound.Beep(frequency, duration)
            except (RuntimeError, ValueError, OSError):
                return


def play_system(cue: str = "message"):
    """Fallback that uses a Windows system sound alias."""
    if not _enabled or winsound is None:
        return
    aliases = {
        "message": winsound.MB_ICONASTERISK,
        "error": winsound.MB_ICONHAND,
        "warning": winsound.MB_ICONEXCLAMATION,
    }
    try:
        winsound.MessageBeep(aliases.get(cue, winsound.MB_OK))
    except (RuntimeError, ValueError, OSError):
        pass


def platform_note() -> str:
    return "Windows beeps" if sys.platform.startswith("win") else "disabled (not Windows)"
