# ============================================================
#  AZ Cafe - Client Core
#  Talks to the admin server. Holds no database and no money logic:
#  the server is the single source of truth (this is what made the
#  old admin-unlock button crash on fresh client PCs).
# ============================================================

import socket
import threading
import time

import applog
import client_config
import config
from protocol import (
    CMD_ADMIN_UNLOCK_RESULT, CMD_CONFIG, CMD_LOCK, CMD_LOGIN_RESULT,
    CMD_LOW_TIME_WARNING, CMD_MESSAGE, CMD_PAUSE_SESSION, CMD_PING,
    CMD_RESTART, CMD_RESUME_SESSION, CMD_SESSION_EXPIRED, CMD_SHUTDOWN,
    CMD_START_SESSION, CMD_STOP_SESSION, CMD_TIME_UPDATE, CMD_UNLOCK,
    PROTOCOL_VERSION, MessageReader, send,
)

log = applog.get_logger("client")

EVENTS = (
    "connected", "disconnected", "session_started", "session_stopped",
    "session_paused", "session_resumed", "locked", "unlocked",
    "time_update", "message", "shutdown", "restart", "session_expired",
    "low_time_warning", "login_result", "admin_unlock_result", "config",
)


class AZCafeClient:
    """
    Connection + message dispatch for one gaming PC.

    on_event(event, **data) is always called on a worker thread — the UI
    layer is responsible for hopping onto the Tk main loop.
    """

    def __init__(self, on_event, server_ip=None, server_port=None, pc_name=None):
        settings = client_config.load_client_config()
        self.server_ip = server_ip or settings["server_ip"]
        self.server_port = int(server_port or settings["server_port"])
        self.pc_name = pc_name or settings["pc_name"]

        self.on_event = on_event
        self.settings = {}

        self._sock = None
        self._reader = MessageReader()
        self._connected = False
        self._running = True
        self._send_lock = threading.Lock()
        self._retry_delay = 2

        # Local mirror of the server's session state (display only)
        self.session = {"active": False, "user": "", "remaining": 0, "paused": False}

    # ── lifecycle ───────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self._close_socket()

    @property
    def connected(self) -> bool:
        return self._connected

    def _close_socket(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ── connection ──────────────────────────────────────────
    def _connect_loop(self):
        while self._running:
            if not self.server_ip:
                self.on_event("config_missing")
                time.sleep(5)
                continue
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                sock.connect((self.server_ip, self.server_port))
                sock.settimeout(1.0)
                self._sock = sock
                self._connected = True
                self._retry_delay = 2

                self._send("REGISTER", pc_name=self.pc_name,
                           version=PROTOCOL_VERSION,
                           hostname=self.pc_name)
                log.info("Connected to %s:%s", self.server_ip, self.server_port)
                self.on_event("connected")

                heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
                heartbeat.start()
                self._recv_loop()
            except (ConnectionRefusedError, socket.timeout, OSError) as exc:
                log.debug("Connect failed: %s", exc)
            finally:
                self._close_socket()
                self.on_event("disconnected")
            if self._running:
                time.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, 15)

    def _recv_loop(self):
        self._reader.reset()
        while self._running and self._connected:
            try:
                data = self._sock.recv(config.BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            for message in self._reader.feed(data):
                try:
                    self._dispatch(message)
                except Exception:                              # noqa: BLE001
                    log.exception("Bad message from server")

    def _heartbeat_loop(self):
        while self._running and self._connected:
            time.sleep(config.HEARTBEAT_INTERVAL)
            if not self._connected:
                break
            if not self._send("HEARTBEAT", pc_name=self.pc_name):
                break

    def _send(self, msg_type: str, **kwargs) -> bool:
        if not self._connected or not self._sock:
            return False
        with self._send_lock:
            return send(self._sock, msg_type, **kwargs)

    # ── dispatch ────────────────────────────────────────────
    def _dispatch(self, msg: dict):
        msg_type = msg.get("type", "")
        data = msg.get("data") or {}

        if msg_type == CMD_START_SESSION:
            self.session.update(active=True,
                                user=data.get("user", "Guest"),
                                remaining=data.get("duration_secs", 3600),
                                paused=False)
            self.on_event("session_started", user=data.get("user", "Guest"),
                          duration_secs=data.get("duration_secs", 3600),
                          resumed=bool(data.get("resumed")))

        elif msg_type == CMD_STOP_SESSION:
            self.session.update(active=False, user="", remaining=0, paused=False)
            self.on_event("session_stopped", reason=data.get("reason", ""))

        elif msg_type == CMD_SESSION_EXPIRED:
            self.session.update(active=False, remaining=0, paused=False)
            self.on_event("session_expired")

        elif msg_type == CMD_PAUSE_SESSION:
            self.session["paused"] = True
            self.on_event("session_paused")

        elif msg_type == CMD_RESUME_SESSION:
            self.session["paused"] = False
            self.on_event("session_resumed")

        elif msg_type == CMD_LOCK:
            self.on_event("locked")

        elif msg_type == CMD_UNLOCK:
            self.on_event("unlocked")

        elif msg_type == CMD_TIME_UPDATE:
            remaining = int(data.get("remaining", 0))
            self.session["remaining"] = remaining
            self.on_event("time_update", remaining=remaining)

        elif msg_type == CMD_LOW_TIME_WARNING:
            self.on_event("low_time_warning",
                          remaining=data.get("remaining", 0),
                          minutes=data.get("minutes", 0))

        elif msg_type == CMD_MESSAGE:
            self.on_event("message", text=data.get("text", ""))

        elif msg_type == CMD_CONFIG:
            self.settings = dict(data)
            self.on_event("config", **data)

        elif msg_type == CMD_SHUTDOWN:
            self.on_event("shutdown")

        elif msg_type == CMD_RESTART:
            self.on_event("restart")

        elif msg_type == CMD_LOGIN_RESULT:
            self.on_event("login_result",
                          success=bool(data.get("success")),
                          reason=data.get("reason", ""),
                          member_name=data.get("member_name", ""),
                          duration_secs=data.get("duration_secs", 0),
                          balance_used=data.get("balance_used", 0),
                          balance_left=data.get("balance_left", 0))

        elif msg_type == CMD_ADMIN_UNLOCK_RESULT:
            self.on_event("admin_unlock_result",
                          success=bool(data.get("success")),
                          reason=data.get("reason", ""))

        elif msg_type == CMD_PING:
            self._send("PONG")

    # ── public helpers ──────────────────────────────────────
    def send_member_login(self, username: str, password: str) -> bool:
        return self._send("MEMBER_LOGIN", pc_name=self.pc_name,
                          username=username, password=password)

    def send_admin_unlock(self, password: str) -> bool:
        """The server verifies the password — clients hold no database."""
        return self._send("ADMIN_UNLOCK_REQ", pc_name=self.pc_name,
                          password=password)

    def report_session_ended(self) -> bool:
        return self._send("SESSION_ENDED", pc_name=self.pc_name)

    def send_status(self, status: str) -> bool:
        return self._send("STATUS_UPDATE", pc_name=self.pc_name, status=status)
