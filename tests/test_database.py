# ============================================================
#  Database layer tests: passwords, money, refunds, sessions,
#  groups, ledger, backups.
# ============================================================

import os
import unittest

from tests.base import DBTestCase, TMP_DIR
import database as db
import paths


class TestPasswords(DBTestCase):

    def test_scrypt_hash_roundtrip(self):
        stored = db.hash_password("s3cret")
        self.assertTrue(db.is_hashed(stored))
        self.assertTrue(db.verify_password("s3cret", stored))
        self.assertFalse(db.verify_password("wrong", stored))
        self.assertNotIn("s3cret", stored)

    def test_same_password_hashes_differently(self):
        self.assertNotEqual(db.hash_password("x"), db.hash_password("x"))

    def test_legacy_plaintext_admin_password_upgrades(self):
        db.set_setting("admin_password", "admin123")       # old databases
        self.assertTrue(db.verify_admin_password("admin123"))
        self.assertTrue(db.is_hashed(db.get_setting("admin_password")))
        self.assertFalse(db.verify_admin_password("admin1234"))

    def test_set_admin_password_is_salted(self):
        db.set_admin_password("newpass")
        raw = db.get_setting("admin_password")
        self.assertTrue(db.is_hashed(raw))
        self.assertNotIn("newpass", raw)
        self.assertTrue(db.verify_admin_password("newpass"))
        self.assertFalse(db.verify_admin_password("newpass "))


class TestMembers(DBTestCase):

    def test_create_and_login(self):
        db.create_member("Ali", "ali", "pw", balance=100)
        member = db.verify_member_login("ali", "pw")
        self.assertIsNotNone(member)
        self.assertEqual(member["name"], "Ali")
        self.assertIsNone(db.verify_member_login("ali", "nope"))

    def test_sha256_legacy_hash_is_accepted_and_upgraded(self):
        import hashlib
        conn = db.get_connection()
        conn.execute("INSERT INTO members (name, username, password_hash, balance)"
                     " VALUES ('Old','old',?,10)",
                     (hashlib.sha256(b"legacy").hexdigest(),))
        conn.commit()
        conn.close()
        member = db.verify_member_login("old", "legacy")
        self.assertIsNotNone(member)
        self.assertTrue(db.is_hashed(db.get_member_by_username("old")["password_hash"]))

    def test_topup_and_remove_write_ledger(self):
        member_id = db.create_member("Bilal", "bilal", "pw", balance=0)
        db.topup_member_balance(member_id, 500)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 500)
        db.remove_member_balance(member_id, 200)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 300)
        types = [t["type"] for t in db.get_cash_log()]
        self.assertIn("topup", types)
        self.assertIn("refund", types)

    def test_search_matches_name_username_phone(self):
        db.create_member("Hamza Khan", "hamza", "pw", phone="03001234567")
        self.assertEqual(len(db.search_members("hamza")), 1)
        self.assertEqual(len(db.search_members("Hamza")), 1)
        self.assertEqual(len(db.search_members("0300")), 1)
        self.assertEqual(len(db.search_members("zzz")), 0)


class TestSessionMoney(DBTestCase):
    """The money rules that used to leak cash."""

    def _member(self, balance=500.0):
        return db.create_member("Member", f"m{balance}", "pw", balance=balance)

    def test_start_session_deducts_wallet_and_logs(self):
        member_id = self._member(600)
        session_id = db.start_session("PC1", member_id=member_id, duration_mins=300,
                                      amount=300.0, payment_type="balance",
                                      deduct_balance=True)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 300)
        session = db.get_open_session("PC1")
        self.assertEqual(session["id"], session_id)
        self.assertEqual(session["remaining_secs"], 300 * 60)
        self.assertEqual(db.get_transaction_totals()["session_prepaid"]["total"], 300)

    def test_early_stop_refunds_unused_balance(self):
        member_id = self._member(60)                     # Rs 60 = 1 hour
        session_id = db.start_session("PC1", member_id=member_id, duration_mins=60,
                                      amount=60.0, payment_type="balance",
                                      deduct_balance=True)
        # 30 of 60 minutes used → charge Rs 30, refund Rs 30
        result = db.settle_session(session_id, actual_amount=30.0,
                                   refund_amount=30.0, refund_to_wallet=True,
                                   note="stopped early")
        self.assertEqual(result["charged"], 30.0)
        self.assertEqual(result["refund"], 30.0)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 30.0)
        self.assertEqual(db.get_member_by_id(member_id)["total_spent"], 30.0)
        types = db.get_transaction_totals()
        self.assertEqual(types["session_refund"]["total"], 30.0)
        self.assertEqual(types["session_charge"]["total"], 30.0)

    def test_cash_refund_is_recorded_but_does_not_touch_wallet(self):
        session_id = db.start_session("PC2", guest_name="Guest", duration_mins=60,
                                      amount=60.0, payment_type="cash")
        db.settle_session(session_id, actual_amount=20.0, refund_amount=40.0,
                          refund_to_wallet=False, note="cash handed back")
        types = db.get_transaction_totals()
        self.assertEqual(types["cash_refund"]["total"], -40.0)
        self.assertNotIn("session_refund", types)

    def test_extend_session_persists_and_logs(self):
        session_id = db.start_session("PC3", guest_name="G", duration_mins=60,
                                      amount=60.0, payment_type="cash")
        updated = db.extend_session(session_id, 30, 30.0)
        self.assertEqual(updated["duration_mins"], 90)
        self.assertEqual(updated["amount_charged"], 90.0)
        self.assertEqual(updated["remaining_secs"], 90 * 60)
        self.assertEqual(db.get_transaction_totals()["time_purchase"]["total"], 30.0)

    def test_extend_session_from_balance_deducts_wallet(self):
        member_id = self._member(100)
        session_id = db.start_session("PC4", member_id=member_id, duration_mins=60,
                                      amount=60.0, payment_type="balance",
                                      deduct_balance=True)
        db.extend_session(session_id, 30, 30.0, member_id=member_id,
                          payment_type="balance", deduct_balance=True)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 10.0)

    def test_revenue_counts_only_settled_sessions(self):
        db.start_session("PC5", guest_name="Running", duration_mins=60, amount=60.0)
        self.assertEqual(db.get_today_revenue(), 0.0)
        self.assertEqual(db.get_today_open_amount(), 60.0)
        session_id = db.start_session("PC6", guest_name="Done", duration_mins=60,
                                      amount=45.0)
        db.settle_session(session_id, actual_amount=45.0)
        self.assertEqual(db.get_today_revenue(), 45.0)
        totals = db.get_day_totals(db.get_sessions_by_date(
            __import__("datetime").datetime.now().strftime("%Y-%m-%d"))[0]["start_time"][:10])
        self.assertEqual(totals["revenue"], 45.0)
        self.assertEqual(totals["open_sessions"], 1)


class TestSessionRecovery(DBTestCase):

    def test_suspend_resume_and_sweep_keeps_cash(self):
        session_id = db.start_session("PC9", guest_name="G", duration_mins=60,
                                      amount=60.0, payment_type="cash")
        db.update_session_live(session_id, 1800, False)      # 30 min used
        db.suspend_session(session_id, 1800, False)
        session = db.get_open_session("PC9")
        self.assertEqual(session["status"], "suspended")

        db.set_setting("session_resume_grace", "0")
        settled = db.sweep_stale_sessions()
        self.assertEqual(len(settled), 1)
        row = db.get_sessions_by_date(
            __import__("datetime").datetime.now().strftime("%Y-%m-%d"))
        self.assertEqual(row[0]["status"], "completed")
        # Cash prepaid: the café keeps the money that was in the drawer
        self.assertEqual(row[0]["amount_charged"], 60.0)

    def test_sweep_refunds_unused_balance_to_member(self):
        member_id = db.create_member("M", "mm", "pw", balance=120)
        session_id = db.start_session("PC10", member_id=member_id, duration_mins=120,
                                      amount=120.0, payment_type="balance",
                                      deduct_balance=True)
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 0)
        db.update_session_live(session_id, 3600, False)      # only 60 min used
        db.suspend_session(session_id, 3600, False)
        db.set_setting("session_resume_grace", "0")
        db.sweep_stale_sessions()
        self.assertEqual(db.get_member_by_id(member_id)["balance"], 60.0)

    def test_hold_sessions_across_restart(self):
        db.start_session("PC11", guest_name="G", duration_mins=60, amount=60.0)
        self.assertEqual(db.hold_sessions_across_restart(), 1)
        self.assertEqual(db.get_open_session("PC11")["status"], "suspended")
        # Reconnecting within the grace window must still resume
        self.assertEqual(db.get_open_session("PC11")["status"], "suspended")

    def test_force_close(self):
        db.start_session("PC12", guest_name="G", duration_mins=30, amount=30.0)
        self.assertEqual(db.force_close_open_sessions("maintenance"), 1)
        self.assertIsNone(db.get_open_session("PC12"))


class TestGroupsAndPcs(DBTestCase):

    def test_group_rename_and_delete(self):
        db.save_pc("PC1")
        db.save_pc("PC2")
        db.update_pc_group("PC1", "VIP")
        db.update_pc_group("PC2", "VIP")
        self.assertIn("VIP", db.get_all_pc_groups())
        self.assertEqual(db.rename_pc_group("VIP", "Premium"), 2)
        self.assertIn("Premium", db.get_all_pc_groups())
        self.assertEqual(db.delete_pc_group("Premium"), 2)
        self.assertEqual([p["group_name"] for p in db.get_all_pcs()], ["Default", "Default"])

    def test_display_name_and_position_persist(self):
        db.save_pc("PC1")
        db.update_pc_display_name("PC1", "Corner PC")
        db.update_pc_position("PC1", 3, 2)
        pc = db.get_pc_by_name("PC1")
        self.assertEqual(pc["display_name"], "Corner PC")
        self.assertEqual((pc["grid_x"], pc["grid_y"]), (3, 2))


class TestMaintenance(DBTestCase):

    def test_backup_creates_usable_copy(self):
        db.create_member("A", "a", "pw", balance=10)
        dest = db.backup_db()
        self.assertTrue(os.path.exists(dest))
        import sqlite3
        conn = sqlite3.connect(dest)
        count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_db_info_points_at_data_dir(self):
        info = db.db_info()
        self.assertTrue(info["path"].startswith(TMP_DIR))
        self.assertEqual(info["counts"]["members"], 0)


class TestPaths(unittest.TestCase):

    def test_data_dir_honours_env_var(self):
        self.assertEqual(paths.data_dir(), os.path.abspath(TMP_DIR))

    def test_resource_path_returns_assets(self):
        self.assertTrue(paths.resource_path("assets", "logo.png").endswith("logo.png"))


if __name__ == "__main__":
    unittest.main()
