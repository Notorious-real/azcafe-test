# ============================================================
#  AZ Cafe - Server Core
#  TCP socket server — manages all client PC connections
# ============================================================

import socket
import threading
import time
import sys
import os

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
import config
import database as db
from protocol import (
    MessageReader, send,
    CMD_PING, CMD_TIME_UPDATE, CMD_LOGIN_RESULT,
    EVT_REGISTER, EVT_HEARTBEAT, EVT_PONG,
    EVT_SESSION_ENDED, EVT_STATUS_UPDATE, EVT_MEMBER_LOGIN
)


class ClientConnection:
    """
    Represents one connected client PC.
    Holds the socket, PC info, and session state.
    """

    def __init__(self, sock, addr):
        self.sock        = sock
        self.addr        = addr
        self.pc_name     = None
        self.status      = config.STATUS_OFFLINE
        self.connected   = True
        self.reader      = MessageReader()

        # Session info
        self.session_id      = None
        self.session_user    = None
        self.remaining_secs  = 0
        self.paused          = False

        self.last_heartbeat  = time.time()

    def send(self, msg_type: str, **kwargs) -> bool:
        return send(self.sock, msg_type, **kwargs)

    def disconnect(self):
        self.connected = False
        self.status    = config.STATUS_OFFLINE
        try:
            self.sock.close()
        except OSError:
            pass

    def __repr__(self):
        return f"<Client {self.pc_name or self.addr} [{self.status}]>"


class AZCafeServer:
    """
    Main TCP server.
    - Listens for client connections on LAN
    - Spawns a thread per connected client
    - Notifies the admin app when PC list changes
    - Ticks session timers every second
    """

    def __init__(self, on_pc_update=None, on_status_msg=None):
        """
        on_pc_update(clients: dict)  — called when any PC connects/disconnects/changes
        on_status_msg(msg: str)      — called to push messages to status bar
        """
        self.clients       = {}          # pc_name → ClientConnection
        self._lock         = threading.Lock()
        self._running      = False

        self.on_pc_update  = on_pc_update  or (lambda c: None)
        self.on_status_msg = on_status_msg or (lambda m: None)

        self._server_sock  = None

    # ── Start / Stop ──────────────────────────────────────────

    def start(self):
        self._running = True
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()
        t2 = threading.Thread(target=self._timer_loop, daemon=True)
        t2.start()
        t3 = threading.Thread(target=self._heartbeat_watchdog, daemon=True)
        t3.start()
        self.on_status_msg(
            f"Server listening on port {config.SERVER_PORT}"
        )

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        with self._lock:
            for c in self.clients.values():
                c.disconnect()

    # ── Listen loop ───────────────────────────────────────────

    def _listen_loop(self):
        try:
            self._server_sock = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            self._server_sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            self._server_sock.bind((config.SERVER_HOST, config.SERVER_PORT))
            self._server_sock.listen(64)
            self._server_sock.settimeout(1.0)

            while self._running:
                try:
                    sock, addr = self._server_sock.accept()
                    sock.settimeout(10.0)
                    client = ClientConnection(sock, addr)
                    t = threading.Thread(
                        target=self._handle_client,
                        args=(client,), daemon=True
                    )
                    t.start()
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            self.on_status_msg(f"Server error: {e}")

    # ── Client handler ────────────────────────────────────────

    def _handle_client(self, client: ClientConnection):
        try:
            while self._running and client.connected:
                try:
                    data = client.sock.recv(config.BUFFER_SIZE)
                except socket.timeout:
                    # Check if client is still alive via heartbeat watchdog
                    continue
                except OSError:
                    break

                if not data:
                    break

                messages = client.reader.feed(data)
                for msg in messages:
                    self._dispatch(client, msg)

        finally:
            self._remove_client(client)

    def _dispatch(self, client: ClientConnection, msg: dict):
        """Route an incoming message to the correct handler."""
        msg_type = msg.get("type")
        data     = msg.get("data", {})

        if msg_type == EVT_REGISTER:
            self._on_register(client, data)

        elif msg_type == EVT_HEARTBEAT:
            client.last_heartbeat = time.time()
            client.send(CMD_PING)

        elif msg_type == EVT_PONG:
            client.last_heartbeat = time.time()

        elif msg_type == EVT_SESSION_ENDED:
            self._on_session_ended(client, data)

        elif msg_type == EVT_STATUS_UPDATE:
            client.status = data.get("status", client.status)
            self._notify_update()

        elif msg_type == EVT_MEMBER_LOGIN:
            self._on_member_login(client, data)

    def _on_member_login(self, client: ClientConnection, data: dict):
        """
        3B — Member self-login from the client lock screen.
        Verifies credentials, then if valid auto-starts a session
        using the member's available balance and the default rate.
        Sends CMD_LOGIN_RESULT back with success/fail details.
        """
        username = data.get("username", "").strip()
        password = data.get("password", "")

        member = db.verify_member_login(username, password)

        if not member:
            client.send(CMD_LOGIN_RESULT,
                        success=False,
                        reason="Wrong username or password.")
            return

        # Check balance (6.5 E — dynamic time based on balance)
        rate = db.get_pc_rate(client.pc_name)          # Rs per hour for this PC
        if member["balance"] <= 0 or rate <= 0:
            client.send(CMD_LOGIN_RESULT,
                        success=False,
                        reason=f"Insufficient balance: "
                               f"{config.CURRENCY} {member['balance']:.0f}")
            return

        # Calculate how many minutes the total balance covers (no cap)
        duration_mins = int((member["balance"] / rate) * 60)
        if duration_mins < 1:
            client.send(CMD_LOGIN_RESULT,
                        success=False,
                        reason=f"Balance too low for a session. "
                               f"({config.CURRENCY} {member['balance']:.0f})")
            return

        amount = round((duration_mins / 60.0) * rate, 2)

        # Deduct balance upfront (same as prepaid cash sessions)
        db.deduct_member_balance(member["id"], amount)

        # Record session in DB
        session_id = db.start_session(
            pc_name      =client.pc_name,
            member_id    =member["id"],
            duration_mins=duration_mins,
            amount       =amount,
            payment_type ="balance"
        )

        # Update server-side client state
        client.session_id     = session_id
        client.session_user   = member["name"]
        client.remaining_secs = duration_mins * 60
        client.status         = config.STATUS_ACTIVE
        client.paused         = False

        # Tell client: login ok, start session overlay
        client.send(CMD_LOGIN_RESULT,
                    success      =True,
                    member_name  =member["name"],
                    duration_secs=client.remaining_secs,
                    balance_used =amount,
                    balance_left =round(member["balance"] - amount, 2))

        # Send CMD_START_SESSION so client unlocks & shows game launcher
        client.send(CMD_START_SESSION,
                    user         =member["name"],
                    duration_secs=client.remaining_secs)

        self.on_status_msg(
            f"Member login: {member['name']} on {client.pc_name} "
            f"({duration_mins} min)"
        )
        self._notify_update()


    def _on_register(self, client: ClientConnection, data: dict):
        pc_name = data.get("pc_name", f"PC_{client.addr[0]}")
        client.pc_name = pc_name
        client.status  = config.STATUS_FREE
        client.last_heartbeat = time.time()

        with self._lock:
            # If same PC name reconnects, replace old connection
            if pc_name in self.clients:
                old = self.clients[pc_name]
                old.disconnect()
            self.clients[pc_name] = client

        # Remember PC in database (stores position etc.)
        db.save_pc(pc_name)

        self.on_status_msg(f"PC connected: {pc_name}")
        self._notify_update()

    def _on_session_ended(self, client: ClientConnection, data: dict):
        if client.session_id:
            db.end_session(client.session_id)
        client.session_id     = None
        client.session_user   = None
        client.remaining_secs = 0
        client.status         = config.STATUS_FREE
        self._notify_update()

    def _remove_client(self, client: ClientConnection):
        client.disconnect()
        with self._lock:
            if client.pc_name and self.clients.get(client.pc_name) is client:
                del self.clients[client.pc_name]
        if client.pc_name:
            self.on_status_msg(f"PC disconnected: {client.pc_name}")
        self._notify_update()

    # ── Timer loop ────────────────────────────────────────────

    # Warning thresholds in seconds — send a warning once each
    WARN_THRESHOLDS = [300, 120, 60]   # 5 min, 2 min, 1 min

    def _timer_loop(self):
        """
        Precise timer — uses monotonic clock to avoid drift.
        Ticks every second, syncs client every 10 seconds.
        Sends low-time warnings at 5min / 2min / 1min.
        """
        next_tick = time.monotonic() + 1.0

        while self._running:
            # Sleep until next tick (drift-corrected)
            now  = time.monotonic()
            wait = next_tick - now
            if wait > 0:
                time.sleep(wait)
            next_tick += 1.0

            with self._lock:
                clients = list(self.clients.values())

            changed = False
            for c in clients:
                if c.status != config.STATUS_ACTIVE or c.paused:
                    continue

                if c.remaining_secs > 0:
                    c.remaining_secs -= 1
                    changed = True

                    # Sync client every 10 seconds
                    if c.remaining_secs % 10 == 0:
                        c.send(CMD_TIME_UPDATE,
                               remaining=c.remaining_secs)

                    # Low-time warnings (sent once each threshold)
                    if not hasattr(c, '_warnings_sent'):
                        c._warnings_sent = set()

                    for threshold in self.WARN_THRESHOLDS:
                        if (c.remaining_secs == threshold
                                and threshold not in c._warnings_sent):
                            c._warnings_sent.add(threshold)
                            mins = threshold // 60
                            c.send("LOW_TIME_WARNING",
                                   remaining=c.remaining_secs,
                                   minutes=mins)
                            # Also notify admin UI
                            self.on_status_msg(
                                f"⚠ {c.pc_name} — {mins} min remaining"
                                f" ({c.session_user})"
                            )

                else:
                    # Time is up
                    c.status = config.STATUS_FREE
                    c._warnings_sent = set()
                    c.send("SESSION_EXPIRED")
                    self._on_session_ended(c, {})
                    changed = True

            if changed:
                self._notify_update()

    # ── Heartbeat watchdog ────────────────────────────────────

    def _heartbeat_watchdog(self):
        """Detects dead clients that stopped sending heartbeats."""
        while self._running:
            time.sleep(10)
            now = time.time()
            with self._lock:
                dead = [
                    c for c in self.clients.values()
                    if now - c.last_heartbeat > 30   # 30s timeout
                ]
            for c in dead:
                self.on_status_msg(f"PC timed out: {c.pc_name}")
                self._remove_client(c)

    # ── Commands (called from admin UI) ──────────────────────

    def start_session(self, pc_name: str, user: str,
                      duration_mins: int, amount: float,
                      member_id=None, payment_type="cash",
                      discount_pct: float = 0.0,
                      discount_amount: float = 0.0) -> bool:
        client = self._get(pc_name)
        if not client:
            return False

        session_id = db.start_session(
            pc_name, member_id=member_id,
            guest_name=user if not member_id else None,
            duration_mins=duration_mins,
            amount=amount, payment_type=payment_type,
            discount_pct=discount_pct,
            discount_amount=discount_amount
        )

        client.session_id     = session_id
        client.session_user   = user
        client.remaining_secs = duration_mins * 60
        client.status         = config.STATUS_ACTIVE
        client.paused         = False

        ok = client.send(
            "START_SESSION",
            user=user,
            duration_secs=client.remaining_secs
        )
        self._notify_update()
        return ok

    def stop_session(self, pc_name: str, actual_amount: float = None) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        if client.session_id:
            db.end_session(client.session_id, actual_amount=actual_amount)
        client.session_id     = None
        client.session_user   = None
        client.remaining_secs = 0
        client.status         = config.STATUS_FREE
        ok = client.send("STOP_SESSION")
        self._notify_update()
        return ok

    def lock_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.status = config.STATUS_LOCKED
        ok = client.send("LOCK")
        self._notify_update()
        return ok

    def unlock_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.status = config.STATUS_FREE
        ok = client.send("UNLOCK")
        self._notify_update()
        return ok

    def send_message(self, pc_name: str, message: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        return client.send("MESSAGE", text=message)

    def send_message_all(self, message: str):
        with self._lock:
            clients = list(self.clients.values())
        for c in clients:
            c.send("MESSAGE", text=message)

    def restart_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        return client.send("RESTART")

    def restart_all(self):
        with self._lock:
            clients = list(self.clients.values())
        for c in clients:
            c.send("RESTART")

    def shutdown_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        return client.send("SHUTDOWN")

    def shutdown_all(self):
        with self._lock:
            clients = list(self.clients.values())
        for c in clients:
            c.send("SHUTDOWN")

    def pause_session(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.paused = True
        client.status = config.STATUS_PAUSED
        ok = client.send("PAUSE_SESSION")
        self._notify_update()
        return ok

    def resume_session(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.paused = False
        client.status = config.STATUS_ACTIVE
        ok = client.send("RESUME_SESSION")
        self._notify_update()
        return ok

    def add_time(self, pc_name: str, extra_mins: int) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.remaining_secs += extra_mins * 60
        ok = client.send(CMD_TIME_UPDATE, remaining=client.remaining_secs)
        self._notify_update()
        return ok

    # ── Helpers ───────────────────────────────────────────────

    def _get(self, pc_name: str):
        with self._lock:
            return self.clients.get(pc_name)

    def _notify_update(self):
        """Send a snapshot of all clients to the admin UI."""
        with self._lock:
            snapshot = dict(self.clients)
        self.on_pc_update(snapshot)

    def get_clients_snapshot(self) -> dict:
        with self._lock:
            return dict(self.clients)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for c in self.clients.values()
                if c.status == config.STATUS_ACTIVE
            )

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self.clients)
