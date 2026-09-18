# ============================================================
#  AZ Cafe - Database Layer
#  SQLite database for members, sessions, billing, settings
# ============================================================

import sqlite3
import os
import hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "azcafe.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    return conn


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    cur  = conn.cursor()

    # ── Members ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            balance       REAL    DEFAULT 0.0,
            total_spent   REAL    DEFAULT 0.0,
            created_at    TEXT    DEFAULT (datetime('now')),
            last_seen     TEXT,
            notes         TEXT
        )
    """)

    # ── PC Registry ─────────────────────────────────────────
    # Stores remembered PCs (position on dashboard, display name)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pcs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_name       TEXT    UNIQUE NOT NULL,
            display_name  TEXT,
            grid_x        INTEGER DEFAULT 0,
            grid_y        INTEGER DEFAULT 0,
            group_name    TEXT    DEFAULT 'Default',
            added_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── Sessions ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_name       TEXT    NOT NULL,
            member_id     INTEGER,                  -- NULL = guest
            guest_name    TEXT,
            start_time    TEXT    NOT NULL,
            end_time      TEXT,
            duration_mins INTEGER DEFAULT 0,
            amount_charged REAL   DEFAULT 0.0,
            payment_type  TEXT    DEFAULT 'cash',   -- cash / balance
            status        TEXT    DEFAULT 'active', -- active / completed / cancelled
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
    """)

    # ── Pricing Plans ───────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pricing_plans (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            rate_per_hour REAL    NOT NULL,
            min_minutes   INTEGER DEFAULT 0,
            is_default    INTEGER DEFAULT 0
        )
    """)

    # ── Time Packages (Phase 4B) ────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS time_packages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            duration_mins INTEGER NOT NULL,
            price         REAL    NOT NULL,
            description   TEXT
        )
    """)

    # ── Migrations for existing DBs ─────────────────────────
    # Ensure pcs table has pricing_plan_id (Phase 4C)
    try:
        cur.execute("ALTER TABLE pcs ADD COLUMN pricing_plan_id INTEGER REFERENCES pricing_plans(id)")
    except sqlite3.OperationalError:
        pass

    # Ensure sessions table has discount_pct and discount_amount (Phase 4D)
    try:
        cur.execute("ALTER TABLE sessions ADD COLUMN discount_pct REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE sessions ADD COLUMN discount_amount REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass

    # ── Admin Settings ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ── Transactions / Cash Log ─────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER,
            member_id     INTEGER,
            type          TEXT,   -- session_charge / topup / refund
            amount        REAL,
            timestamp     TEXT    DEFAULT (datetime('now')),
            notes         TEXT
        )
    """)

    # ── Seed default data ────────────────────────────────────
    _seed_defaults(cur)

    conn.commit()
    conn.close()
    print("[DB] Database initialised OK")


def _seed_defaults(cur):
    """Insert default records if the tables are empty."""

    # Default pricing plan
    cur.execute("SELECT COUNT(*) FROM pricing_plans")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO pricing_plans (name, rate_per_hour, min_minutes, is_default)
            VALUES (?, ?, ?, ?)
        """, ("Standard", 60.0, 0, 1))   # Rs 60/hour default

    # Default time packages (Phase 4B bundles)
    cur.execute("SELECT COUNT(*) FROM time_packages")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO time_packages (name, duration_mins, price, description)
            VALUES (?, ?, ?, ?)
        """, [
            ("1 Hour Bundle", 60, 60.0, "Standard 1 Hour"),
            ("2 Hour Pass", 120, 110.0, "Save Rs 10"),
            ("3 Hour Gamer Pass", 180, 150.0, "Save Rs 30"),
            ("5 Hour Pro Pass", 300, 240.0, "Save Rs 60 (Best Value)"),
        ])

    # Default settings
    defaults = {
        "admin_password":   "admin123",
        "shop_name":        "AZ Cafe",
        "low_time_warning": "5",          # minutes before end to warn
        "auto_lock":        "1",
        "receipt_printer":  "0",
    }
    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )


# ── Helper functions ─────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_setting(key: str, default=None):
    conn = get_connection()
    row  = conn.execute(
        "SELECT value FROM settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value))
    )
    conn.commit()
    conn.close()


def get_default_rate() -> float:
    conn = get_connection()
    row  = conn.execute(
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


def save_pc(pc_name: str, grid_x=0, grid_y=0):
    """Remember a PC's position. Called when a new PC connects for the first time."""
    conn = get_connection()
    conn.execute("""
        INSERT OR IGNORE INTO pcs (pc_name, display_name, grid_x, grid_y)
        VALUES (?, ?, ?, ?)
    """, (pc_name, pc_name, grid_x, grid_y))
    conn.commit()
    conn.close()


def update_pc_position(pc_name: str, grid_x: int, grid_y: int):
    conn = get_connection()
    conn.execute(
        "UPDATE pcs SET grid_x=?, grid_y=? WHERE pc_name=?",
        (grid_x, grid_y, pc_name)
    )
    conn.commit()
    conn.close()


def update_pc_display_name(pc_name: str, display_name: str):
    conn = get_connection()
    conn.execute(
        "UPDATE pcs SET display_name=? WHERE pc_name=?",
        (display_name, pc_name)
    )
    conn.commit()
    conn.close()


def update_pc_group(pc_name: str, group_name: str):
    conn = get_connection()
    conn.execute(
        "UPDATE pcs SET group_name=? WHERE pc_name=?",
        (group_name, pc_name)
    )
    conn.commit()
    conn.close()


def get_all_pc_groups() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT group_name FROM pcs WHERE group_name IS NOT NULL AND group_name != '' ORDER BY group_name").fetchall()
    conn.close()
    groups = [r["group_name"] for r in rows]
    return groups if groups else ["Default"]


def get_all_pcs() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM pcs ORDER BY grid_y, grid_x").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def start_session(pc_name: str, member_id=None, guest_name=None,
                  duration_mins=60, amount=0.0, payment_type="cash",
                  discount_pct=0.0, discount_amount=0.0) -> int:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO sessions
            (pc_name, member_id, guest_name, start_time, duration_mins,
             amount_charged, payment_type, status, discount_pct, discount_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
    """, (pc_name, member_id, guest_name,
          datetime.now().isoformat(), duration_mins, amount, payment_type,
          discount_pct, discount_amount))
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id: int, actual_amount: float = None):
    """
    Mark a session completed.
    actual_amount: when provided (early manual stop), overwrites amount_charged
                   with the charge for time actually used.
                   When None (natural timer expiry), amount_charged is unchanged.
    """
    conn = get_connection()
    if actual_amount is not None:
        conn.execute("""
            UPDATE sessions
            SET end_time=?, status='completed', amount_charged=?
            WHERE id=?
        """, (datetime.now().isoformat(), round(actual_amount, 2), session_id))
    else:
        conn.execute("""
            UPDATE sessions
            SET end_time=?, status='completed'
            WHERE id=?
        """, (datetime.now().isoformat(), session_id))
    conn.commit()
    conn.close()


def get_active_session(pc_name: str):
    conn = get_connection()
    row  = conn.execute("""
        SELECT * FROM sessions
        WHERE pc_name=? AND status='active'
        ORDER BY id DESC LIMIT 1
    """, (pc_name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_today_revenue() -> float:
    conn   = get_connection()
    today  = datetime.now().strftime("%Y-%m-%d")
    row    = conn.execute("""
        SELECT COALESCE(SUM(amount_charged), 0) as total
        FROM sessions
        WHERE date(start_time)=? AND status='completed'
    """, (today,)).fetchone()
    conn.close()
    return float(row["total"])


def get_today_sessions() -> int:
    conn  = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    row   = conn.execute("""
        SELECT COUNT(*) as cnt FROM sessions
        WHERE date(start_time)=? AND status='completed'
    """, (today,)).fetchone()
    conn.close()
    return int(row["cnt"])


def search_members(query: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM members
        WHERE name LIKE ? OR username LIKE ?
        ORDER BY name LIMIT 20
    """, (f"%{query}%", f"%{query}%")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_pricing_plans() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pricing_plans ORDER BY is_default DESC, name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deduct_member_balance(member_id: int, amount: float):
    conn = get_connection()
    conn.execute("""
        UPDATE members
        SET balance     = balance - ?,
            total_spent = total_spent + ?,
            last_seen   = datetime('now')
        WHERE id = ?
    """, (amount, amount, member_id))
    conn.commit()
    conn.close()


def get_all_members() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM members ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_by_id(member_id: int):
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM members WHERE id=?", (member_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_member(name: str, username: str, password: str,
                  balance: float = 0.0):
    conn = get_connection()
    conn.execute("""
        INSERT INTO members (name, username, password_hash, balance)
        VALUES (?, ?, ?, ?)
    """, (name, username, hash_password(password), balance))
    conn.commit()
    conn.close()


def update_member(member_id: int, name: str, username: str,
                  notes: str, new_password: str = None):
    conn = get_connection()
    if new_password:
        conn.execute("""
            UPDATE members
            SET name=?, username=?, notes=?, password_hash=?
            WHERE id=?
        """, (name, username, notes, hash_password(new_password), member_id))
    else:
        conn.execute("""
            UPDATE members
            SET name=?, username=?, notes=?
            WHERE id=?
        """, (name, username, notes, member_id))
    conn.commit()
    conn.close()


def delete_member(member_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()


def topup_member_balance(member_id: int, amount: float):
    conn = get_connection()
    conn.execute("""
        UPDATE members SET balance = balance + ? WHERE id=?
    """, (amount, member_id))
    conn.execute("""
        INSERT INTO transactions (member_id, type, amount, notes)
        VALUES (?, 'topup', ?, 'Manual top up')
    """, (member_id, amount))
    conn.commit()
    conn.close()


def remove_member_balance(member_id: int, amount: float):
    conn = get_connection()
    conn.execute("""
        UPDATE members SET balance = balance - ? WHERE id=?
    """, (amount, member_id))
    conn.execute("""
        INSERT INTO transactions (member_id, type, amount, notes)
        VALUES (?, 'refund', ?, 'Manual balance removal')
    """, (member_id, -amount))
    conn.commit()
    conn.close()

def get_member_sessions(member_id: int) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM sessions
        WHERE member_id=?
        ORDER BY start_time DESC
        LIMIT 100
    """, (member_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verify_member_login(username: str, password: str):
    conn = get_connection()
    row  = conn.execute("""
        SELECT * FROM members
        WHERE username=? AND password_hash=?
    """, (username, hash_password(password))).fetchone()
    conn.close()
    return dict(row) if row else None


def get_sessions_by_date(date_str: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM sessions
        WHERE date(start_time) = ?
        ORDER BY start_time DESC
    """, (date_str,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_per_pc_stats() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            pc_name,
            COUNT(*)                        AS total_sessions,
            COALESCE(SUM(duration_mins), 0) AS total_mins,
            COALESCE(SUM(amount_charged), 0)AS total_revenue,
            MAX(start_time)                 AS last_used
        FROM sessions
        WHERE status = 'completed'
        GROUP BY pc_name
        ORDER BY total_revenue DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_members(limit: int = 20) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            m.id, m.name, m.username,
            m.balance, m.total_spent,
            COUNT(s.id) AS session_count
        FROM members m
        LEFT JOIN sessions s ON s.member_id = m.id
        GROUP BY m.id
        ORDER BY m.total_spent DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_revenue_range(start_date: str, end_date: str) -> float:
    conn = get_connection()
    row  = conn.execute("""
        SELECT COALESCE(SUM(amount_charged), 0) AS total
        FROM sessions
        WHERE date(start_time) BETWEEN ? AND ?
        AND status = 'completed'
    """, (start_date, end_date)).fetchone()
    conn.close()
    return float(row["total"])


def get_daily_revenue_range(start_date: str, end_date: str) -> list:
    """Get per-day revenue breakdown for chart visualization (Phase 6C)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            date(start_time) AS day,
            COALESCE(SUM(amount_charged), 0) AS revenue,
            COUNT(*) AS sessions_count
        FROM sessions
        WHERE date(start_time) BETWEEN ? AND ?
        AND status = 'completed'
        GROUP BY date(start_time)
        ORDER BY day ASC
    """, (start_date, end_date)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_revenue_breakdown(months_count: int = 6) -> list:
    """Get monthly revenue breakdown for chart visualization (Phase 6C)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strftime('%Y-%m', start_time) AS month,
            COALESCE(SUM(amount_charged), 0) AS revenue,
            COUNT(*) AS sessions_count
        FROM sessions
        WHERE status = 'completed'
        GROUP BY strftime('%Y-%m', start_time)
        ORDER BY month DESC
        LIMIT ?
    """, (months_count,)).fetchall()
    conn.close()
    res = [dict(r) for r in rows]
    res.reverse()
    return res


def create_pricing_plan(name: str, rate_per_hour: float,
                        min_minutes: int = 0):
    conn = get_connection()
    conn.execute("""
        INSERT INTO pricing_plans (name, rate_per_hour, min_minutes)
        VALUES (?, ?, ?)
    """, (name, rate_per_hour, min_minutes))
    conn.commit()
    conn.close()


def update_pricing_plan(plan_id: int, name: str,
                        rate_per_hour: float, min_minutes: int):
    conn = get_connection()
    conn.execute("""
        UPDATE pricing_plans
        SET name=?, rate_per_hour=?, min_minutes=?
        WHERE id=?
    """, (name, rate_per_hour, min_minutes, plan_id))
    conn.commit()
    conn.close()


def delete_pricing_plan(plan_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM pricing_plans WHERE id=?", (plan_id,))
    conn.commit()
    conn.close()


def set_default_plan(plan_id: int):
    conn = get_connection()
    conn.execute("UPDATE pricing_plans SET is_default=0")
    conn.execute("UPDATE pricing_plans SET is_default=1 WHERE id=?",
                 (plan_id,))
    conn.commit()
    conn.close()


# ── Time Packages (Phase 4B) ─────────────────────────────────

def get_all_time_packages() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM time_packages ORDER BY duration_mins ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_time_package(name: str, duration_mins: int, price: float, description: str = ""):
    conn = get_connection()
    conn.execute("""
        INSERT INTO time_packages (name, duration_mins, price, description)
        VALUES (?, ?, ?, ?)
    """, (name, duration_mins, price, description))
    conn.commit()
    conn.close()


def update_time_package(pkg_id: int, name: str, duration_mins: int, price: float, description: str = ""):
    conn = get_connection()
    conn.execute("""
        UPDATE time_packages
        SET name=?, duration_mins=?, price=?, description=?
        WHERE id=?
    """, (name, duration_mins, price, description, pkg_id))
    conn.commit()
    conn.close()


def delete_time_package(pkg_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM time_packages WHERE id=?", (pkg_id,))
    conn.commit()
    conn.close()


# ── PC Plan Assignment (Phase 4C) ────────────────────────────

def get_pc_by_name(pc_name: str):
    conn = get_connection()
    row  = conn.execute("SELECT * FROM pcs WHERE pc_name=?", (pc_name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_pc_pricing_plan(pc_name: str, plan_id: int):
    conn = get_connection()
    conn.execute("UPDATE pcs SET pricing_plan_id=? WHERE pc_name=?", (plan_id, pc_name))
    conn.commit()
    conn.close()
