# ============================================================
#  AZ Cafe - Server Core
#  TCP server that owns all session state, timers and money.
#
#  Design rules:
#    * The server is the single source of truth. Clients only render.
#    * A session survives a client disconnect: it is suspended and
#      resumed on reconnect (see _suspend_client_session / _recover).
#    * Every session that ends early is settled fairly (see
#      database.settle_session) and written to the ledger.
#    * No UI or Tkinter imports here — this module is headless-testable.
# ============================================================

import socket
import threading
import time

import applog
import games
import config
import database as db
import paths
from protocol import (
    CMD_ADMIN_UNLOCK_RESULT, CMD_CONFIG, CMD_LOCK, CMD_LOGIN_RESULT,
    CMD_LOW_TIME_WARNING, CMD_MESSAGE, CMD_PAUSE_SESSION,
    CMD_RESTART, CMD_RESUME_SESSION, CMD_SESSION_EXPIRED, CMD_SHUTDOWN,
    CMD_START_SESSION, CMD_STOP_SESSION, CMD_TIME_UPDATE, CMD_UNLOCK,
    EVT_ADMIN_UNLOCK_REQ, EVT_HEARTBEAT, EVT_MEMBER_LOGIN, EVT_PONG,
    EVT_REGISTER, EVT_SESSION_ENDED, EVT_STATUS_UPDATE,
    PROTOCOL_VERSION, STATUS_ACTIVE, STATUS_FREE, STATUS_LOCKED,
    STATUS_OFFLINE, STATUS_PAUSED, MessageReader, send,
)

log = applog.get_logger("server")

HEARTBEAT_TIMEOUT = 30      # seconds without a heartbeat → PC considered gone
LIVE_PERSIST_INTERVAL = 10  # seconds between live countdown snapshots
SWEEP_INTERVAL = 60         # how often stale suspended sessions are settled


def implied_rate(session: dict) -> float:
    """Rs/hour implied by the booking (so old plans keep their price)."""
    duration = int(session.get("duration_mins") or 0)
    amount = float(session.get("amount_charged") or 0)
    if duration > 0 and amount > 0:
        return (amount / duration) * 60.0
    return db.get_default_rate()


def charge_for_used(session: dict, used_secs: int) -> float:
    prepaid = float(session.get("amount_charged") or 0)
    charge = (max(0, used_secs) / 3600.0) * implied_rate(session)
    return round(min(charge, prepaid) if prepaid else round(charge, 2), 2)


class ClientConnection:
    """One connected gaming PC."""

    def __init__(self, sock, addr, pc_name=None):
        self.sock = sock
        self.addr = addr
        self.pc_name = pc_name
        self.status = STATUS_OFFLINE
        self.connected = True
        self.reader = MessageReader()

        self.session_id = None
        self.session_user = ""
        self.remaining_secs = 0
        self.paused = False
        self.suspended = False

        self.last_heartbeat = time.time()
        self._warnings_sent = set()
        self._send_lock = threading.Lock()

    # ── socket helpers ───────────────────────────────────────
    def send(self, msg_type: str, **kwargs) -> bool:
        """Thread-safe send (timer, UI and reader threads all talk here)."""
        if not self.connected:
            return False
        with self._send_lock:
            return send(self.sock, msg_type, **kwargs)

    def disconnect(self):
        self.connected = False
        self.status = STATUS_OFFLINE
        try:
            self.sock.close()
        except OSError:
            pass

    def apply_session(self, session: dict, remaining_secs: int = None,
                      user: str = None):
        self.session_id = session.get("id")
        self.session_user = user or _session_user_name(session)
        self.remaining_secs = (int(session.get("remaining_secs") or 0)
                               if remaining_secs is None else int(remaining_secs))
        self.paused = bool(session.get("paused"))
        self.status = STATUS_PAUSED if self.paused else STATUS_ACTIVE
        self._warnings_sent = set()

    def clear_session(self):
        self.session_id = None
        self.session_user = ""
        self.remaining_secs = 0
        self.paused = False
        self.suspended = False
        self._warnings_sent = set()

    def __repr__(self):
        return f"<Client {self.pc_name or self.addr} [{self.status}]>"


def _session_user_name(session: dict) -> str:
    if not session:
        return ""
    if session.get("guest_name"):
        return session["guest_name"]
    if session.get("member_id"):
        member = db.get_member_by_id(session["member_id"])
        if member:
            return member["name"]
        return f"Member #{session['member_id']}"
    return "Guest"


class AZCafeServer:
    """Listens for clients, owns the timers, settles the money."""

    def __init__(self, on_pc_update=None, on_status_msg=None, on_session_event=None):
        self.clients = {}
        self._lock = threading.RLock()
        self._running = False

        self.on_pc_update = on_pc_update or (lambda clients: None)
        self.on_status_msg = on_status_msg or (lambda msg: None)
        self.on_session_event = on_session_event or (lambda kind, payload: None)

        self._server_sock = None
        self.warn_thresholds = [300, 120, 60]
        self.settings_cache = {}
        self.reload_settings()

    # ── settings ─────────────────────────────────────────────

    def reload_settings(self):
        """Cache the settings the server itself enforces."""
        warn_mins = db.get_int_setting("low_time_warning", 5)
        thresholds = {warn_mins * 60, 120, 60}
        self.warn_thresholds = sorted((t for t in thresholds if t > 0), reverse=True)
        self.settings_cache = {
            "shop_name": db.get_setting("shop_name", config.APP_NAME),
            "currency": db.get_setting("currency", config.CURRENCY),
            "low_time_warning": warn_mins,
            "auto_lock": db.get_bool_setting("auto_lock", True),
            "sound_enabled": db.get_bool_setting("sound_enabled", True),
            "kiosk_mode": db.get_bool_setting("kiosk_mode", True),
            "lock_task_manager": db.get_bool_setting("lock_task_manager", False),
            "auto_print_receipt": db.get_bool_setting("auto_print_receipt", True),
            "receipt_printer": db.get_setting("receipt_printer", ""),
            "games": games.load_games(),
            "protocol_version": PROTOCOL_VERSION,
        }

    def _config_payload(self) -> dict:
        return dict(self.settings_cache, app_name=config.APP_NAME,
                    server_time=time.time())

    # ── lifecycle ────────────────────────────────────────────

    def start(self):
        self._running = True
        self.reload_settings()

        # Sessions left open by a previous run are recoverable: a client
        # that is still running will reconnect and resume them. The sweep
        # loop settles anything that never comes back.
        try:
            held = db.hold_sessions_across_restart()
            if held:
                log.info("Holding %d session(s) for reconnect after restart", held)
        except Exception as exc:                              # noqa: BLE001
            log.warning("Session hold failed: %s", exc)

        for target, name in ((self._listen_loop, "listen"),
                             (self._timer_loop, "timer"),
                             (self._watchdog_loop, "watchdog"),
                             (self._persist_loop, "persist"),
                             (self._sweep_loop, "sweep")):
            threading.Thread(target=target, name=f"azcafe-{name}", daemon=True).start()

        self.on_status_msg(f"Server listening on port {config.SERVER_PORT}")
        log.info("Server started on %s:%s", config.SERVER_HOST, config.SERVER_PORT)

    def stop(self):
        self._running = False
        try:
            with self._lock:
                for client in list(self.clients.values()):
                    if client.session_id:
                        self._suspend_client_session(client, "server shutting down")
                    client.disconnect()
        except Exception as exc:                              # noqa: BLE001
            log.warning("Error while shutting down clients: %s", exc)
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        log.info("Server stopped")

    # ── network loops ────────────────────────────────────────

    def _listen_loop(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((config.SERVER_HOST, config.SERVER_PORT))
            self._server_sock.listen(64)
            self._server_sock.settimeout(1.0)

            while self._running:
                try:
                    sock, addr = self._server_sock.accept()
                    sock.settimeout(1.0)
                    client = ClientConnection(sock, addr)
                    threading.Thread(target=self._handle_client,
                                     args=(client,), daemon=True).start()
                except socket.timeout:
                    continue
                except OSError:
                    break
        except OSError as exc:
            message = (f"Cannot listen on port {config.SERVER_PORT}: {exc}\n"
                       f"Another program (or a second AZ Cafe window) may be using it.")
            log.error(message)
            self.on_status_msg("SERVER FAILED — " + message.splitlines()[0])
        except Exception as exc:                              # noqa: BLE001
            log.exception("Listen loop crashed")
            self.on_status_msg(f"Server error: {exc}")

    def _handle_client(self, client: ClientConnection):
        try:
            while self._running and client.connected:
                try:
                    data = client.sock.recv(config.BUFFER_SIZE)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                for msg in client.reader.feed(data):
                    try:
                        self._dispatch(client, msg)
                    except Exception as exc:                  # noqa: BLE001
                        log.exception("Handler failed for %s", client)
                        self.on_status_msg(f"Error handling message: {exc}")
        finally:
            self._remove_client(client, "connection closed")

    def _dispatch(self, client: ClientConnection, msg: dict):
        msg_type = msg.get("type")
        data = msg.get("data") or {}

        if msg_type == EVT_REGISTER:
            self._on_register(client, data)
        elif msg_type == EVT_HEARTBEAT:
            client.last_heartbeat = time.time()
        elif msg_type == EVT_PONG:
            client.last_heartbeat = time.time()
        elif msg_type == EVT_SESSION_ENDED:
            self._on_session_ended(client, data)
        elif msg_type == EVT_STATUS_UPDATE:
            client.status = data.get("status", client.status)
            self._notify_update()
        elif msg_type == EVT_MEMBER_LOGIN:
            self._on_member_login(client, data)
        elif msg_type == EVT_ADMIN_UNLOCK_REQ:
            self._on_admin_unlock_request(client, data)
        else:
            log.debug("Unhandled message %s from %s", msg_type, client)

    # ── registration & recovery ──────────────────────────────

    def _on_register(self, client: ClientConnection, data: dict):
        pc_name = (data or {}).get("pc_name") or f"PC_{client.addr[0]}"
        client.pc_name = pc_name
        client.last_heartbeat = time.time()

        with self._lock:
            old = self.clients.get(pc_name)
            if old is not None and old is not client:
                log.info("Replacing stale connection for %s", pc_name)
                if old.session_id and old.session_id == client.session_id:
                    pass
                old.disconnect()
            self.clients[pc_name] = client

        db.save_pc(pc_name)
        client.send(CMD_CONFIG, **self._config_payload())

        recovered = self._recover_session(client)
        if not recovered:
            client.status = STATUS_FREE
            # Tell the client to lock unless it has a session the server knows about
            client.send(CMD_STOP_SESSION, reason="no active session")

        self.on_status_msg(f"PC connected: {pc_name}"
                           + (" (session resumed)" if recovered else ""))
        self._notify_update()

    def _recover_session(self, client: ClientConnection) -> bool:
        """
        Re-attach a PC that reconnects mid-session. Restores the
        remaining time and re-arms the client UI.
        """
        session = db.get_open_session(client.pc_name)
        if not session:
            return False

        remaining = session.get("remaining_secs")
        if remaining is None:
            remaining = max(0, int(session["duration_mins"]) * 60)
        remaining = int(remaining)

        if remaining <= 0:
            self._settle(client, session, used_secs=int(session["duration_mins"]) * 60,
                         reason="time already used up", expired=True)
            return False

        if session["status"] == "suspended":
            db.resume_session(session["id"])

        client.apply_session(session, remaining_secs=remaining)
        user = client.session_user
        client.send(CMD_START_SESSION, user=user, duration_secs=remaining, resumed=True)
        if client.paused:
            client.send(CMD_PAUSE_SESSION)
        client.send(CMD_TIME_UPDATE, remaining=remaining)
        log.info("Resumed session %s on %s (%ss left)", session["id"], client.pc_name, remaining)
        self.on_session_event("recovered", {"pc_name": client.pc_name, "user": user,
                                            "remaining_secs": remaining,
                                            "session": session})
        return True

    # ── client events ────────────────────────────────────────

    def _on_session_ended(self, client: ClientConnection, data: dict):
        """
        The customer pressed "End session" on the client.
        Settle the booking fairly and LOCK the PC — this used to leave the
        machine unlocked and unbilled.
        """
        if not client.session_id:
            client.send(CMD_STOP_SESSION, reason="no session")
            return
        session = db.get_open_session(client.pc_name)
        if not session:
            client.clear_session()
            client.send(CMD_STOP_SESSION, reason="session already closed")
            self._notify_update()
            return

        duration = int(session["duration_mins"]) * 60
        used = max(0, min(duration, duration - client.remaining_secs))
        self._settle(client, session, used_secs=used, reason="ended by customer",
                     lock=True)

    def _on_member_login(self, client: ClientConnection, data: dict):
        """Self-service login from the lock screen: balance buys time."""
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        member = db.verify_member_login(username, password)
        if not member:
            client.send(CMD_LOGIN_RESULT, success=False,
                        reason="Wrong username or password.")
            return

        if client.session_id:
            client.send(CMD_LOGIN_RESULT, success=False,
                        reason="This PC already has a running session.")
            return

        rate = db.get_pc_rate(client.pc_name)
        balance = float(member["balance"] or 0)
        if rate <= 0:
            client.send(CMD_LOGIN_RESULT, success=False,
                        reason="No hourly rate configured for this PC.")
            return
        if balance <= 0:
            client.send(CMD_LOGIN_RESULT, success=False,
                        reason=f"Insufficient balance: {config.CURRENCY} {balance:.0f}")
            return

        duration_mins = int((balance / rate) * 60)
        if duration_mins < 1:
            client.send(CMD_LOGIN_RESULT, success=False,
                        reason=f"Balance too low for a session ({config.CURRENCY} {balance:.0f}).")
            return

        amount = round((duration_mins / 60.0) * rate, 2)
        session_id = db.start_session(
            pc_name=client.pc_name, member_id=member["id"],
            duration_mins=duration_mins, amount=amount,
            payment_type="balance", deduct_balance=True)

        session = db.get_open_session(client.pc_name) or {"id": session_id}
        client.apply_session(session, remaining_secs=duration_mins * 60,
                             user=member["name"])

        client.send(CMD_LOGIN_RESULT, success=True, member_name=member["name"],
                    duration_secs=client.remaining_secs, balance_used=amount,
                    balance_left=round(balance - amount, 2))
        client.send(CMD_START_SESSION, user=member["name"],
                    duration_secs=client.remaining_secs)

        self.on_status_msg(f"Member login: {member['name']} on {client.pc_name} "
                           f"({duration_mins} min)")
        self.on_session_event("started", {"pc_name": client.pc_name, "user": member["name"],
                                          "session": session, "amount": amount})
        self._notify_update()

    def _on_admin_unlock_request(self, client: ClientConnection, data: dict):
        """
        Password check for the client's corner unlock, verified HERE so
        client PCs never need a copy of the database.
        """
        password = (data or {}).get("password", "")
        ok = db.verify_admin_password(password)
        if ok:
            client.send(CMD_ADMIN_UNLOCK_RESULT, success=True)
            self.on_status_msg(f"Admin unlock used on {client.pc_name}")
            log.info("Admin unlock on %s", client.pc_name)
        else:
            client.send(CMD_ADMIN_UNLOCK_RESULT, success=False,
                        reason="Wrong admin password")
            log.warning("Failed admin unlock attempt from %s", client.pc_name or client.addr)
            self.on_status_msg(f"Wrong admin password from {client.pc_name or client.addr}")

    # ── settlement helpers ───────────────────────────────────

    def _settle(self, client: ClientConnection, session: dict, used_secs: int,
                reason: str, lock: bool = False, expired: bool = False,
                keep_prepaid: bool = False):
        """
        Close a session for a connected client: price it, refund balance
        members, tell the client what happened.
        """
        prepaid = float(session.get("amount_charged") or 0)
        if keep_prepaid:
            charge, refund = prepaid, 0.0
        else:
            charge = charge_for_used(session, used_secs)
            refund = round(max(0.0, prepaid - charge), 2)

        wallet_refund = (session.get("payment_type") == "balance"
                         and session.get("member_id") and refund > 0)
        result = db.settle_session(
            session["id"], actual_amount=charge,
            refund_amount=refund if refund > 0 else 0.0,
            refund_to_wallet=bool(wallet_refund),
            note=f"{reason}")

        member = db.get_member_by_id(session["member_id"]) if session.get("member_id") else None
        payload = {
            "session_id": session["id"], "pc_name": client.pc_name,
            "user": client.session_user, "started": session.get("start_time"),
            "ended": result.get("ended"), "booked_mins": session.get("duration_mins"),
            "used_secs": used_secs, "prepaid": prepaid, "charged": charge,
            "refund": refund, "payment_type": session.get("payment_type"),
            "balance_left": member["balance"] if member else None,
            "reason": reason,
        }

        client.clear_session()
        client.status = STATUS_FREE

        if expired:
            client.send(CMD_SESSION_EXPIRED)
            if self.settings_cache.get("auto_lock", True):
                client.status = STATUS_LOCKED
                client.send(CMD_LOCK)
        elif lock:
            client.send(CMD_STOP_SESSION, reason=reason)
            if self.settings_cache.get("auto_lock", True):
                client.status = STATUS_LOCKED
                client.send(CMD_LOCK)

        self.on_status_msg(
            f"Session ended on {client.pc_name} — charged "
            f"{config.CURRENCY} {charge:.0f}"
            + (f", refunded {config.CURRENCY} {refund:.0f}" if refund else ""))
        self.on_session_event("settled", payload)
        self._notify_update()
        return payload

    def _suspend_client_session(self, client: ClientConnection, reason: str):
        """PC vanished mid-session — keep the booking so it can resume."""
        if not client.session_id:
            return
        db.suspend_session(client.session_id, client.remaining_secs, client.paused)
        session = db.get_open_session(client.pc_name)
        log.info("Suspended session %s on %s (%s)", client.session_id,
                 client.pc_name, reason)
        self.on_session_event("suspended", {
            "pc_name": client.pc_name, "user": client.session_user,
            "remaining_secs": client.remaining_secs, "session": session,
            "reason": reason,
        })
        self.on_status_msg(f"PC offline mid-session: {client.pc_name} "
                           f"— {client.remaining_secs // 60} min held for reconnect")
        client.session_id = None
        client.suspended = True

    def _remove_client(self, client: ClientConnection, reason: str):
        if client.session_id:
            self._suspend_client_session(client, reason)
        with self._lock:
            if client.pc_name and self.clients.get(client.pc_name) is client:
                del self.clients[client.pc_name]
        if client.pc_name:
            self.on_status_msg(f"PC disconnected: {client.pc_name}")
        client.disconnect()
        self._notify_update()

    # ── timer loops ──────────────────────────────────────────

    def _timer_loop(self):
        """Drift-corrected 1-second tick. Server time is authoritative."""
        next_tick = time.monotonic() + 1.0
        while self._running:
            now = time.monotonic()
            wait = next_tick - now
            if wait > 0:
                time.sleep(wait)
            next_tick += 1.0
            try:
                self._tick()
            except Exception:                                  # noqa: BLE001
                log.exception("Timer tick failed")

    def _tick(self):
        with self._lock:
            clients = list(self.clients.values())

        changed = False
        for client in clients:
            if not client.session_id or client.paused:
                continue
            if client.remaining_secs > 0:
                client.remaining_secs -= 1
                changed = True

                if client.remaining_secs % 10 == 0:
                    client.send(CMD_TIME_UPDATE, remaining=client.remaining_secs)

                for threshold in self.warn_thresholds:
                    if (client.remaining_secs == threshold
                            and threshold not in client._warnings_sent):
                        client._warnings_sent.add(threshold)
                        minutes = max(1, threshold // 60)
                        client.send(CMD_LOW_TIME_WARNING,
                                    remaining=client.remaining_secs, minutes=minutes)
                        self.on_status_msg(f"⚠ {client.pc_name} — {minutes} min "
                                           f"remaining ({client.session_user})")
            else:
                session = db.get_open_session(client.pc_name)
                if session:
                    duration = int(session["duration_mins"]) * 60
                    self._settle(client, session, used_secs=duration,
                                 reason="time expired", expired=True)
                else:
                    client.clear_session()
                    client.send(CMD_SESSION_EXPIRED)
                changed = True

        if changed:
            self._notify_update()

    def _persist_loop(self):
        """Snapshot live countdowns so a crash costs at most ~10 seconds."""
        while self._running:
            time.sleep(LIVE_PERSIST_INTERVAL)
            try:
                with self._lock:
                    clients = list(self.clients.values())
                for client in clients:
                    if client.session_id:
                        db.update_session_live(client.session_id,
                                               client.remaining_secs, client.paused)
            except Exception:                                  # noqa: BLE001
                log.exception("Live snapshot failed")

    def _sweep_loop(self):
        """Settle suspended sessions whose PC never came back."""
        while self._running:
            time.sleep(SWEEP_INTERVAL)
            try:
                for item in db.sweep_stale_sessions():
                    self.on_status_msg(
                        f"Auto-settled {item['pc_name']} — PC did not reconnect")
                    self.on_session_event("settled", dict(item, reason="pc offline"))
                self._notify_update()
            except Exception:                                  # noqa: BLE001
                log.exception("Sweep failed")

    def _watchdog_loop(self):
        """Detect dead clients (cable pulled, PC powered off)."""
        while self._running:
            time.sleep(5)
            now = time.time()
            with self._lock:
                dead = [c for c in self.clients.values()
                        if now - c.last_heartbeat > HEARTBEAT_TIMEOUT]
            for client in dead:
                log.info("Heartbeat timeout for %s", client.pc_name)
                self._remove_client(client, "heartbeat timeout")

    # ── admin API (called from the UI) ───────────────────────

    def start_session(self, pc_name: str, user: str, duration_mins: int,
                      amount: float, member_id=None, payment_type="cash",
                      discount_pct: float = 0.0,
                      discount_amount: float = 0.0) -> dict:
        client = self._get(pc_name)
        if not client:
            return {"ok": False, "error": "PC is not connected."}
        if client.session_id:
            return {"ok": False, "error": f"{pc_name} already has a running session."}
        if db.get_open_session(pc_name):
            return {"ok": False,
                    "error": f"A stale session still exists for {pc_name}. "
                             f"Use “Force close” from the PC menu first."}
        if duration_mins <= 0:
            return {"ok": False, "error": "Duration must be at least a minute."}

        deduct = bool(member_id) and payment_type == "balance"
        if deduct:
            member = db.get_member_by_id(member_id)
            if not member:
                return {"ok": False, "error": "Member not found."}
            if float(member["balance"] or 0) < amount:
                return {"ok": False,
                        "error": f"Insufficient balance: {config.CURRENCY} "
                                 f"{member['balance']:.0f} available, "
                                 f"{config.CURRENCY} {amount:.0f} needed."}

        session_id = db.start_session(
            pc_name, member_id=member_id,
            guest_name=user if not member_id else None,
            duration_mins=duration_mins, amount=amount,
            payment_type=payment_type, discount_pct=discount_pct,
            discount_amount=discount_amount, deduct_balance=deduct)

        session = db.get_open_session(pc_name) or {"id": session_id}
        client.apply_session(session, remaining_secs=duration_mins * 60, user=user)
        ok = client.send(CMD_START_SESSION, user=user,
                         duration_secs=duration_mins * 60)
        if not ok:
            db.settle_session(session_id, actual_amount=0.0,
                              refund_amount=amount if deduct else 0.0,
                              refund_to_wallet=deduct,
                              note="PC dropped before the session started")
            client.clear_session()
            self._notify_update()
            return {"ok": False, "error": "PC dropped the connection — nothing charged."}

        self.on_session_event("started", {"pc_name": pc_name, "user": user,
                                          "session": session, "amount": amount})
        self._notify_update()
        return {"ok": True, "session_id": session_id, "amount": amount}

    def stop_session(self, pc_name: str, actual_amount: float = None,
                     payment_type: str = None) -> dict:
        client = self._get(pc_name)
        session = db.get_open_session(pc_name)
        if not session:
            if client:
                client.clear_session()
                client.status = STATUS_FREE
            return {"ok": False, "error": "No open session on this PC."}

        if payment_type:
            session["payment_type"] = payment_type

        duration = int(session["duration_mins"]) * 60
        if client and client.session_id:
            used = max(0, min(duration, duration - client.remaining_secs))
        else:
            used = db.get_used_seconds(session)

        prepaid = float(session.get("amount_charged") or 0)
        charge = charge_for_used(session, used) if actual_amount is None \
            else round(max(0.0, min(actual_amount, prepaid)), 2)
        refund = round(max(0.0, prepaid - charge), 2)
        wallet_refund = (session.get("payment_type") == "balance"
                         and session.get("member_id") and refund > 0)

        result = db.settle_session(
            session["id"], actual_amount=charge,
            refund_amount=refund if refund > 0 else 0.0,
            refund_to_wallet=bool(wallet_refund),
            note="stopped by admin")

        if client:
            client.clear_session()
            client.status = STATUS_FREE
            if self.settings_cache.get("auto_lock", True):
                client.status = STATUS_LOCKED
                client.send(CMD_STOP_SESSION)
                client.send(CMD_LOCK)
            else:
                client.send(CMD_STOP_SESSION)

        member = db.get_member_by_id(session["member_id"]) if session.get("member_id") else None
        payload = {
            "session_id": session["id"], "pc_name": pc_name,
            "user": _session_user_name(session), "started": session.get("start_time"),
            "ended": result.get("ended"), "booked_mins": session.get("duration_mins"),
            "used_secs": used, "prepaid": prepaid, "charged": charge,
            "refund": refund, "payment_type": session.get("payment_type"),
            "balance_left": member["balance"] if member else None,
            "reason": "stopped by admin",
        }
        self.on_status_msg(
            f"Session stopped on {pc_name} — charged {config.CURRENCY} {charge:.0f}"
            + (f" (cash refund due: {config.CURRENCY} {refund:.0f})"
               if refund > 0 and not wallet_refund else "")
            + (f", {config.CURRENCY} {refund:.0f} returned to balance"
               if wallet_refund else ""))
        self.on_session_event("settled", payload)
        self._notify_update()
        return {"ok": True, **payload}

    def add_time(self, pc_name: str, extra_mins: int, amount: float = 0.0,
                 payment_type: str = "cash", member_id=None,
                 deduct_balance=None) -> dict:
        """Add paid time to a running session and record the money."""
        client = self._get(pc_name)
        session = db.get_open_session(pc_name)
        if not session:
            return {"ok": False, "error": "No running session on this PC."}
        if extra_mins <= 0:
            return {"ok": False, "error": "Enter at least one minute."}

        member_id = member_id or session.get("member_id")
        if deduct_balance is None:
            deduct_balance = bool(member_id) and payment_type == "balance"

        if deduct_balance and amount > 0:
            member = db.get_member_by_id(member_id)
            if not member:
                return {"ok": False, "error": "Member not found."}
            if float(member["balance"] or 0) < amount:
                return {"ok": False,
                        "error": f"Insufficient balance: {config.CURRENCY} "
                                 f"{member['balance']:.0f} available."}

        updated = db.extend_session(session["id"], extra_mins, amount,
                                    member_id=member_id, payment_type=payment_type,
                                    deduct_balance=bool(deduct_balance))
        if not updated:
            return {"ok": False, "error": "Could not update the session."}

        if client:
            client.remaining_secs += extra_mins * 60
            client._warnings_sent = {t for t in client._warnings_sent
                                     if t < client.remaining_secs}
            client.send(CMD_TIME_UPDATE, remaining=client.remaining_secs)
        else:
            db.update_session_live(session["id"],
                                   int(updated.get("remaining_secs") or 0),
                                   bool(updated.get("paused")))

        self.on_session_event("add_time", {"pc_name": pc_name, "minutes": extra_mins,
                                           "amount": amount, "session": updated})
        self.on_status_msg(f"+{extra_mins} min on {pc_name}"
                           + (f" ({config.CURRENCY} {amount:.0f})" if amount else ""))
        self._notify_update()
        return {"ok": True, "session": updated, "amount": amount}

    def lock_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.status = STATUS_LOCKED
        ok = client.send(CMD_LOCK)
        self._notify_update()
        return ok

    def unlock_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        if not client:
            return False
        client.status = STATUS_FREE
        ok = client.send(CMD_UNLOCK)
        self._notify_update()
        return ok

    def send_message(self, pc_name: str, message: str) -> bool:
        client = self._get(pc_name)
        return client.send(CMD_MESSAGE, text=message) if client else False

    def send_message_all(self, message: str):
        for client in self._snapshot():
            client.send(CMD_MESSAGE, text=message)

    def restart_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        return client.send(CMD_RESTART) if client else False

    def restart_all(self):
        for client in self._snapshot():
            client.send(CMD_RESTART)

    def shutdown_pc(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        return client.send(CMD_SHUTDOWN) if client else False

    def shutdown_all(self):
        for client in self._snapshot():
            client.send(CMD_SHUTDOWN)

    def lock_all(self):
        for client in self._snapshot():
            client.status = STATUS_LOCKED
            client.send(CMD_LOCK)
        self._notify_update()

    def pause_session(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        session = db.get_open_session(pc_name)
        if not client:
            return False
        client.paused = True
        client.status = STATUS_PAUSED
        if session:
            db.update_session_live(session["id"], client.remaining_secs, True)
        ok = client.send(CMD_PAUSE_SESSION)
        self._notify_update()
        return ok

    def resume_session(self, pc_name: str) -> bool:
        client = self._get(pc_name)
        session = db.get_open_session(pc_name)
        if not client:
            return False
        client.paused = False
        client.status = STATUS_ACTIVE if client.session_id else STATUS_FREE
        if session:
            db.update_session_live(session["id"], client.remaining_secs, False)
        ok = client.send(CMD_RESUME_SESSION)
        self._notify_update()
        return ok

    def force_close_session(self, pc_name: str, keep_prepaid: bool = True) -> dict:
        """Close a session row whose PC is not connected (stale row)."""
        session = db.get_open_session(pc_name)
        if not session:
            return {"ok": False, "error": "No open session on this PC."}
        client = self._get(pc_name)
        if client and client.session_id:
            return self.stop_session(pc_name)

        used = db.get_used_seconds(session)
        if keep_prepaid:
            charge, refund = float(session["amount_charged"] or 0), 0.0
        else:
            charge = charge_for_used(session, used)
            refund = round(float(session["amount_charged"] or 0) - charge, 2)
        wallet = (session.get("payment_type") == "balance"
                  and session.get("member_id") and refund > 0)
        db.settle_session(session["id"], actual_amount=charge,
                          refund_amount=refund if refund > 0 else 0.0,
                          refund_to_wallet=bool(wallet),
                          note="force-closed by admin")
        self.on_status_msg(f"Force-closed session on {pc_name}")
        self._notify_update()
        return {"ok": True, "charged": charge, "refund": refund}

    def close_all_sessions(self, reason: str = "closed by admin") -> int:
        count = db.force_close_open_sessions(reason)
        with self._lock:
            for client in self.clients.values():
                if client.session_id:
                    client.clear_session()
                    client.status = STATUS_FREE
                    client.send(CMD_STOP_SESSION)
        self.on_status_msg(f"Closed {count} open session(s)")
        self._notify_update()
        return count

    # ── helpers ──────────────────────────────────────────────

    def _get(self, pc_name: str):
        with self._lock:
            return self.clients.get(pc_name)

    def _snapshot(self) -> list:
        with self._lock:
            return list(self.clients.values())

    def _notify_update(self):
        with self._lock:
            snapshot = dict(self.clients)
        self.on_pc_update(snapshot)

    def get_clients_snapshot(self) -> dict:
        with self._lock:
            return dict(self.clients)

    @property
    def active_count(self) -> int:
        return sum(1 for c in self._snapshot() if c.status == STATUS_ACTIVE)

    @property
    def total_count(self) -> int:
        return len(self._snapshot())


# Re-export for callers that used to import it from here
__all__ = ["AZCafeServer", "ClientConnection", "implied_rate", "charge_for_used",
           "HEARTBEAT_TIMEOUT", "paths"]
