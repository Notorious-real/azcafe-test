# ============================================================
#  AZ Cafe - Communication Protocol
#  Defines all messages exchanged between server and clients
#  Both server and client import this file
# ============================================================

import json

# ── Command types (Server → Client) ─────────────────────────
CMD_START_SESSION   = "START_SESSION"    # Start a session on client PC
CMD_STOP_SESSION    = "STOP_SESSION"     # End session, lock screen
CMD_PAUSE_SESSION   = "PAUSE_SESSION"    # Pause timer (screen stays unlocked)
CMD_RESUME_SESSION  = "RESUME_SESSION"   # Resume paused session
CMD_LOCK            = "LOCK"             # Lock screen immediately
CMD_UNLOCK          = "UNLOCK"           # Unlock screen (admin override)
CMD_SHUTDOWN        = "SHUTDOWN"         # Shutdown the PC
CMD_RESTART         = "RESTART"          # Restart the PC
CMD_MESSAGE         = "MESSAGE"          # Show popup message on client
CMD_TIME_UPDATE     = "TIME_UPDATE"      # Send remaining time to client
CMD_PING            = "PING"             # Heartbeat check

# ── Event types (Client → Server) ───────────────────────────
EVT_REGISTER        = "REGISTER"         # Client registers itself on connect
EVT_HEARTBEAT       = "HEARTBEAT"        # Client is alive
EVT_SESSION_ENDED   = "SESSION_ENDED"    # Client reports session ended (time up)
EVT_ADMIN_UNLOCK    = "ADMIN_UNLOCK"     # Admin unlocked from client side
EVT_STATUS_UPDATE   = "STATUS_UPDATE"    # Client sends its current status
EVT_PONG            = "PONG"             # Response to ping
EVT_MEMBER_LOGIN    = "MEMBER_LOGIN"     # Member logs in from client lock screen

# ── Login result (Server → Client) ───────────────────────────
CMD_LOGIN_RESULT    = "LOGIN_RESULT"     # success/fail + session details


def build_message(msg_type: str, **kwargs) -> bytes:
    """
    Build a JSON message to send over the socket.
    All messages follow this structure:
    {
        "type": "CMD_or_EVT_name",
        "data": { ...optional key-value pairs... }
    }
    """
    payload = {"type": msg_type, "data": kwargs}
    raw = json.dumps(payload) + "\n"   # newline = message delimiter
    return raw.encode("utf-8")


def parse_message(raw: str) -> dict:
    """
    Parse a received JSON string into a dict.
    Returns None if parsing fails.
    """
    try:
        return json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def send(sock, msg_type: str, **kwargs) -> bool:
    """
    Send a message through a socket.
    Returns True on success, False on failure.
    """
    try:
        sock.sendall(build_message(msg_type, **kwargs))
        return True
    except OSError:
        return False


class MessageReader:
    """
    Reads newline-delimited JSON messages from a socket stream.
    Handles partial reads and multiple messages in one recv() call.

    Usage:
        reader = MessageReader()
        ...
        data = sock.recv(BUFFER_SIZE)
        messages = reader.feed(data)
        for msg in messages:
            handle(msg)
    """

    def __init__(self):
        self._buffer = ""

    def feed(self, data: bytes) -> list:
        """
        Feed raw bytes into the reader.
        Returns a list of fully parsed messages (may be empty).
        """
        self._buffer += data.decode("utf-8", errors="replace")
        messages = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                parsed = parse_message(line)
                if parsed:
                    messages.append(parsed)
        return messages

    def reset(self):
        self._buffer = ""
