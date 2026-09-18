# ============================================================
#  End-to-end flow tests.
#
#  These drive the real server object (no sockets, no GUI) against a
#  throwaway SQLite database and assert on what the client and the
#  ledger actually receive — the checks that matter when money moves.
# ============================================================

import datetime as dt
import unittest

from tests.base import DBTestCase, connect_pc, make_server
import database as db
from protocol import (CMD_CONFIG, CMD_LOCK, CMD_START_SESSION, CMD_STOP_SESSION)


class FlowTestCase(DBTestCase):
    """A server plus the helpers every flow test needs."""

    def setUp(self):
        super().setUp()
        self.events = []
        self.server = make_server(
            on_status_msg=lambda msg: self.events.append(("status", msg)),
            on_session_event=lambda kind, payload: self.events.append(
                ("event", kind, payload)))

    # ── helpers ──────────────────────────────────────────────
    def start(self, pc, minutes, amount, payment_type="cash", **kwargs):
        kwargs.setdefault("user", "Walk-in")
        result = self.server.start_session(pc, duration_mins=minutes, amount=amount,
                                           payment_type=payment_type, **kwargs)
        self.assertTrue(result.get("ok"), result)
        return result

    def settle_payload(self):
        payloads = [e[2] for e in self.events if e[0] == "event" and e[1] == "settled"]
        self.assertTrue(payloads, f"no settle event fired: {self.events}")
        return payloads[-1]

    def ledger(self, tx_type):
        return [t for t in db.get_cash_log() if t["type"] == tx_type]


class TestSessionFlows(FlowTestCase):

    def test_register_pushes_config_to_the_client(self):
        client = connect_pc(self.server, "PC-01")
        config = client.sock.last(CMD_CONFIG)
        self.assertIsNotNone(config)
        self.assertGreaterEqual(len(config["games"]), 5)
        for key in ("kiosk_mode", "auto_lock", "sound_enabled", "low_time_warning",
                    "receipt_printer", "shop_name"):
            self.assertIn(key, config)

    def test_cash_self_end_charges_only_time_used(self):
        client = connect_pc(self.server, "PC-01")
        self.start("PC-01", 60, 60)
        client.remaining_secs = 45 * 60                      # played 15 minutes
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})

        payload = self.settle_payload()
        self.assertEqual(payload["charged"], 15.0)
        self.assertEqual(payload["refund"], 45.0)
        self.assertEqual(payload["used_secs"], 900)

    def test_self_end_tells_the_pc_to_stop_and_lock(self):
        client = connect_pc(self.server, "PC-01")
        self.start("PC-01", 60, 60)
        client.remaining_secs = 45 * 60
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})
        self.assertIn(CMD_STOP_SESSION, client.sock.types())
        self.assertIn(CMD_LOCK, client.sock.types())

    def test_unused_cash_is_recorded_as_money_owed_back(self):
        client = connect_pc(self.server, "PC-01")
        self.start("PC-01", 60, 60)
        client.remaining_secs = 45 * 60
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})
        owed = self.ledger("cash_refund")
        self.assertEqual(len(owed), 1)
        self.assertEqual(owed[0]["amount"], -45.0)

    def test_balance_session_refund_returns_to_the_wallet(self):
        member_id = db.create_member("Ali Khan", "ali", "pw123456", 200.0)
        client = connect_pc(self.server, "PC-02")
        self.start("PC-02", 60, 60, payment_type="balance", member_id=member_id,
                   user="Ali Khan")
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 140.0)  # charged

        client.remaining_secs = 30 * 60                      # played half
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})

        self.assertEqual(db.get_member_by_id(member_id)["balance"], 170.0)  # +30 back
        refunds = self.ledger("session_refund")
        self.assertEqual(refunds[0]["amount"], 30.0)
        self.assertFalse(self.ledger("cash_refund"))         # no cash involved

    def test_expiry_settles_at_full_price_and_locks(self):
        client = connect_pc(self.server, "PC-03")
        self.start("PC-03", 30, 30)
        client.remaining_secs = 0
        self.server._tick()
        payload = self.settle_payload()
        self.assertEqual(payload["charged"], 30.0)
        self.assertEqual(payload["refund"], 0.0)
        self.assertIn(CMD_LOCK, client.sock.types())


class TestDisconnectAndRecovery(FlowTestCase):

    def test_disconnect_suspends_and_reconnect_resumes(self):
        client = connect_pc(self.server, "PC-04")
        self.start("PC-04", 60, 60, user="Sara")
        client.remaining_secs = 20 * 60
        self.server._remove_client(client, "connection lost")

        held = db.get_open_session("PC-04")
        self.assertEqual(held["status"], "suspended")
        self.assertEqual(held["remaining_secs"], 20 * 60)

        resumed = connect_pc(self.server, "PC-04")
        start_msg = resumed.sock.last(CMD_START_SESSION)
        self.assertIsNotNone(start_msg)
        self.assertTrue(start_msg["resumed"])
        self.assertEqual(start_msg["duration_secs"], 20 * 60)
        self.assertEqual(db.get_open_session("PC-04")["status"], "active")

    def test_stale_session_is_swept_and_keeps_the_prepaid_cash(self):
        client = connect_pc(self.server, "PC-05")
        self.start("PC-05", 60, 60)
        self.server._remove_client(client, "connection lost")

        stale = db.get_open_session("PC-05")
        conn = db.get_connection()
        conn.execute("UPDATE sessions SET suspended_at=? WHERE id=?",
                     ((dt.datetime.now() - dt.timedelta(hours=3)).isoformat(
                         timespec="seconds"), stale["id"]))
        conn.commit()
        conn.close()

        settled = db.sweep_stale_sessions(grace_mins=60)
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["session"]["charged"], 60.0)   # café keeps it
        self.assertEqual(settled[0]["session"]["refund"], 0.0)
        self.assertIsNone(db.get_open_session("PC-05"))

    def test_live_session_is_not_swept(self):
        client = connect_pc(self.server, "PC-06")
        self.start("PC-06", 60, 60)
        self.assertEqual(db.sweep_stale_sessions(grace_mins=0), [])
        self.assertIsNotNone(db.get_open_session("PC-06"))
        self.assertIsNotNone(client.session_id)


class TestAdminActions(FlowTestCase):

    def test_admin_stop_charges_used_time_and_returns_the_rest(self):
        client = connect_pc(self.server, "PC-07")
        self.start("PC-07", 60, 60)
        client.remaining_secs = 40 * 60                      # 20 min played

        stopped = self.server.stop_session("PC-07")
        self.assertEqual(stopped["charged"], 20.0)
        self.assertEqual(stopped["refund"], 40.0)
        self.assertIn(CMD_STOP_SESSION, client.sock.types())
        self.assertIsNone(db.get_open_session("PC-07"))

    def test_force_close_keeps_prepaid_when_the_pc_never_came_back(self):
        client = connect_pc(self.server, "PC-08")
        self.start("PC-08", 60, 60)
        self.server._remove_client(client, "connection lost")     # PC vanished

        forced = self.server.force_close_session("PC-08")         # keep_prepaid default
        self.assertTrue(forced.get("ok"))
        self.assertEqual(forced["charged"], 60.0)
        self.assertEqual(forced["refund"], 0.0)
        self.assertIsNone(db.get_open_session("PC-08"))

    def test_add_time_persists_charges_and_notifies_the_pc(self):
        client = connect_pc(self.server, "PC-09")
        self.start("PC-09", 30, 30)
        before = client.remaining_secs

        result = self.server.add_time("PC-09", 30, amount=30, payment_type="cash")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(db.get_open_session("PC-09")["duration_mins"], 60)
        self.assertEqual(client.remaining_secs, before + 30 * 60)
        self.assertTrue(client.sock.last("TIME_UPDATE"))
        purchases = self.ledger("time_purchase")
        self.assertEqual(purchases[0]["amount"], 30.0)

    def test_double_start_is_refused(self):
        connect_pc(self.server, "PC-10")
        first = self.server.start_session("PC-10", "Guest", duration_mins=30, amount=30)
        self.assertTrue(first.get("ok"), first)
        second = self.server.start_session("PC-10", "Guest", duration_mins=30, amount=30)
        self.assertFalse(second.get("ok"))
        self.assertEqual(len(db.get_open_sessions_all()), 1)

    def test_start_refuses_a_balance_session_without_enough_credit(self):
        member_id = db.create_member("Poor", "poor", "pw123456", 10.0)
        connect_pc(self.server, "PC-11")
        refused = self.server.start_session("PC-11", "Poor", duration_mins=60, amount=100,
                                            payment_type="balance", member_id=member_id)
        self.assertFalse(refused.get("ok"), refused)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 10.0)

    def test_close_all_sessions_clears_the_books(self):
        connect_pc(self.server, "PC-12")
        connect_pc(self.server, "PC-13")
        self.start("PC-12", 60, 60)
        self.start("PC-13", 60, 60)
        closed = self.server.close_all_sessions()
        self.assertEqual(closed, 2)
        self.assertEqual(db.get_open_sessions_all(), [])


class TestMoneySummary(FlowTestCase):

    def test_day_totals_separate_completed_revenue_from_open_tabs(self):
        client = connect_pc(self.server, "PC-14")
        self.start("PC-14", 60, 60)
        client.remaining_secs = 45 * 60
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})

        open_client = connect_pc(self.server, "PC-15")
        self.start("PC-15", 60, 180)                          # still running

        totals = db.get_day_totals(dt.date.today().isoformat())
        self.assertEqual(totals["revenue"], 15.0)             # only what was charged
        self.assertEqual(totals["open_amount"], 180.0)        # running tab shown apart
        self.assertEqual(totals["completed_sessions"], 1)
        self.assertEqual(totals["open_sessions"], 1)
        self.assertTrue(open_client.session_id)

    def test_receipt_renders_from_the_real_settle_payload(self):
        from server import printer
        client = connect_pc(self.server, "PC-16")
        self.start("PC-16", 60, 60, user="Walk-in")
        client.remaining_secs = 45 * 60
        self.server._dispatch(client, {"type": "SESSION_ENDED", "data": {}})

        payload = self.settle_payload()
        for key in ("session_id", "pc_name", "user", "payment_type", "booked_mins",
                    "used_secs", "prepaid", "charged", "refund", "balance_left"):
            self.assertIn(key, payload)
        text = printer.build_receipt_text(payload, shop_name="AZ Cafe", currency="Rs")
        self.assertIn("SESSION RECEIPT", text)
        self.assertLessEqual(max(len(line) for line in text.splitlines()),
                             printer.WIDTH)


if __name__ == "__main__":
    unittest.main()
