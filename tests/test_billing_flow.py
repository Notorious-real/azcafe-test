# ============================================================
#  End-to-end session flows through AZCafeServer — the paths that
#  used to leak money (self-end, disconnect, add-time, refunds).
#  Uses fake sockets; no network and no display required.
# ============================================================

import unittest

from tests.base import DBTestCase, connect_pc, make_server
import database as db
from server import server_core
from protocol import (
    CMD_LOCK, CMD_LOGIN_RESULT, CMD_LOW_TIME_WARNING, CMD_START_SESSION,
    CMD_STOP_SESSION, CMD_TIME_UPDATE, STATUS_ACTIVE, STATUS_LOCKED,
    STATUS_PAUSED,
)


class TestServerSessions(DBTestCase):

    def setUp(self):
        super().setUp()
        self.events = []
        self.statuses = []
        self.server = make_server(on_session_event=lambda k, p: self.events.append((k, p)),
                                  on_status_msg=self.statuses.append)

    # ── starting ────────────────────────────────────────────

    def test_start_session_sends_command_and_persists(self):
        client = connect_pc(self.server, "PC1")
        result = self.server.start_session("PC1", "Ali", 60, 60.0)
        self.assertTrue(result["ok"], result)
        self.assertEqual(client.status, STATUS_ACTIVE)
        self.assertEqual(client.remaining_secs, 3600)
        self.assertIn(CMD_START_SESSION, client.sock.types())
        session = db.get_open_session("PC1")
        self.assertEqual(session["duration_mins"], 60)
        self.assertEqual(session["remaining_secs"], 3600)

    def test_double_start_is_refused(self):
        connect_pc(self.server, "PC1")
        self.assertTrue(self.server.start_session("PC1", "Ali", 60, 60.0)["ok"])
        second = self.server.start_session("PC1", "Ali", 60, 60.0)
        self.assertFalse(second["ok"])
        self.assertIn("already", second["error"])
        self.assertEqual(len(db.get_open_sessions_all()), 1)

    def test_start_without_connection_is_refused(self):
        result = self.server.start_session("Ghost", "Ali", 60, 60.0)
        self.assertFalse(result["ok"])
        self.assertIsNone(db.get_open_session("Ghost"))

    def test_balance_payment_checks_wallet_server_side(self):
        connect_pc(self.server, "PC1")
        member_id = db.create_member("Poor", "poor", "pw", balance=10)
        result = self.server.start_session("PC1", "Poor", 60, 60.0,
                                           member_id=member_id,
                                           payment_type="balance")
        self.assertFalse(result["ok"])
        self.assertIn("Insufficient", result["error"])
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 10)
        self.assertIsNone(db.get_open_session("PC1"))

    def test_balance_payment_deducts_exactly_once(self):
        connect_pc(self.server, "PC1")
        member_id = db.create_member("Rich", "rich", "pw", balance=500)
        self.server.start_session("PC1", "Rich", 120, 120.0,
                                  member_id=member_id, payment_type="balance")
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 380)

    # ── stopping ────────────────────────────────────────────

    def test_admin_stop_refunds_and_locks(self):
        client = connect_pc(self.server, "PC1")
        member_id = db.create_member("Ali", "ali", "pw", balance=60)
        self.server.start_session("PC1", "Ali", 60, 60.0, member_id=member_id,
                                  payment_type="balance")
        client.remaining_secs = 1800          # half the hour used

        result = self.server.stop_session("PC1", actual_amount=30.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["charged"], 30.0)
        self.assertEqual(result["refund"], 30.0)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 30.0)
        self.assertEqual(client.status, STATUS_LOCKED)
        self.assertIn(CMD_STOP_SESSION, client.sock.types())
        self.assertIn(CMD_LOCK, client.sock.types())
        self.assertIsNone(db.get_open_session("PC1"))

    def test_customer_self_end_locks_the_pc_and_bills_used_time(self):
        """The bug that let a customer keep playing for free."""
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "Guest", 60, 60.0)   # cash prepaid
        client.remaining_secs = 900                            # 45 min used

        self.server._on_session_ended(client, {})

        self.assertIn(CMD_STOP_SESSION, client.sock.types())
        self.assertIn(CMD_LOCK, client.sock.types())
        self.assertEqual(client.status, STATUS_LOCKED)
        self.assertEqual(client.session_id, None)
        self.assertIsNone(db.get_open_session("PC1"))
        row = db.get_sessions_by_date(__import__("datetime").datetime.now().strftime("%Y-%m-%d"))[0]
        self.assertEqual(row["status"], "completed")
        self.assertAlmostEqual(row["amount_charged"], 45.0, places=2)   # 45 min @ Rs 60/h

    def test_self_end_refunds_balance_member(self):
        client = connect_pc(self.server, "PC1")
        member_id = db.create_member("Ali", "ali", "pw", balance=60)
        self.server.start_session("PC1", "Ali", 60, 60.0, member_id=member_id,
                                  payment_type="balance")
        client.remaining_secs = 1800
        self.server._on_session_ended(client, {})
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 30.0)

    def test_expiry_settles_and_locks(self):
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "Guest", 1, 1.0)
        client.remaining_secs = 1
        self.server._tick()                   # drops to zero
        self.server._tick()                   # settles
        self.assertIsNone(db.get_open_session("PC1"))
        self.assertEqual(client.status, STATUS_LOCKED)

    # ── recovery ────────────────────────────────────────────

    def test_disconnect_suspends_and_reconnect_resumes(self):
        client = connect_pc(self.server, "PC1")
        member_id = db.create_member("Ali", "ali", "pw", balance=120)
        self.server.start_session("PC1", "Ali", 120, 120.0, member_id=member_id,
                                  payment_type="balance")
        client.remaining_secs = 3000          # 20 minutes used

        self.server._remove_client(client, "cable pulled")
        session = db.get_open_session("PC1")
        self.assertEqual(session["status"], "suspended")
        self.assertEqual(session["remaining_secs"], 3000)

        # The PC comes back on a NEW connection
        revived = connect_pc(self.server, "PC1")
        self.assertEqual(revived.status, STATUS_ACTIVE)
        self.assertEqual(revived.remaining_secs, 3000)
        self.assertIn(CMD_START_SESSION, revived.sock.types())
        self.assertEqual(db.get_open_session("PC1")["status"], "active")

    def test_reconnect_without_session_locks_the_client(self):
        client = connect_pc(self.server, "PC1")
        self.assertIn(CMD_STOP_SESSION, client.sock.types())
        self.assertEqual(client.status, "FREE")

    # ── add time ────────────────────────────────────────────

    def test_add_time_persists_charges_and_notifies(self):
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "Guest", 60, 60.0)
        client.sock.clear()

        result = self.server.add_time("PC1", 30, 30.0)
        self.assertTrue(result["ok"], result)
        self.assertEqual(client.remaining_secs, 5400)
        self.assertIn(CMD_TIME_UPDATE, client.sock.types())
        session = db.get_open_session("PC1")
        self.assertEqual(session["duration_mins"], 90)
        self.assertEqual(session["amount_charged"], 90.0)
        self.assertEqual(db.get_transaction_totals()["time_purchase"]["total"], 30.0)

    def test_add_time_from_balance_validates_wallet(self):
        connect_pc(self.server, "PC1")
        member_id = db.create_member("Ali", "ali", "pw", balance=90)
        self.server.start_session("PC1", "Ali", 60, 60.0, member_id=member_id,
                                  payment_type="balance")
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 30.0)

        fail = self.server.add_time("PC1", 60, 60.0, payment_type="balance")
        self.assertFalse(fail["ok"])
        self.assertIn("Insufficient", fail["error"])

        ok = self.server.add_time("PC1", 30, 30.0, payment_type="balance")
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 0.0)
        self.assertEqual(db.get_open_session("PC1")["duration_mins"], 90)

    def test_add_time_without_session_is_refused(self):
        connect_pc(self.server, "PC1")
        self.assertFalse(self.server.add_time("PC1", 30, 0)["ok"])

    # ── pause / warnings ────────────────────────────────────

    def test_pause_freezes_the_timer(self):
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "G", 60, 60.0)
        self.server.pause_session("PC1")
        self.assertEqual(client.status, STATUS_PAUSED)
        before = client.remaining_secs
        self.server._tick()
        self.assertEqual(client.remaining_secs, before)
        self.server.resume_session("PC1")
        self.assertEqual(client.status, STATUS_ACTIVE)
        self.server._tick()
        self.assertEqual(client.remaining_secs, before - 1)

    def test_low_time_warning_uses_settings(self):
        db.set_setting("low_time_warning", "2")
        self.server.reload_settings()
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "G", 3, 3.0)
        client.remaining_secs = 61
        self.server._tick()                    # → 60
        self.assertIn(CMD_LOW_TIME_WARNING, client.sock.types())
        self.assertEqual(client.sock.last(CMD_LOW_TIME_WARNING)["minutes"], 1)

    # ── member self-service ─────────────────────────────────

    def test_member_login_buys_time_from_balance(self):
        client = connect_pc(self.server, "PC1")
        db.create_member("Ali", "ali", "pw", balance=120)
        db.set_setting("currency", "Rs")

        self.server._on_member_login(client, {"username": "ali", "password": "pw"})

        result = client.sock.last(CMD_LOGIN_RESULT)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["duration_secs"], 7200)      # Rs 120 @ Rs 60/h
        self.assertEqual(db.get_member_by_id(1)["balance"], 0.0)
        session = db.get_open_session("PC1")
        self.assertEqual(session["payment_type"], "balance")

    def test_member_login_rejects_bad_password_and_empty_wallet(self):
        client = connect_pc(self.server, "PC1")
        db.create_member("Broke", "broke", "pw", balance=0)
        self.server._on_member_login(client, {"username": "broke", "password": "nope"})
        self.assertFalse(client.sock.last(CMD_LOGIN_RESULT)["success"])
        self.server._on_member_login(client, {"username": "broke", "password": "pw"})
        self.assertFalse(client.sock.last(CMD_LOGIN_RESULT)["success"])
        self.assertIn("Insufficient", client.sock.last(CMD_LOGIN_RESULT)["reason"])

    def test_member_login_refused_when_session_running(self):
        client = connect_pc(self.server, "PC1")
        db.create_member("Ali", "ali", "pw", balance=120)
        self.server.start_session("PC1", "Guest", 30, 30.0)
        self.server._on_member_login(client, {"username": "ali", "password": "pw"})
        self.assertFalse(client.sock.last(CMD_LOGIN_RESULT)["success"])

    # ── admin unlock (1F) ───────────────────────────────────

    def test_admin_unlock_is_verified_by_the_server(self):
        client = connect_pc(self.server, "PC1")
        db.set_admin_password("s3cret")
        self.server._on_admin_unlock_request(client, {"password": "bad"})
        self.assertFalse(client.sock.last("ADMIN_UNLOCK_RESULT")["success"])
        self.server._on_admin_unlock_request(client, {"password": "s3cret"})
        self.assertTrue(client.sock.last("ADMIN_UNLOCK_RESULT")["success"])

    # ── maintenance ────────────────────────────────────────

    def test_force_close_stale_row(self):
        db.start_session("PC9", guest_name="Ghost", duration_mins=60, amount=60.0)
        result = self.server.force_close_session("PC9")
        self.assertTrue(result["ok"])
        self.assertIsNone(db.get_open_session("PC9"))

    def test_close_all_sessions_clears_clients(self):
        client = connect_pc(self.server, "PC1")
        self.server.start_session("PC1", "G", 60, 60.0)
        self.server.close_all_sessions("shutdown")
        self.assertIsNone(db.get_open_session("PC1"))
        self.assertIsNone(client.session_id)
        self.assertIn(CMD_STOP_SESSION, client.sock.types())


class TestBillingMath(unittest.TestCase):

    def test_charge_for_used_uses_the_booked_rate(self):
        session = {"duration_mins": 120, "amount_charged": 110.0}   # 2h pass Rs 110
        self.assertAlmostEqual(server_core.implied_rate(session), 55.0, places=2)
        self.assertAlmostEqual(server_core.charge_for_used(session, 3600), 55.0, places=2)
        # never charges more than the customer prepaid
        self.assertEqual(server_core.charge_for_used(session, 99999), 110.0)

    def test_charge_for_used_never_negative(self):
        session = {"duration_mins": 60, "amount_charged": 60.0}
        self.assertEqual(server_core.charge_for_used(session, -10), 0.0)


if __name__ == "__main__":
    unittest.main()
