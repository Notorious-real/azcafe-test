# AZ Cafe — Repository Analysis & Code Review

> **Status note (added after the fix pass):** every issue in this review has since been
> addressed — see `docs/PHASE_STATUS.md` for the re-verification of all 45 plan sections
> and `tests/` (90 headless tests) for the evidence. This document is kept as the record
> of what the code looked like before the fixes.

**Repo:** `Notorious-real/azcafe-test` (private) · **Branch analyzed:** `arena/01a0b300-azcafe-test` @ `c4dc45f` ("Initial commit")
**Reviewed:** 2026-09-18 · **Size:** 33 tracked files, ~7.4k lines of Python, 729 KB working tree

---

## 1. What this project is

A LAN-based internet/gaming café management system with two applications:

| Component | Entry point | Role |
|---|---|---|
| **Admin app** | `server/main.py` → `server/admin_app.py` | Tkinter desktop GUI (dashboard, members, sessions, reports, pricing, settings) **and** the TCP server (`server/server_core.py`) in one process |
| **Client app** | `client/main.py` → `client/lock_screen.py`, `game_launcher.py` | Full-screen kiosk on each gaming PC: lock screen, member self-login, game launcher, timer overlay |
| **Shared** | `config.py`, `protocol.py`, `database.py` | Settings/theme, newline-delimited JSON protocol, SQLite layer |

**Data flow:** clients open a TCP socket to port 5555 → send `REGISTER` with hostname → receive commands (`START_SESSION`, `STOP_SESSION`, `LOCK`, `TIME_UPDATE`, `LOW_TIME_WARNING`, `SESSION_EXPIRED`, `SHUTDOWN`, `RESTART`) → send events back. All state (billing, timers, sessions) lives in the admin process' memory + a single SQLite file `azcafe.db`. Distribution is by PyInstaller onedir builds driven by `BUILD.bat`, with `DEPLOY.md` as the operator guide.

**Stack:** Python 3.11 · stdlib `tkinter` + `PIL` (no `customtkinter` used despite being in `requirements.txt`) · raw `socket` + `json` · SQLite.

**Maturity:** a working, fairly complete v1 with real business logic (pricing plans, time packages, discounts, balance payments, drag-and-drop PC grid, CSV/HTML report export, custom canvas charts). It reads like a "Codex/Cursor-built from a spec" project: consistent formatting and section headers, phase markers in comments, but **no tests, no CI, no license, no logging, a 2-line README**, and a handful of half-finished features.

---

## 2. What is genuinely good

- **Clean-ish layering.** UI / socket core / DB layer are separated, and the client's socket logic (`client/client_core.py`) is decoupled from its UI via an `on_event` callback — testable if you ever add tests.
- **Drift-corrected server timer.** `server_core._timer_loop` uses `time.monotonic()` and accumulates `next_tick` instead of sleeping 1 s, so it doesn't drift. Most hobby projects get this wrong.
- **Prepaid model is coherent.** Time is sold up-front, `end_session(actual_amount=…)` re-prices on early stop, and the "rate implied by this session" trick (dialogs.py:490) keeps stop-charges consistent with the package the customer actually bought instead of today's default rate.
- **Thread-careful socket handling.** `MessageReader` handles partial reads and coalesced messages; `send()` swallows `OSError`; a heartbeat watchdog exists; per-PC locking around the client dict.
- **Sensible defaults seeded** (`_seed_defaults`): pricing plan, 4 time packages, shop settings, PKR currency, red/dark theme.
- **Deployment is documented** (BUILD.bat + DEPLOY.md + Windows Firewall instructions) — much better than most café scripts.

---

## 3. Findings by severity

### 🔴 P0 — Data leak committed to the repo

| # | Finding | Evidence |
|---|---|---|
| 1 | **Real customer data and password hashes are committed.** `azcafe.db` contains 3 imported members with **real names, phone numbers and SHA-256 password hashes**, plus `settings.admin_password = "admin123"` in **plaintext**. | `azcafe.db` (tracked), `git ls-files` |
| 2 | **`user_import_data.csv` is a leaked third-party export + AI agent transcript.** It holds 3 real member rows (usernames, obfuscated passwords, phone numbers, birthdates) followed by ~44 lines of a **coding-agent session log** — step indices, tool calls, "the stream was interrupted", and a local path `C:\Users\Server\Downloads\CCP clone (AZ Cafe)\azcafe test`. `import_user_data.csv` (0 bytes) is a second, empty copy. | `user_import_data.csv` lines 1–47 |
| 3 | **No secret hygiene.** `config.ADMIN_PASSWORD = "admin123"` is a source constant and the documented default (`DEPLOY.md`), stored verbatim by Settings → Change Password. | `config.py:12`, `database.py:166`, `server/settings_panel.py:267` |

**Why it matters:** the repo is private today, but history is forever — if it's ever made public, shared with a contractor, or forked, you leak paying customers' credentials and phone numbers. Any member whose password is reused elsewhere is exposed.
**Fix:** (a) `git rm --cached azcafe.db user_import_data.csv import_user_data.csv`, add `*.db`, `*.db-wal`, `*.db-shm`, `*_data.csv`, `.env` to `.gitignore`; (b) because it's already in history, purge with `git filter-repo`/BFG and **rotate any passwords that were in that data**; (c) move the admin password out of source — store a salted hash (bcrypt/`hashlib.scrypt`), force a change on first run, and ship a `azcafe.example.db` or first-run seeding instead of a populated DB.

---

### 🔴 P0 — Money and billing correctness

**4. Early stop never refunds the member's balance (the UI says it does).**
`dialogs.py:553` renders `Prepaid: Rs X | Refund: Rs Y` in green, and `_confirm()` passes `actual_amount` to the server (dialogs.py:621). The server then only rewrites the *session row*:

```python
# server_core.py:422 stop_session()
db.end_session(client.session_id, actual_amount=actual_amount)   # sessions table only
```

Nothing credits `members.balance` back. For a balance session the full amount was already debited at start (`server_core.py:230` on member login, `dashboard.py:294` on admin "Member Balance" start). Example: member with Rs 500 at Rs 60/h → server converts the whole balance to 500 minutes and debits Rs 500; customer stops after 40 minutes → Rs 460 is silently kept even though the dialog promised a refund.
**Fix:** in `stop_session`, when `session.payment_type == "balance"` and `member_id` is set, call a new `db.refund_member_balance(member_id, prepaid - actual)` that writes a `transactions` row of type `session_refund`.

**5. A customer can end their own session and keep playing, unbilled and unlocked.**
Client: `game_launcher._confirm_end_session` (game_launcher.py:239) → `report_session_ended()` → `SESSION_ENDED`. Server:

```python
# server_core.py:287
def _on_session_ended(self, client, data):
    if client.session_id: db.end_session(client.session_id)   # ← marks completed
    client.session_id = None; client.remaining_secs = 0
    client.status = config.STATUS_FREE; self._notify_update()  # ← never sends STOP_SESSION/LOCK
```

Compare with the expiry path (`_timer_loop`), which *does* send `SESSION_EXPIRED` and makes the client lock. So on a self-ended session: the server closes the session, the card goes **FREE**, but the client PC stays **unlocked on the game launcher with no timer** — the customer keeps gaming on a PC the cashier thinks is idle. There's also no charge/used-time accounting on this path (the customer sets the stop time; prepaid cash means they only "lose" time).
**Fix:** have `_on_session_ended` send `STOP_SESSION` (or `LOCK`) back before clearing state, and price the used time server-side before completing the row.

**6. Any disconnect mid-session orphans the session — permanently, and for free.**
`_remove_client` (server_core.py:296) removes the client from the dict but **never calls `db.end_session`**; `_heartbeat_watchdog` (server_core.py:374) routes timeouts into the same function. Worse, `_on_register` (server_core.py:268) creates a **brand-new `ClientConnection`** and sets `status = FREE`, so if the PC reconnects even seconds later (cable bump, switch reboot, Wi-Fi blip) the server has lost `session_id` and `remaining_secs` forever. Results: rows stuck at `status='active'` in `sessions`, revenue that never appears in "today's revenue" (which counts only `completed`), `get_active_session()` returning stale rows, the dashboard showing FREE while the DB shows ACTIVE, and the customer's remaining prepaid time silently evaporating.
**Fix:** on `_remove_client`, if a session is active → either close it (`db.end_session`) or (better) mark it `suspended` with remaining seconds persisted; on `REGISTER`, re-attach by looking up the active/suspended session for that `pc_name`, restore `remaining_secs` from `start_time + duration`, and re-send `START_SESSION`/`LOCK` as appropriate. Add a startup reconciliation pass that closes orphaned `active` rows.

**7. Time added via "Add Time" is never persisted or charged.**
`server_core.add_time` (server_core.py:510) only bumps the in-memory counter and re-sends `TIME_UPDATE`; `dashboard._dialog_add_time` (dashboard.py:331) collects no money. The DB's `duration_mins`/`amount_charged` are untouched, so reports, receipts and the member's `total_spent` all undercount. If the PC is offline, the minutes vanish entirely (the call returns `False` and nothing is shown).
**Fix:** make it `db.extend_session(session_id, extra_mins, amount)` + a `transactions` row, and surface a payment prompt in the dialog.

**8. No server-side guard against double-starting a session on the same PC.**
`server_core.start_session` creates a new `sessions` row unconditionally, even if that PC already has an `active` session — and only `client.session_id` is tracked, so the older row becomes orphaned and can never be closed by the UI. Double-clicking Start, or a Start on a PC whose card is stale, silently produces duplicate `active` rows and double billing. *(Correction: the balance check for member "balance" payments **does** exist in `StartSessionDialog._confirm`, dialogs.py:414-423 — an earlier draft of this review claimed otherwise. The remaining gap is that the check lives only in the UI.)*
**Fix:** move the balance check into `start_session`/`db` (defense in depth), refuse to start when `db.get_active_session(pc_name)` returns a row, and expose a "force close stale session" action.

**9. The transactions ledger is 90 % empty.**
`transactions` is only written by `topup_member_balance` and `remove_member_balance` (database.py:452, 465) — **session charges, refunds and add-time purchases are never recorded**. There is no cash-drawer audit trail, which is the one report a café owner actually needs.
**Fix:** write a transaction row in `start_session`, `stop_session`, `add_time` and the member self-login path; add a "Cash log / day-close" tab.

**10. Today's revenue is reported two different ways.**
Top bar uses `get_today_revenue()` → `WHERE status='completed'` (database.py:335). Reports → Today uses `get_sessions_by_date()` (no status filter) and sums `amount_charged` over rows (reports_panel.py:143–144), so it includes still-running sessions. The two numbers on the same screen will disagree — guaranteed support calls.
**Fix:** pick one definition (completed-only is right for revenue) and use it everywhere; show active sessions as a separate "open tabs" figure.

---

### 🟠 P1 — Crashes and broken features

**11. Admin unlock on a client PC throws an exception (verified by execution).**
`client/lock_screen.py:318-320` does `import database as db; db.get_setting("admin_password", …)`. But `DB_PATH` is next to `database.py` (`database.py:11`) and **`init_db()` is only ever called by the admin app** (`server/main.py:27`, `server/admin_app.py:50`). On a fresh gaming PC the client's `azcafe.db` doesn't exist, so the first admin unlock raises:

```
sqlite3.OperationalError: no such table: settings
```

Verified by copying `database.py` to an empty directory and calling `get_setting()`. In a `--windowed` PyInstaller build the traceback goes nowhere, so the button simply "does nothing" and the PC can only be unlocked by restarting the admin session — the exact opposite of an emergency override. The same wrong-DB design means the client's admin password can silently differ from the admin app's.
**Fix:** the admin password check belongs on the **server side** (the client asks the server to verify and the server answers `LOGIN_RESULT`-style), or the client must hold no DB at all. Minimum hotfix: wrap in `try/except` + `db.init_db()`, but the real fix is removing `database.py` from the client build entirely (`BUILD.bat` currently ships it as `--add-data`).

**12. Sessions panel crashes as soon as any session is active (verified by execution).**
`sessions_panel.py:61` uses `s.get("guest_name")` on a `sqlite3.Row`, which has no `.get()`:

```
AttributeError: 'sqlite3.Row' object has no attribute 'get'
```

Confirmed experimentally. Since `_refresh()` runs in `__init__`, opening **Sessions** with ≥1 active session raises inside the Tk callback.

**13. "Rename PC" doesn't persist.** `dashboard.py:339-347` only sets the label text; `db.update_pc_display_name()` exists and is **never called** (dead code). Renames vanish on restart.

**14. Three settings are decorative.** `receipt_printer` is never read anywhere; `low_time_warning` is saved but the server uses a hardcoded `WARN_THRESHOLDS = [300, 120, 60]` (server_core.py:308); `auto_lock` is saved and never enforced. Users will change these and see nothing happen.

**15. Two competing protocol modules.** `protocol.py` (used, constants + `MessageReader`) and `shared/protocol.py` (37 lines of a **different, unused** `CMD`/`STATUS` enum set with different names/values) both exist — `shared/protocol.py` is referenced nowhere (the only "shared" hit is a comment). Also, most of `protocol.py`'s constants are unused: `server_core` sends `"START_SESSION"`, `"STOP_SESSION"`, `"LOCK"`, `"MESSAGE"`, `"RESTART"`… as raw string literals, so typos can never be caught by the linter/IDE.
**Fix:** delete `shared/protocol.py`, import the constants everywhere, add a message-type enum and a version handshake.

**16. Thread-safety of Tkinter.** `server/main.py` calls `app.after(0, …)` from server threads (`on_pc_update`, `on_status_msg`). Tkinter is not thread-safe; this usually works but can produce `RuntimeError: main thread is not in main loop` during shutdown or `TclError` under load. Every `ClientConnection.send` also runs on a different thread than the UI reading the same objects.
**Fix:** a `queue.Queue` drained by a 50 ms `after()` poller on the main thread.

**17. SQLite concurrency has no safety net.** A new connection is opened per call with `PRAGMA journal_mode=WAL` set on every connection, but **no `busy_timeout`** and no retry. With the timer thread, socket threads and the UI all writing, `database is locked` is a matter of traffic. There is also no migration version, no backup/rotate of `azcafe.db`, and the DB lives inside the install folder (see #20).

**18. Offline PCs look alive forever / double countdowns.** If the server process dies, no further `on_pc_update` arrives, so cards stay `ACTIVE` and their **own local tick** (`pc_card.py:353-357`) keeps counting down to zero — showing a session that doesn't exist. Meanwhile the server *also* decrements the same value, and `SessionOverlay._tick` (client, session_screen.py:143) decrements a third copy, while the launcher's timer only refreshes on the 10 s server sync. Three clocks, one truth: pick one (server-authoritative) and derive displays from it.

**19. Reconnect punishes the paying customer.** On any socket blip, `client/main.py` locks the PC (killing launched games) while the server keeps billing — and because of #6 the server has by then forgotten the session, so a reconnect leaves the customer locked out with money spent and no way back except a manual cashier restart. A 3-second Wi-Fi hiccup should not end a paid hour.

**20. Deployment/packaging risks.**
- `SERVER_IP` is a hardcoded literal (`client/client_core.py:19`) — every site change means editing source and **rebuilding the exe**; no config file, env var, CLI flag or UDP discovery.
- `BUILD.bat` `--add-data "database.py;."` ships the whole DB layer (and an empty DB) to client PCs — the root cause of #11.
- `--windowed` on both apps means a startup crash is a silent no-op (no console, no log file). There is no logging module anywhere in the project.
- The DB is written next to the executable, i.e. under `C:\AZCafe\...`; that breaks with UAC/Program Files, and any "extract the new version over the old folder" update can wipe the owner's entire history.
- `setup_autostart.py` writes `HKCU\...\Run`, which the café's own users can delete, and it isn't bundled/run by `BUILD.bat` — DEPLOY.md tells the operator to run a dev-only script.

**21. Kiosk escape hatches.** Only `<Alt-F4>` and `<Escape>` are neutralised (`client/main.py:_bind_hotkeys`). Alt+Tab, Win, Ctrl+Alt+Del/Task Manager, right-click taskbar and killing the process are all still available, and the client is `--windowed` with no watchdog/service to restart it. Treat the lock screen as a deterrent, not a security control — or move to a Windows shell-replacement/kiosk mode plus a watchdog service.

**22. No auth or transport security on the socket.** Any host on the LAN can `REGISTER` as any PC name, or send `MEMBER_LOGIN` with a captured username/password (plaintext over TCP) and drain that member's balance; the server can't verify an event came from the registered machine. Member passwords are single-round **unsalted SHA-256** (`database.py:181-182`) — brute-forceable instantly with a rainbow table. The client's admin panel has an attempts counter that is purely cosmetic (no lockout/delay), and a brute-forcer can script the socket.
**Fix (short term):** per-PC shared secret in `REGISTER`, `busy_timeout`, `hashlib.scrypt`/bcrypt with per-user salt, unlock lockout, admin-password check moved server-side.
**Fix (long term):** TLS (or at least HMAC-signed messages) — required if the café network is reachable by customers, which it is.

---

### 🟡 P2 — Quality, repo hygiene, maintainability

| # | Finding |
|---|---|
| 23 | **The CSV import can't read either CSV in the repo.** `members_panel._import_csv` (members_panel.py:394) expects headers `name,username,password,balance`; both committed files are a third-party export with 46 different columns (`Username,PWORD,UnlimitedTime,…`). The importer that produced `azcafe.db`'s 3 members isn't in the repo — it was the agent session that leaked into the CSV. Write a real importer (or delete the files and the feature). |
| 24 | **Dead code / duplicated logic:** `shared/protocol.py` (unused), `import_user_data.csv` (0 bytes), `db.hash_password` appears "unused" only because `database.py` imports it (fine), `update_pc_display_name` and `get_revenue_range` never called, `_warnings_sent` initialised with `hasattr` inside a hot loop, `server/admin_app.py:50` calls `init_db()` although `server/main.py:27` already did. |
| 25 | **18 broad `except Exception`/bare `except`** blocks, several swallowing failures silently (`client/main.py` connection loop `except (…) : pass`, `game_launcher._launch_game` catching everything and showing "it will open shortly"). Errors are printed or dropped; nothing is logged. |
| 26 | **No tests, no CI, no LICENSE, no `pyproject.toml`.** A 7.4k-line app whose core is money math has zero automated checks. `requirements.txt` omits `pyinstaller`'s real pinning and includes `customtkinter`, which is never imported. |
| 27 | **Giant UI files.** `reports_panel.py` (746), `dialogs.py` (724), `members_panel.py` (715), `settings_panel.py` (609) each mix widget construction, data access and business math. The custom canvas chart drawing (~90 lines) belongs in its own module. |
| 28 | **Hard-coded PII-adjacent paths and magic strings:** game launcher entries are fixed `C:\Program Files…` paths in `DEFAULT_GAMES` — the operator can't edit them without a rebuild, and a missing path silently falls back to `os.startfile()` which throws (and is caught and reported as success). This list should be a DB table or JSON config file. |
| 29 | **`README.md` is 2 lines** while `DEPLOY.md` is thorough — merge them and document the protocol, the DB schema, the money rules (prepaid, refund, add-time) and the recovery procedure for orphaned sessions. |
| 30 | **Timezone/date handling** uses `datetime.now()` and SQLite `datetime('now')` (**UTC** in SQLite) mixed in the same schema — `created_at`/`added_at` defaults are UTC while `start_time`/`end_time` are local `.isoformat()`. Reports filter with `date(start_time) = today_local`, so rows created near midnight can land in the wrong day bucket. Standardise on local time everywhere (or store UTC and convert at the edges). |

---

## 4. Verified by execution

| Check | Result |
|---|---|
| `python3 -m compileall` on all 27 modules | passes (no syntax errors) |
| `db.get_setting()` on a fresh DB (client's real situation) | ❌ `OperationalError: no such table: settings` |
| `sqlite3.Row.get()` (sessions panel path) | ❌ `AttributeError: 'sqlite3.Row' object has no attribute 'get'` |
| Reachability scan of DB helper functions | `update_pc_display_name`, `get_revenue_range` never called |
| Reachability scan of protocol constants | most `CMD_*` constants unused; `shared/protocol.py` unused entirely |
| `init_db()` call sites | only the admin app — client never creates its DB |
| `end_session()` call sites | only `stop_session` and the expiry path — **not** on disconnect |

---

## 5. Suggested order of work

**Day 1 — stop the bleeding (small, high-value diffs)**
1. Purge the data leak: untrack `azcafe.db` + both CSVs, extend `.gitignore`, plan a history rewrite, rotate exposed passwords.
2. Fix the sessions-panel `Row.get()` crash → `s["guest_name"]`.
3. Send `STOP_SESSION`/`LOCK` back on client-initiated session end (#5).
4. Wrap the client's admin-unlock in a guarded path and stop shipping `database.py` to clients (#11).
5. Close/refund correctly: `db.end_session` on disconnect + persist `add_time` + `update_pc_display_name` on rename (#6, #7, #13).

**Week 1 — make the money trustworthy**
6. Balance validation, refund path, `transactions` rows for every money movement, one canonical revenue definition (#4, #8, #9, #10).
7. Session recovery on reconnect; reconcile orphaned `active` rows at startup (#6).
8. Replace thread-driven `after()` calls with a UI queue (#16); add `busy_timeout` and a `logging` setup with a rotating file log.

**Week 2 — hardening & maintainability**
9. Server-side admin password verification, salted `scrypt`/`bcrypt` hashes, unlock lockout, per-PC registration secret (#22).
10. External config file for `SERVER_IP`/games (no rebuild per site), DB moved to `%PROGRAMDATA%\AZCafe\` with automated daily backup (#20).
11. Delete `shared/protocol.py`, use the constants, add protocol versioning.
12. First tests: price/refund math, `MessageReader` framing, session lifecycle (start → stop → refund → revenue) against a temp SQLite file — these are exactly the invariants that are currently wrong.

---

## 6. One-paragraph summary

This is a genuinely useful, ~7.4k-line v1 of a gaming-café manager: the architecture (Tkinter admin + TCP server in one process, kiosk clients, prepaid SQLite billing) is sound and the UI work is thorough. The risks are concentrated in three places: **(1) a committed database and CSV containing real customer credentials/PII — and a leaked agent transcript — that need purging from history today; (2) billing holes where money is silently lost** (no refund on early stop, add-time never persisted, sessions orphaned by every disconnect with remaining time destroyed, a customer-triggerable "end session" that leaves the PC unlocked and unbilled, and two contradictory revenue numbers); and **(3) deployment fragility** — the client crash on admin unlock, a hardcoded IP requiring rebuilds, no logs, no tests, no CI. Fixing the P0 list is a day or two of focused work and removes essentially all of the risk to the owner's money and data.
