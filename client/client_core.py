# ============================================================
#  AZ Cafe - Client Application
#  Runs on each gaming PC
#  - Connects to server automatically
#  - Shows lock screen when no session
#  - Receives commands from admin
# ============================================================

import tkinter as tk
from tkinter import messagebox
import socket
import threading
import time
import sys
import os
import subprocess

# ── Path setup ───────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config
from protocol import MessageReader, send

# ── Client config (edit SERVER_IP before deploying) ──────────
SERVER_IP   = "192.168.100.2"   # ← Change to admin PC's local IP
PC_NAME     = socket.gethostname()   # Auto-uses this PC's name


class AZCafeClient:
    """
    Core client logic — handles server connection,
    message dispatch, and session state.
    Separated from UI so it can be tested independently.
    """

    def __init__(self, on_event):
        """
        on_event(event, **data) — called on UI thread via after()
        Events:
            connected         — server connection established
            disconnected      — lost connection to server
            session_started   — user, duration_secs
            session_stopped   — (no data)
            session_paused    — (no data)
            session_resumed   — (no data)
            locked            — (no data)
            unlocked          — (no data)
            time_update       — remaining (seconds)
            message           — text
            shutdown          — (no data)
            restart           — (no data)
            session_expired   — (no data)
        """
        self.on_event       = on_event
        self._sock          = None
        self._reader        = MessageReader()
        self._connected     = False
        self._running       = True
        self._session_active= False

    def start(self):
        t = threading.Thread(target=self._connect_loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    # ── Connection loop ───────────────────────────────────────

    def _connect_loop(self):
        """Keeps trying to connect to server. Auto-reconnects on drop."""
        while self._running:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(10)
                self._sock.connect((SERVER_IP, config.SERVER_PORT))
                self._sock.settimeout(None)
                self._connected = True

                # Register with server
                send(self._sock, "REGISTER", pc_name=PC_NAME)
                self.on_event("connected")

                # Start heartbeat
                hb = threading.Thread(target=self._heartbeat, daemon=True)
                hb.start()

                self._recv_loop()

            except (ConnectionRefusedError, socket.timeout, OSError):
                pass
            finally:
                self._connected = False
                if self._sock:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                self.on_event("disconnected")

            if self._running:
                time.sleep(config.RECONNECT_DELAY)

    def _recv_loop(self):
        """Receive and dispatch messages from server."""
        self._reader.reset()
        while self._running and self._connected:
            try:
                data = self._sock.recv(config.BUFFER_SIZE)
                if not data:
                    break
                messages = self._reader.feed(data)
                for msg in messages:
                    self._dispatch(msg)
            except OSError:
                break

    def _heartbeat(self):
        """Send heartbeat every N seconds to keep connection alive."""
        while self._running and self._connected:
            time.sleep(config.HEARTBEAT_INTERVAL)
            if not self._connected:
                break
            try:
                send(self._sock, "HEARTBEAT", pc_name=PC_NAME)
            except OSError:
                break

    # ── Dispatch ──────────────────────────────────────────────

    def _dispatch(self, msg: dict):
        msg_type = msg.get("type", "")
        data     = msg.get("data", {})

        if msg_type == "START_SESSION":
            self._session_active = True
            self.on_event("session_started",
                          user=data.get("user", "Guest"),
                          duration_secs=data.get("duration_secs", 3600))

        elif msg_type == "STOP_SESSION":
            self._session_active = False
            self.on_event("session_stopped")

        elif msg_type == "SESSION_EXPIRED":
            self._session_active = False
            self.on_event("session_expired")

        elif msg_type == "PAUSE_SESSION":
            self.on_event("session_paused")

        elif msg_type == "RESUME_SESSION":
            self.on_event("session_resumed")

        elif msg_type == "LOCK":
            self.on_event("locked")

        elif msg_type == "UNLOCK":
            self.on_event("unlocked")

        elif msg_type == "TIME_UPDATE":
            self.on_event("time_update",
                          remaining=data.get("remaining", 0))

        elif msg_type == "MESSAGE":
            self.on_event("message", text=data.get("text", ""))

        elif msg_type == "SHUTDOWN":
            self.on_event("shutdown")
            time.sleep(2)
            subprocess.run(["shutdown", "/s", "/t", "5"])

        elif msg_type == "RESTART":
            self.on_event("restart")
            time.sleep(2)
            subprocess.run(["shutdown", "/r", "/t", "5"])

        elif msg_type == "LOW_TIME_WARNING":
            self.on_event("low_time_warning",
                          remaining=data.get("remaining", 0),
                          minutes=data.get("minutes", 0))

        elif msg_type == "LOGIN_RESULT":
            self.on_event("login_result",
                          success=data.get("success", False),
                          reason=data.get("reason", ""),
                          member_name=data.get("member_name", ""),
                          duration_secs=data.get("duration_secs", 0),
                          balance_used=data.get("balance_used", 0),
                          balance_left=data.get("balance_left", 0))

        elif msg_type == "PING":
            try:
                send(self._sock, "PONG")
            except OSError:
                pass

    def send_member_login(self, username: str, password: str) -> bool:
        """Send a member login request to server."""
        if self._connected and self._sock:
            try:
                return send(self._sock, "MEMBER_LOGIN",
                            pc_name=PC_NAME,
                            username=username,
                            password=password)
            except OSError:
                return False
        return False

    def report_session_ended(self):
        """Called when timer reaches zero — notify server."""
        if self._connected:
            try:
                send(self._sock, "SESSION_ENDED", pc_name=PC_NAME)
            except OSError:
                pass
