# ============================================================
#  AZ Cafe - Communication Protocol
#  Newline-delimited JSON messages over TCP.
#
#  Envelope:
#      {"type": "CMD_or_EVT_name", "v": 2, "data": {...}}
#
#  All message type strings live here as constants so that
#  server and client can never drift apart on a typo.
# ============================================================

import json

PROTOCOL_VERSION = 2

# ── Commands (Server → Client) ──────────────────────────────
CMD_START_SESSION      = "START_SESSION"       # begin a paid session
CMD_STOP_SESSION       = "STOP_SESSION"        # end session, show lock screen
CMD_PAUSE_SESSION      = "PAUSE_SESSION"       # freeze the timer
CMD_RESUME_SESSION     = "RESUME_SESSION"      # unfreeze the timer
CMD_LOCK               = "LOCK"                # lock this PC now
CMD_UNLOCK             = "UNLOCK"              # admin override unlock
CMD_SHUTDOWN           = "SHUTDOWN"
CMD_RESTART            = "RESTART"
CMD_MESSAGE            = "MESSAGE"             # popup text on client
CMD_TIME_UPDATE        = "TIME_UPDATE"         # authoritative remaining seconds
CMD_LOW_TIME_WARNING   = "LOW_TIME_WARNING"    # 5 / 2 / 1 minute warnings
CMD_SESSION_EXPIRED    = "SESSION_EXPIRED"     # time is up, lock the PC
CMD_CONFIG             = "CONFIG"              # shop name, sounds, kiosk flags
CMD_PING               = "PING"

# ── Events (Client → Server) ────────────────────────────────
EVT_REGISTER           = "REGISTER"            # client announces itself
EVT_HEARTBEAT          = "HEARTBEAT"
EVT_PONG               = "PONG"
EVT_SESSION_ENDED      = "SESSION_ENDED"       # customer pressed "End Session"
EVT_STATUS_UPDATE      = "STATUS_UPDATE"
EVT_MEMBER_LOGIN       = "MEMBER_LOGIN"        # self-service login from lock screen
EVT_ADMIN_UNLOCK_REQ   = "ADMIN_UNLOCK_REQ"    # password check for the corner unlock

# ── Results (Server → Client) ───────────────────────────────
CMD_LOGIN_RESULT          = "LOGIN_RESULT"
CMD_ADMIN_UNLOCK_RESULT   = "ADMIN_UNLOCK_RESULT"

# Statuses shared by server, client and UI
STATUS_FREE    = "FREE"
STATUS_ACTIVE  = "ACTIVE"
STATUS_LOCKED  = "LOCKED"
STATUS_OFFLINE = "OFFLINE"
STATUS_PAUSED  = "PAUSED"

# Session row states (database)
SESSION_ACTIVE    = "active"
SESSION_SUSPENDED = "suspended"
SESSION_COMPLETED = "completed"
SESSION_OPEN_STATES = (SESSION_ACTIVE, SESSION_SUSPENDED)

MAX_BUFFER = 256 * 1024   # protect against a client that never sends a newline


def build_message(msg_type: str, **kwargs) -> bytes:
    """Serialise one message: {"type": ..., "v": ..., "data": {...}}\\n"""
    payload = {"type": msg_type, "v": PROTOCOL_VERSION, "data": kwargs}
    return (json.dumps(payload, default=str) + "\n").encode("utf-8")


def parse_message(raw: str):
    """Parse a JSON line into a dict, or None when malformed."""
    try:
        msg = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(msg, dict) or "type" not in msg:
        return None
    return msg


def send(sock, msg_type: str, **kwargs) -> bool:
    """Send a message. Returns False instead of raising on a dead socket."""
    try:
        sock.sendall(build_message(msg_type, **kwargs))
        return True
    except OSError:
        return False


class MessageReader:
    """
    Incremental newline-delimited JSON reader for a byte stream.
    Handles partial reads and several messages arriving at once.
    """

    def __init__(self, max_buffer: int = MAX_BUFFER):
        self._buffer = ""
        self.max_buffer = max_buffer
        self.dropped = 0

    def feed(self, data: bytes) -> list:
        self._buffer += data.decode("utf-8", errors="replace")

        if len(self._buffer) > self.max_buffer and "\n" not in self._buffer:
            # Runaway sender: drop the junk instead of eating all RAM.
            self.dropped += 1
            self._buffer = ""
            return []

        messages = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            parsed = parse_message(line)
            if parsed:
                messages.append(parsed)
        return messages

    def reset(self):
        self._buffer = ""
