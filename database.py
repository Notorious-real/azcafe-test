# ============================================================
#  AZ Cafe - Database Layer
#  SQLite storage for members, sessions, billing, settings.
#
#  Money rules (single source of truth — keep in sync with docs):
#    * Time is prepaid. sessions.amount_charged holds the prepaid
#      amount while the session is open.
#    * On settle, amount_charged becomes the amount actually kept,
#      priced from the rate implied by the prepaid booking.
#    * Balance-paid sessions are refunded to the member when the
#      customer leaves early. Cash sessions are refunded by hand
#      (the ledger records it, the software moves no money).
#    * Every money movement writes a row in `transactions`.
# ============================================================

import hashlib
import hmac
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta

import paths

DB_PATH = paths.data_path("azcafe.db")

WAL_ENABLED = False
_SETTLE_GRACE_MINS = 10


# ── Connections ─────────────────────────────────────────────

def get_connection():
    """Open a connection with sane concurrency settings."""
    global WAL_ENABLED
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    if not WAL_ENABLED:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            WAL_ENABLED = True
        except sqlite3.Error:
            pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    """Local timestamp, same format everywhere (ISO seconds)."""
    return datetime.now().isoformat(timespec="seconds")


def _ensure_column(cur, table: str, column: str, ddl: str):
    """Add a column to an existing database (migration)."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except sqlite3.OperationalError:
        pass


# ── Schema ──────────────────────────────────────────────────

def init_db():
    """Create every table and apply migrations. Safe on each startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            balance       REAL    DEFAULT 0.0,
            total_spent   REAL    DEFAULT 0.0,
            phone         TEXT,
            created_at    TEXT    DEFAULT (datetime('now','localtime')),
            last_seen     TEXT,
            notes         TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pcs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_name        TEXT    UNIQUE NOT NULL,
            display_name   TEXT,
            grid_x         INTEGER DEFAULT 0,
            grid_y         INTEGER DEFAULT 0,
            group_name     TEXT    DEFAULT 'Default',
            pricing_plan_id INTEGER REFERENCES pricing_plans(id),
            added_at       TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_name        TEXT    NOT NULL,
            member_id      INTEGER,
            guest_name     TEXT,
            start_time     TEXT    NOT NULL,
            end_time       TEXT,
            duration_mins  INTEGER DEFAULT 0,
            amount_charged REAL    DEFAULT 0.0,
            payment_type   TEXT    DEFAULT 'cash',
            status         TEXT    DEFAULT 'active',
            discount_pct   REAL    DEFAULT 0.0,
            discount_amount REAL   DEFAULT 0.0,
            remaining_secs INTEGER,
            paused         INTEGER DEFAULT 0,
            suspended_at   TEXT,
            settled_note   TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pc_groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pricing_plans (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            rate_per_hour REAL    NOT NULL,
            min_minutes   INTEGER DEFAULT 0,
            is_default    INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS time_packages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            duration_mins INTEGER NOT NULL,
            price         REAL    NOT NULL,
            description   TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            member_id  INTEGER,
            type       TEXT,
            amount     REAL,
            timestamp  TEXT DEFAULT (datetime('now','localtime')),
            notes      TEXT
        )
    """)

    # ── Migrations for databases created by older versions ──
    _ensure_column(cur, "pcs",      "pricing_plan_id", "INTEGER REFERENCES pricing_plans(id)")
    _ensure_column(cur, "sessions", "discount_pct",   "REAL DEFAULT 0.0")
    _ensure_column(cur, "sessions", "discount_amount", "REAL DEFAULT 0.0")
    _ensure_column(cur, "sessions", "remaining_secs", "INTEGER")
    _ensure_column(cur, "sessions", "paused",         "INTEGER DEFAULT 0")
    _ensure_column(cur, "sessions", "suspended_at",   "TEXT")
    _ensure_column(cur, "sessions", "settled_note",   "TEXT")
    _ensure_column(cur, "members",  "phone",          "TEXT")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_pc     ON sessions(pc_name, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start  ON sessions(start_time)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_timestamp    ON transactions(timestamp)")

    _seed_defaults(cur)
    conn.commit()
    conn.close()


def _seed_defaults(cur):
    """Insert default records if the tables are empty."""

    cur.execute("SELECT COUNT(*) FROM pricing_plans")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO pricing_plans (name, rate_per_hour, min_minutes, is_default)
            VALUES (?, ?, ?, ?)
        """, ("Standard", 60.0, 0, 1))   # Rs 60/hour

    cur.execute("SELECT COUNT(*) FROM time_packages")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO time_packages (name, duration_mins, price, description)
            VALUES (?, ?, ?, ?)
        """, [
            ("1 Hour Bundle",    60,  60.0,  "Standard 1 Hour"),
            ("2 Hour Pass",      120, 110.0, "Save Rs 10"),
            ("3 Hour Gamer Pass", 180, 150.0, "Save Rs 30"),
            ("5 Hour Pro Pass",  300, 240.0, "Save Rs 60 (Best Value)"),
        ])

    defaults = {
        "admin_password":        "admin123",   # hashed on first login / change
        "shop_name":             "AZ Cafe",
        "low_time_warning":      "5",          # minutes before the end to warn
        "auto_lock":             "1",          # lock PCs when a session ends
        "receipt_printer":       "",           # "" = system default printer
        "auto_print_receipt":    "1",
        "sound_enabled":         "1",
        "kiosk_mode":            "1",          # block Windows keys on client PCs
        "lock_task_manager":     "0",
        "session_resume_grace":  str(_SETTLE_GRACE_MINS),
        "import_default_password": "123456",
        "import_default_balance":  "0",
        "currency":              "Rs",
    }
    for key, value in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value))

    cur.execute("INSERT OR IGNORE INTO pc_groups (name) VALUES ('Default')")


# ── Passwords ───────────────────────────────────────────────

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    """Salted scrypt hash: scrypt$n$r$p$salt$hash (hex)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     salt.hex(), digest.hex()])


def verify_password(password: str, stored: str) -> bool:
    """
    Verify against a scrypt hash. Legacy plaintext values (pre-2.0
    databases shipped admin123 as-is) are accepted once so the app can
    upgrade them in place.
    """
    if not stored:
        return False
    if not stored.startswith("scrypt$"):
        return hmac.compare_digest(stored, password)
    try:
        _, n, r, p, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode("utf-8"),
                                salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def is_hashed(value: str) -> bool:
    return bool(value) and value.startswith("scrypt$")


def get_setting(key: str, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                 (key, str(value)))
    conn.commit()
    conn.close()


def get_int_setting(key: str, default: int = 0) -> int:
    try:
        return int(float(get_setting(key, default)))
    except (TypeError, ValueError):
        return default


def get_bool_setting(key: str, default: bool = False) -> bool:
    value = get_setting(key, "1" if default else "0")
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def verify_admin_password(password: str) -> bool:
    """
    Check the admin password. A legacy plaintext or default value is
    upgraded to a salted hash on the first successful login.
    """
    stored = get_setting("admin_password", "")
    if verify_password(password, stored):
        if not is_hashed(stored):
            set_setting("admin_password", hash_password(password))
        return True
    return False


def set_admin_password(new_password: str):
    set_setting("admin_password", hash_password(new_password))


# ── Pricing ─────────────────────────────────────────────────

def get_default_rate() -> float:
    conn = get_connection()
    row = conn.execute(
        "SELECT rate_per_hour FROM pricing_plans WHERE is_default=1 LIMIT 1"
    ).fetchone()
    conn.close()
    return float(row["rate_per_hour"]) if row else 60.0


def get_pc_rate(pc_name: str) -> float:
    conn = get_connection()
    row = conn.execute("""
        SELECT p.rate_per_hour
        FROM pcs pc
        JOIN pricing_plans p ON pc.pricing_plan_id = p.id
        WHERE pc.pc_name = ?
    """, (pc_name,)).fetchone()
    conn.close()
    return float(row["rate_per_hour"]) if row else get_default_rate()


def get_all_pricing_plans() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pricing_plans ORDER BY is_default DESC, rate_per_hour"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_pricing_plan(name: str, rate_per_hour: float, min_minutes: int = 0) -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO pricing_plans (name, rate_per_hour, min_minutes, is_default)
        VALUES (?, ?, ?, 0)
    """, (name, rate_per_hour, min_minutes))
    plan_id = cur.lastrowid
    conn.commit()
    conn.close()
    return plan_id


def update_pricing_plan(plan_id: int, name: str, rate_per_hour: float,
                        min_minutes: int = 0):
    conn = get_connection()
    conn.execute("""
        UPDATE pricing_plans SET name=?, rate_per_hour=?, min_minutes=?
        WHERE id=?
    """, (name, rate_per_hour, min_minutes, plan_id))
    conn.commit()
    conn.close()


def delete_pricing_plan(plan_id: int):
    conn = get_connection()
    conn.execute("UPDATE pricing_plans SET is_default=0 WHERE id=?", (plan_id,))
    conn.execute("UPDATE pcs SET pricing_plan_id=NULL WHERE pricing_plan_id=?", (plan_id,))
    conn.execute("DELETE FROM pricing_plans WHERE id=?", (plan_id,))
    remaining = conn.execute("SELECT COUNT(*) c FROM pricing_plans").fetchone()["c"]
    if remaining and not conn.execute(
            "SELECT 1 FROM pricing_plans WHERE is_default=1").fetchone():
        conn.execute("UPDATE pricing_plans SET is_default=1 WHERE id=(SELECT MIN(id) FROM pricing_plans)")
    conn.commit()
    conn.close()


def set_default_plan(plan_id: int):
    conn = get_connection()
    conn.execute("UPDATE pricing_plans SET is_default=0")
    conn.execute("UPDATE pricing_plans SET is_default=1 WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()


# ── Time packages ───────────────────────────────────────────

def get_all_time_packages() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM time_packages ORDER BY duration_mins").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_time_package(name: str, duration_mins: int, price: float,
                        description: str = "") -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO time_packages (name, duration_mins, price, description)
        VALUES (?, ?, ?, ?)
    """, (name, duration_mins, price, description))
    conn.commit()
    pkg_id = cur.lastrowid
    conn.close()
    return pkg_id


def update_time_package(pkg_id: int, name: str, duration_mins: int, price: float,
                        description: str = ""):
    conn = get_connection()
    conn.execute("""
        UPDATE time_packages SET name=?, duration_mins=?, price=?, description=?
        WHERE id=?
    """, (name, duration_mins, price, description, pkg_id))
    conn.commit()
    conn.close()


def delete_time_package(pkg_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM time_packages WHERE id=?", (pkg_id,))
    conn.commit()
    conn.close()


# ── PCs, positions, groups ──────────────────────────────────

def save_pc(pc_name: str, grid_x=0, grid_y=0):
    conn = get_connection()
    conn.execute("""
        INSERT OR IGNORE INTO pcs (pc_name, display_name, grid_x, grid_y)
        VALUES (?, ?, ?, ?)
    """, (pc_name, pc_name, grid_x, grid_y))
    conn.commit()
    conn.close()


def update_pc_position(pc_name: str, grid_x: int, grid_y: int):
    conn = get_connection()
    conn.execute("UPDATE pcs SET grid_x=?, grid_y=? WHERE pc_name=?",
                 (grid_x, grid_y, pc_name))
    conn.commit()
    conn.close()


def update_pc_display_name(pc_name: str, display_name: str):
    conn = get_connection()
    conn.execute("UPDATE pcs SET display_name=? WHERE pc_name=?",
                 (display_name, pc_name))
    conn.commit()
    conn.close()


def create_pc_group(group_name: str) -> bool:
    """Create an (initially empty) group."""
    name = (group_name or "").strip()
    if not name:
        return False
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO pc_groups (name) VALUES (?)", (name,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def update_pc_group(pc_name: str, group_name: str):
    name = (group_name or "Default").strip() or "Default"
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO pc_groups (name) VALUES (?)", (name,))
    conn.execute("UPDATE pcs SET group_name=? WHERE pc_name=?", (name, pc_name))
    conn.commit()
    conn.close()


def get_group_counts() -> dict:
    conn = get_connection()
    rows = conn.execute("""
        SELECT COALESCE(NULLIF(group_name,''),'Default') AS g, COUNT(*) AS n
        FROM pcs GROUP BY g
    """).fetchall()
    conn.close()
    return {r["g"]: r["n"] for r in rows}


def rename_pc_group(old_name: str, new_name: str) -> int:
    """Rename a group; returns how many PCs moved."""
    new_name = (new_name or "").strip() or "Default"
    conn = get_connection()
    cur = conn.execute("UPDATE pcs SET group_name=? WHERE group_name=?",
                       (new_name, old_name))
    conn.execute("INSERT OR IGNORE INTO pc_groups (name) VALUES (?)", (new_name,))
    conn.execute("DELETE FROM pc_groups WHERE name=?", (old_name,))
    conn.commit()
    moved = cur.rowcount
    conn.close()
    return moved


def delete_pc_group(group_name: str) -> int:
    """Delete a group — its PCs fall back to 'Default'."""
    if group_name == "Default":
        return 0
    conn = get_connection()
    cur = conn.execute("UPDATE pcs SET group_name='Default' WHERE group_name=?",
                       (group_name,))
    conn.execute("DELETE FROM pc_groups WHERE name=?", (group_name,))
    conn.commit()
    moved = cur.rowcount
    conn.close()
    return moved


def get_all_pc_groups() -> list:
    """Every group: the ones created in Settings plus any seen on PCs."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT name AS g FROM pc_groups
        UNION
        SELECT DISTINCT COALESCE(NULLIF(group_name,''),'Default') AS g FROM pcs
        ORDER BY g
    """).fetchall()
    conn.close()
    groups = [r["g"] for r in rows]
    return groups or ["Default"]


def get_all_pcs() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM pcs ORDER BY grid_y, grid_x, pc_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pc_by_name(pc_name: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM pcs WHERE pc_name=?", (pc_name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_pc_pricing_plan(pc_name: str, plan_id):
    conn = get_connection()
    conn.execute("UPDATE pcs SET pricing_plan_id=? WHERE pc_name=?",
                 (plan_id, pc_name))
    conn.commit()
    conn.close()


# ── Sessions ────────────────────────────────────────────────

def _implied_rate(amount: float, duration_mins: int) -> float:
    """Rs/hour implied by a booking (falls back to the default plan)."""
    if duration_mins > 0 and amount > 0:
        return (amount / duration_mins) * 60.0
    return get_default_rate()


def start_session(pc_name: str, member_id=None, guest_name=None,
                  duration_mins=60, amount=0.0, payment_type="cash",
                  discount_pct=0.0, discount_amount=0.0,
                  deduct_balance=False) -> int:
    """
    Open a prepaid session and record the money in the ledger.
    When deduct_balance is set the prepaid amount also leaves the
    member's wallet, atomically.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions
            (pc_name, member_id, guest_name, start_time, duration_mins,
             amount_charged, payment_type, status, discount_pct, discount_amount,
             remaining_secs, paused)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 0)
    """, (pc_name, member_id, guest_name, _now(), duration_mins,
          amount, payment_type, discount_pct, discount_amount,
          int(duration_mins) * 60))
    session_id = cur.lastrowid

    if deduct_balance and member_id:
        cur.execute("""
            UPDATE members
            SET balance = balance - ?, total_spent = total_spent + ?,
                last_seen = datetime('now','localtime')
            WHERE id = ?
        """, (amount, amount, member_id))

    cur.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, 'session_prepaid', ?, ?)
    """, (session_id, member_id, amount,
          f"{payment_type} prepaid · {duration_mins} min on {pc_name}"))
    conn.commit()
    conn.close()
    return session_id


def settle_session(session_id: int, actual_amount: float = None,
                   refund_amount: float = 0.0, refund_to_wallet: bool = False,
                   note: str = "") -> dict:
    """
    Close a session: set the final charge, return unused time to a
    member's wallet when the booking was paid from balance, and write
    the ledger rows. Returns a summary dict.

    refund_to_wallet=False still records a cash refund in the ledger so
    the operator can see that money left the drawer.
    """
    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return {}

    prepaid = float(row["amount_charged"] or 0.0)
    final = prepaid if actual_amount is None else round(max(0.0, actual_amount), 2)
    refund = round(max(0.0, min(refund_amount, prepaid)), 2)
    ended = _now()

    cur.execute("""
        UPDATE sessions
        SET end_time=?, status='completed', amount_charged=?,
            remaining_secs=0, paused=0, suspended_at=NULL, settled_note=?
        WHERE id=?
    """, (ended, final, note, session_id))

    if refund > 0:
        if refund_to_wallet and row["member_id"]:
            cur.execute("""
                UPDATE members
                SET balance = balance + ?, total_spent = MAX(0, total_spent - ?)
                WHERE id = ?
            """, (refund, refund, row["member_id"]))
            cur.execute("""
                INSERT INTO transactions (session_id, member_id, type, amount, notes)
                VALUES (?, ?, 'session_refund', ?, ?)
            """, (session_id, row["member_id"], refund,
                  note or f"Unused time returned to balance on {row['pc_name']}"))
        else:
            cur.execute("""
                INSERT INTO transactions (session_id, member_id, type, amount, notes)
                VALUES (?, ?, 'cash_refund', ?, ?)
            """, (session_id, row["member_id"], -refund,
                  note or f"Cash refund due on {row['pc_name']}"))

    cur.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, 'session_charge', ?, ?)
    """, (session_id, row["member_id"], final,
          note or f"Session settled on {row['pc_name']}"))

    conn.commit()
    conn.close()
    return {"session_id": session_id, "prepaid": prepaid, "charged": final,
            "refund": refund, "ended": ended}


def end_session(session_id: int, actual_amount: float = None, note: str = ""):
    """Backwards-compatible wrapper around settle_session (no refund)."""
    return settle_session(session_id, actual_amount=actual_amount, note=note)


def _settle_open_row(session: dict, note: str) -> dict:
    """
    Fair settlement for a session whose PC never came back.

    Balance members get their unused time returned to the wallet; cash
    customers keep the prepaid amount with the café (standard prepaid
    policy), so the ledger stays equal to the cash in the drawer.
    """
    prepaid = float(session["amount_charged"] or 0)
    used = get_used_seconds(session)
    if session.get("payment_type") == "balance" and session.get("member_id"):
        rate = _implied_rate(prepaid, int(session["duration_mins"] or 0))
        charge = min(round((used / 3600.0) * rate, 2), prepaid)
        refund = round(prepaid - charge, 2)
        return settle_session(session["id"], actual_amount=charge,
                              refund_amount=refund, refund_to_wallet=True, note=note)
    return settle_session(session["id"], actual_amount=prepaid,
                          refund_amount=0.0, note=note)


def extend_session(session_id: int, extra_mins: int, extra_amount: float = 0.0,
                   member_id=None, payment_type: str = "cash",
                   deduct_balance: bool = False) -> dict:
    """Add paid time to an open session and log the money."""
    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return {}

    cur.execute("""
        UPDATE sessions
        SET duration_mins   = duration_mins + ?,
            amount_charged  = amount_charged + ?,
            remaining_secs  = COALESCE(remaining_secs, duration_mins*60) + ?
        WHERE id = ?
    """, (extra_mins, extra_amount, extra_mins * 60, session_id))

    if deduct_balance and (member_id or row["member_id"]) and extra_amount:
        mid = member_id or row["member_id"]
        cur.execute("""
            UPDATE members
            SET balance = balance - ?, total_spent = total_spent + ?,
                last_seen = datetime('now','localtime')
            WHERE id = ?
        """, (extra_amount, extra_amount, mid))

    cur.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, 'time_purchase', ?, ?)
    """, (session_id, member_id or row["member_id"], extra_amount,
          f"+{extra_mins} min ({payment_type}) on {row['pc_name']}"))
    conn.commit()

    updated = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(updated) if updated else {}


def update_session_live(session_id: int, remaining_secs: int, paused: bool):
    """Persist the live countdown so a reconnect/crash cannot lose it."""
    conn = get_connection()
    conn.execute("""
        UPDATE sessions SET remaining_secs=?, paused=? WHERE id=?
    """, (int(remaining_secs), 1 if paused else 0, session_id))
    conn.commit()
    conn.close()


def suspend_session(session_id: int, remaining_secs: int, paused: bool = False):
    """Client vanished mid-session — keep the booking recoverable."""
    conn = get_connection()
    conn.execute("""
        UPDATE sessions
        SET status='suspended', remaining_secs=?, paused=?, suspended_at=?
        WHERE id=?
    """, (int(remaining_secs), 1 if paused else 0, _now(), session_id))
    conn.commit()
    conn.close()


def resume_session(session_id: int):
    conn = get_connection()
    conn.execute("""
        UPDATE sessions SET status='active', suspended_at=NULL WHERE id=?
    """, (session_id,))
    conn.commit()
    conn.close()


def get_open_session(pc_name: str):
    """The open (active or suspended) session for a PC, newest first."""
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM sessions
        WHERE pc_name = ? AND status IN ('active','suspended')
        ORDER BY id DESC LIMIT 1
    """, (pc_name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_session(pc_name: str):
    """Open session regardless of state (kept for existing callers)."""
    return get_open_session(pc_name)


def get_used_seconds(session: dict) -> int:
    """Seconds already used, from the live snapshot when available."""
    duration = int(session.get("duration_mins") or 0) * 60
    remaining = session.get("remaining_secs")
    if remaining is None:
        try:
            started = datetime.fromisoformat(session["start_time"])
            remaining = max(0, int(duration - (datetime.now() - started).total_seconds()))
        except (ValueError, KeyError, TypeError):
            remaining = duration
    return max(0, min(duration, duration - int(remaining)))


def get_open_sessions_all() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM sessions WHERE status IN ('active','suspended')
        ORDER BY start_time
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def hold_sessions_across_restart() -> int:
    """
    A server restart must not cost a customer their paid time: mark the
    rows left behind as suspended so a reconnecting PC can resume them
    (the grace timer now runs from this moment).
    """
    conn = get_connection()
    cur = conn.execute("""
        UPDATE sessions
        SET status='suspended', suspended_at=?, settled_note='held across restart'
        WHERE status='active'
    """, (_now(),))
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def sweep_stale_sessions(grace_mins: int = None) -> list:
    """
    Settle suspended sessions whose PC never came back after the grace
    window (a powered-off PC, or one that left the café mid-session).
    """
    if grace_mins is None:
        grace_mins = get_int_setting("session_resume_grace", _SETTLE_GRACE_MINS)
    cutoff = datetime.now() - timedelta(minutes=grace_mins)

    settled = []
    for session in get_open_sessions_all():
        if session["status"] != "suspended":
            continue                                   # active rows have a live client
        suspended_at = session.get("suspended_at")
        if suspended_at:
            try:
                if datetime.fromisoformat(suspended_at) > cutoff:
                    continue                           # still inside the grace window
            except ValueError:
                pass
        result = _settle_open_row(session, "PC did not reconnect — auto-settled")
        settled.append({"pc_name": session["pc_name"], "session": result})
    return settled


def force_close_open_sessions(reason: str = "closed by admin") -> int:
    """Close every open session (maintenance button / shutdown)."""
    count = 0
    for session in get_open_sessions_all():
        _settle_open_row(session, reason)
        count += 1
    return count


# ── Reporting ───────────────────────────────────────────────

def get_today_revenue() -> float:
    """Revenue = settled sessions only (single canonical definition)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(amount_charged), 0) AS total
        FROM sessions
        WHERE date(start_time)=date('now','localtime') AND status='completed'
    """).fetchone()
    conn.close()
    return float(row["total"] or 0.0)


def get_today_open_amount() -> float:
    """Prepaid money currently sitting in running sessions."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(amount_charged), 0) AS total
        FROM sessions
        WHERE status IN ('active','suspended')
    """).fetchone()
    conn.close()
    return float(row["total"] or 0.0)


def get_today_sessions() -> int:
    conn = get_connection()
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM sessions
        WHERE date(start_time)=date('now','localtime') AND status='completed'
    """).fetchone()
    conn.close()
    return int(row["cnt"])


def get_sessions_by_date(date_str: str, statuses=None) -> list:
    conn = get_connection()
    if statuses:
        marks = ",".join("?" for _ in statuses)
        rows = conn.execute(f"""
            SELECT * FROM sessions WHERE date(start_time)=? AND status IN ({marks})
            ORDER BY start_time DESC
        """, (date_str, *statuses)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM sessions WHERE date(start_time)=?
            ORDER BY start_time DESC
        """, (date_str,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_day_totals(date_str: str) -> dict:
    """Everything a day-close report needs, from one query."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status='completed' THEN amount_charged END), 0) AS revenue,
            COALESCE(SUM(CASE WHEN status IN ('active','suspended') THEN amount_charged END), 0) AS open_amount,
            COUNT(*) AS total_sessions,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_sessions,
            SUM(CASE WHEN status IN ('active','suspended') THEN 1 ELSE 0 END) AS open_sessions,
            COALESCE(SUM(CASE WHEN status='completed' THEN duration_mins ELSE 0 END), 0) AS minutes_sold
        FROM sessions WHERE date(start_time)=?
    """, (date_str,)).fetchone()
    conn.close()
    data = dict(row)
    total = data["completed_sessions"] or 0
    data["avg_per_session"] = round((data["revenue"] or 0) / total, 2) if total else 0.0
    return data


def get_per_pc_stats() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT pc_name,
               COUNT(*) AS total_sessions,
               COALESCE(SUM(duration_mins), 0) AS total_mins,
               COALESCE(SUM(amount_charged), 0) AS total_revenue,
               MAX(start_time) AS last_used
        FROM sessions WHERE status='completed'
        GROUP BY pc_name ORDER BY total_revenue DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_members(limit: int = 20) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT m.id, m.name, m.username, m.balance, m.total_spent,
               COUNT(s.id) AS session_count
        FROM members m
        LEFT JOIN sessions s ON s.member_id = m.id AND s.status='completed'
        GROUP BY m.id
        ORDER BY m.total_spent DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_revenue_range(start_date: str, end_date: str) -> float:
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(SUM(amount_charged), 0) AS total
        FROM sessions
        WHERE date(start_time) BETWEEN ? AND ? AND status='completed'
    """, (start_date, end_date)).fetchone()
    conn.close()
    return float(row["total"] or 0.0)


def get_daily_revenue_range(start_date: str, end_date: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT date(start_time) AS day, COALESCE(SUM(amount_charged), 0) AS revenue,
               COUNT(*) AS sessions
        FROM sessions
        WHERE date(start_time) BETWEEN ? AND ? AND status='completed'
        GROUP BY day ORDER BY day
    """, (start_date, end_date)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_revenue_breakdown(months_count: int = 6) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', start_time) AS month,
               COALESCE(SUM(amount_charged), 0) AS revenue
        FROM sessions WHERE status='completed'
        GROUP BY month ORDER BY month DESC LIMIT ?
    """, (months_count,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ── Ledger ──────────────────────────────────────────────────

def add_transaction(session_id, member_id, tx_type: str, amount: float,
                    notes: str = ""):
    conn = get_connection()
    conn.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, member_id, tx_type, amount, notes))
    conn.commit()
    conn.close()


def get_cash_log(date_str: str = None, limit: int = 500) -> list:
    """Every ledger row for a day, newest first, with names joined in."""
    conn = get_connection()
    if date_str:
        rows = conn.execute("""
            SELECT t.*, m.name AS member_name, s.pc_name
            FROM transactions t
            LEFT JOIN members m ON m.id = t.member_id
            LEFT JOIN sessions s ON s.id = t.session_id
            WHERE date(t.timestamp) = ?
            ORDER BY t.id DESC LIMIT ?
        """, (date_str, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT t.*, m.name AS member_name, s.pc_name
            FROM transactions t
            LEFT JOIN members m ON m.id = t.member_id
            LEFT JOIN sessions s ON s.id = t.session_id
            ORDER BY t.id DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transaction_totals(date_str: str = None) -> dict:
    conn = get_connection()
    where, params = ("WHERE date(timestamp)=?", (date_str,)) if date_str else ("", ())
    rows = conn.execute(f"""
        SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
        FROM transactions {where} GROUP BY type
    """, params).fetchall()
    conn.close()
    return {r["type"]: {"total": float(r["total"]), "count": r["cnt"]} for r in rows}


# ── Members ─────────────────────────────────────────────────

def get_all_members() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM members ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_by_id(member_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_member_by_username(username: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_members(query: str) -> list:
    conn = get_connection()
    like = f"%{query}%"
    rows = conn.execute("""
        SELECT * FROM members
        WHERE name LIKE ? OR username LIKE ? OR COALESCE(phone,'') LIKE ?
        ORDER BY name COLLATE NOCASE LIMIT 100
    """, (like, like, like)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_member(name: str, username: str, password: str, balance: float = 0.0,
                  notes: str = "", phone: str = "") -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO members (name, username, password_hash, balance, notes, phone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, username, hash_password(password), balance, notes, phone))
    member_id = cur.lastrowid
    if balance:
        cur.execute("""
            INSERT INTO transactions (member_id, type, amount, notes)
            VALUES (?, 'topup', ?, 'Opening balance')
        """, (member_id, balance))
    conn.commit()
    conn.close()
    return member_id


def update_member(member_id: int, name: str, username: str, notes: str = "",
                  new_password: str = None, phone: str = None):
    conn = get_connection()
    if new_password:
        conn.execute("""
            UPDATE members SET name=?, username=?, notes=?, password_hash=?,
                               phone=COALESCE(?, phone)
            WHERE id=?
        """, (name, username, notes, hash_password(new_password), phone, member_id))
    else:
        conn.execute("""
            UPDATE members SET name=?, username=?, notes=?, phone=COALESCE(?, phone)
            WHERE id=?
        """, (name, username, notes, phone, member_id))
    conn.commit()
    conn.close()


def delete_member(member_id: int):
    conn = get_connection()
    conn.execute("UPDATE sessions SET member_id=NULL WHERE member_id=?", (member_id,))
    conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()


def deduct_member_balance(member_id: int, amount: float, session_id=None,
                          notes: str = "Session charge"):
    conn = get_connection()
    conn.execute("""
        UPDATE members
        SET balance = balance - ?, total_spent = total_spent + ?,
            last_seen = datetime('now','localtime')
        WHERE id = ?
    """, (amount, amount, member_id))
    conn.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, 'session_charge', ?, ?)
    """, (session_id, member_id, -abs(amount), notes))
    conn.commit()
    conn.close()


def refund_member_balance(member_id: int, amount: float, session_id=None,
                          notes: str = "Unused time refunded"):
    conn = get_connection()
    conn.execute("""
        UPDATE members
        SET balance = balance + ?, total_spent = MAX(0, total_spent - ?)
        WHERE id = ?
    """, (amount, amount, member_id))
    conn.execute("""
        INSERT INTO transactions (session_id, member_id, type, amount, notes)
        VALUES (?, ?, 'refund', ?, ?)
    """, (session_id, member_id, amount, notes))
    conn.commit()
    conn.close()


def topup_member_balance(member_id: int, amount: float, notes: str = "Manual top up"):
    conn = get_connection()
    conn.execute("UPDATE members SET balance = balance + ? WHERE id=?",
                 (amount, member_id))
    conn.execute("""
        INSERT INTO transactions (member_id, type, amount, notes)
        VALUES (?, 'topup', ?, ?)
    """, (member_id, amount, notes))
    conn.commit()
    conn.close()


def remove_member_balance(member_id: int, amount: float,
                          notes: str = "Manual balance removal"):
    conn = get_connection()
    conn.execute("UPDATE members SET balance = balance - ? WHERE id=?",
                 (amount, member_id))
    conn.execute("""
        INSERT INTO transactions (member_id, type, amount, notes)
        VALUES (?, 'refund', ?, ?)
    """, (member_id, -amount, notes))
    conn.commit()
    conn.close()


def get_member_sessions(member_id: int) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM sessions WHERE member_id=? ORDER BY start_time DESC LIMIT 200
    """, (member_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verify_member_login(username: str, password: str):
    """
    Member self-service login. Verifies against the salted hash and
    transparently upgrades legacy single-round SHA-256 rows.
    """
    member = get_member_by_username(username.strip())
    if not member:
        return None
    stored = member["password_hash"] or ""
    if verify_password(password, stored):
        if not is_hashed(stored):
            conn = get_connection()
            conn.execute("UPDATE members SET password_hash=? WHERE id=?",
                         (hash_password(password), member["id"]))
            conn.commit()
            conn.close()
        return member
    # Legacy databases hashed with plain sha256
    if hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored):
        conn = get_connection()
        conn.execute("UPDATE members SET password_hash=? WHERE id=?",
                     (hash_password(password), member["id"]))
        conn.commit()
        conn.close()
        return member
    return None


# ── Maintenance ─────────────────────────────────────────────

def backup_db(dest_dir: str = None) -> str:
    """Consistent hot backup (safe while the app is running)."""
    dest_dir = dest_dir or paths.backups_dir()
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(dest_dir, f"azcafe_{stamp}.db")
    src = get_connection()
    try:
        dst = sqlite3.connect(dest)
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()
    return dest


def db_info() -> dict:
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    conn = get_connection()
    counts = {}
    for table in ("members", "pcs", "sessions", "transactions"):
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
        except sqlite3.Error:
            counts[table] = 0
    conn.close()
    return {"path": DB_PATH, "size_bytes": size, "counts": counts}


def prune_backups(keep: int = 30):
    """Keep the newest N backups, delete the rest."""
    folder = paths.backups_dir()
    files = sorted(
        (os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".db")),
        key=os.path.getmtime, reverse=True,
    )
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def copy_db_to(path: str) -> str:
    shutil.copy2(DB_PATH, path)
    return path
