# ============================================================
#  Support-module tests: exports, member import, receipt text,
#  game list and the client configuration file.
#
#  These run headless — no tkinter, no Windows — because the
#  printer/games/config layers are deliberately separated from the UI.
# ============================================================

import os
import unittest

from tests.base import DBTestCase, TMP_DIR
import database as db
import client_config
import games
import paths
from server import exporters, member_import, printer


# Key names match the real `sessions` table (SELECT *).
SESSION_ROWS = [
    {"id": 1, "pc_name": "PC-01", "member_id": None, "guest_name": "Ali Khan",
     "start_time": "2026-09-18T10:00:00", "end_time": "2026-09-18T11:30:00",
     "duration_mins": 90, "amount_charged": 90.0,
     "payment_type": "cash", "status": "completed"},
    {"id": 2, "pc_name": "PC-02", "member_id": None, "guest_name": None,
     "start_time": "2026-09-18T12:00:00", "end_time": "2026-09-18T12:45:00",
     "duration_mins": 45, "amount_charged": 45.0,
     "payment_type": "balance", "status": "completed"},
    {"id": 3, "pc_name": "PC-03", "member_id": 7, "member_name": "Sara",
     "start_time": "2026-09-18T13:00:00", "end_time": "2026-09-18T13:30:00",
     "duration_mins": 30, "amount_charged": 30.0,
     "payment_type": "balance", "status": "completed"},
]


# ── Exports (Phase 6E) ───────────────────────────────────────

class TestExporters(DBTestCase):

    def setUp(self):
        super().setUp()
        self.meta = exporters.default_meta("AZ Cafe", "Test", "2026-09-18",
                                           "Rs", SESSION_ROWS)

    def test_csv_has_bom_header_and_rows(self):
        path = os.path.join(TMP_DIR, "report.csv")
        exporters.export_csv(SESSION_ROWS, path, self.meta)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))     # Excel-friendly
        text = raw.decode("utf-8-sig")
        self.assertIn("Ali Khan", text)                       # guest name
        self.assertIn("Guest", text)                          # no name at all
        self.assertIn("Sara", text)                           # member name

    def test_xlsx_is_a_real_workbook(self):
        path = os.path.join(TMP_DIR, "report.xlsx")
        exporters.export_xlsx(SESSION_ROWS, path, self.meta)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"PK\x03\x04"))        # zip container
        self.assertIn(b"xl/worksheets/sheet1.xml", raw)
        self.assertIn(b"[Content_Types].xml", raw)

    def test_pdf_is_a_real_pdf(self):
        path = os.path.join(TMP_DIR, "report.pdf")
        exporters.export_pdf(SESSION_ROWS, path, self.meta)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", raw)
        self.assertIn(b"Page 1 / 1", raw)

    def test_meta_totals_and_names(self):
        self.assertEqual(self.meta["total"], 165.0)
        name = exporters.suggested_name("report", "2026-09-18", "csv")
        self.assertEqual(name, "azcafe_report_2026-09-18.csv")
        self.assertTrue(exporters.ensure_extension("x", "pdf").endswith(".pdf"))
        self.assertTrue(exporters.ensure_extension("x.PDF", "pdf").endswith(".PDF"))

    def test_member_id_falls_back_to_id_when_no_name(self):
        rows = exporters.session_rows([{"pc_name": "PC-09", "member_id": 4}])
        self.assertEqual(rows[0][1], "Member #4")

    def test_export_any_dispatch(self):
        path = os.path.join(TMP_DIR, "any.pdf")
        exporters.export_any("pdf", SESSION_ROWS, path, self.meta)
        self.assertTrue(os.path.exists(path))

    def test_long_report_paginates(self):
        many = [dict(SESSION_ROWS[0], id=i) for i in range(120)]
        path = os.path.join(TMP_DIR, "long.pdf")
        exporters.export_pdf(many, path, self.meta)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertIn(b"Page 1 / 2", raw)


# ── Member CSV import (Phase 6.5D) ───────────────────────────

class TestMemberImport(DBTestCase):

    def _write(self, name, text):
        path = os.path.join(TMP_DIR, name)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def test_simple_format_imports_members(self):
        path = self._write("simple.csv",
                           "name,username,password,balance\n"
                           "Ali Khan,ali,pass1,150\n"
                           "Sara,sara,pass2,0\n")
        report = member_import.import_csv(path)
        self.assertEqual(report["format"], "simple")
        self.assertEqual(report["added"], 2)
        member = db.get_member_by_username("ali")
        self.assertIsNotNone(member)
        self.assertEqual(member["balance"], 150)
        self.assertTrue(db.verify_password("pass1", member["password_hash"]))

    def test_dry_run_writes_nothing(self):
        path = self._write("simple.csv", "name,username,balance\nAli,ali,50\n")
        report = member_import.import_csv(path, dry_run=True)
        self.assertEqual(report["added"], 1)
        self.assertTrue(report["dry_run"])
        self.assertIsNone(db.get_member_by_username("ali"))

    def test_duplicate_rows_are_skipped_not_duplicated(self):
        path = self._write("simple.csv", "name,username,balance\nAli,ali,50\n")
        member_import.import_csv(path)
        again = member_import.import_csv(path)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["skipped"], 1)

    def test_ccp_export_junk_rows_are_filtered(self):
        """The dumped CCP file is contaminated with chat/agent text."""
        path = self._write("ccp.csv",
                           "Username,PWORD,ACCUMTIME,First name,Phone\n"
                           "realuser,ABCDEF123456,120,Real Person,03001112223\n"
                           "\"'\"\"\"\n"
                           "# We will save the CSV data provided by the user\n"
                           "'{\"step_index\":555',\n"
                           "Stdout:\n"
                           "Completed At: 2026-09-17T18:04:14+05:00\n")
        report = member_import.import_csv(path, dry_run=True)
        self.assertEqual(report["format"], "ccp")
        self.assertEqual(report["added"], 1)
        self.assertEqual(report["entries"][0]["username"], "realuser")
        self.assertEqual(report["temp_passwords"], 1)     # hash → temp password
        self.assertEqual(report["errors"], [])

    def test_unknown_format_reports_a_clear_error(self):
        path = self._write("bad.csv", "a,b,c\n1,2,3\n")
        report = member_import.import_csv(path)
        self.assertEqual(report["format"], "unknown")
        self.assertEqual(report["added"], 0)
        self.assertTrue(report["errors"])

    def test_imported_password_is_hashed(self):
        path = self._write("simple.csv", "name,username,password\nAli,ali,plain12\n")
        member_import.import_csv(path)
        stored = db.get_member_by_username("ali")["password_hash"]
        self.assertNotIn("plain12", stored)
        self.assertTrue(db.verify_password("plain12", stored))


# ── Receipt text (Phase 7B) ──────────────────────────────────

class TestReceiptText(unittest.TestCase):

    INFO = {"session_id": 12, "pc_name": "PC-01", "user": "Ali Khan",
            "payment_type": "cash", "started": "2026-09-18T10:00:00",
            "ended": "2026-09-18T11:30:00", "booked_mins": 120,
            "used_secs": 5400, "prepaid": 120, "charged": 90, "refund": 0}

    def test_receipt_fits_the_thermal_printer_width(self):
        text = printer.build_receipt_text(self.INFO, shop_name="AZ Cafe",
                                          currency="Rs")
        self.assertLessEqual(max(len(line) for line in text.splitlines()),
                             printer.WIDTH)
        for expected in ("AZ Cafe", "PC-01", "Ali Khan", "Rs 120", "Rs 90",
                         "1h 30m 00s"):
            self.assertIn(expected, text)

    def test_refund_line_only_when_refunded(self):
        info = dict(self.INFO, refund=30)
        text = printer.build_receipt_text(info)
        self.assertIn("Refunded", text)

    def test_save_receipt_writes_a_text_file(self):
        path = os.path.join(TMP_DIR, "receipt.txt")
        printer.save_receipt(self.INFO, path)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("SESSION RECEIPT", content)

    def test_non_windows_print_is_a_no_op(self):
        if os.name == "nt":                                    # pragma: no cover
            self.skipTest("Windows printing only")
        ok, message = printer.print_text("hello")
        self.assertFalse(ok)
        self.assertTrue(message)


# ── Game list (Phase 6.5C) ───────────────────────────────────

class TestGames(unittest.TestCase):

    def test_defaults_load_and_validate(self):
        games.reset_games()
        titles = games.load_games()
        self.assertGreaterEqual(len(titles), 5)
        for game in titles:
            self.assertIsNone(games.validate_game(game), game)

    def test_save_and_reload_roundtrip(self):
        my_games = [{"name": "Test Game", "cmd": "steam://rungameid/999",
                     "category": "Launcher", "icon": "🎮"}]
        games.save_games(my_games)
        self.assertEqual(games.load_games()[0]["name"], "Test Game")
        self.assertTrue(os.path.exists(games.games_path()))
        games.reset_games()

    def test_validate_rejects_missing_fields(self):
        self.assertIsNotNone(games.validate_game({"name": "", "cmd": "x"}))
        self.assertIsNotNone(games.validate_game({"name": "x", "cmd": ""}))

    def test_available_flags_match_availability(self):
        my_games = [{"name": "A", "cmd": "steam://rungameid/1", "category": "Launcher"},
                    {"name": "B", "cmd": r"C:\Nope\missing.exe", "category": "FPS"}]
        flags = games.available_flags(my_games)
        self.assertEqual(len(flags), 2)
        entries = dict((game["name"], available) for game, available in flags)
        self.assertTrue(entries["A"])             # steam:// is always launchable
        self.assertFalse(entries["B"])            # missing exe


# ── Client config (Phase 7C) ─────────────────────────────────

class TestClientConfig(unittest.TestCase):

    def setUp(self):
        self.path = client_config.client_config_path()
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as handle:
                self._saved = handle.read()
        else:
            self._saved = None
        os.environ.pop("AZCAFE_SERVER_IP", None)
        os.environ.pop("AZCAFE_SERVER_PORT", None)

    def tearDown(self):
        os.environ.pop("AZCAFE_SERVER_IP", None)
        os.environ.pop("AZCAFE_SERVER_PORT", None)
        if self._saved is None:
            if os.path.exists(self.path):
                os.remove(self.path)
        else:
            with open(self.path, "w", encoding="utf-8") as handle:
                handle.write(self._saved)

    def test_defaults_have_no_address(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        data = client_config.load_client_config()
        self.assertEqual(data["server_port"], client_config.DEFAULT_SERVER_PORT)
        self.assertTrue(data["pc_name"])
        self.assertFalse(client_config.is_configured())

    def test_save_and_load_roundtrip(self):
        client_config.save_client_config(server_ip="192.168.1.10",
                                         server_port=6000, pc_name="PC-07")
        data = client_config.load_client_config()
        self.assertEqual(data["server_ip"], "192.168.1.10")
        self.assertEqual(data["server_port"], 6000)
        self.assertEqual(data["pc_name"], "PC-07")
        self.assertTrue(client_config.is_configured())

    def test_environment_variable_wins(self):
        client_config.save_client_config(server_ip="192.168.1.10")
        os.environ["AZCAFE_SERVER_IP"] = "10.0.0.5"
        os.environ["AZCAFE_SERVER_PORT"] = "7000"
        data = client_config.load_client_config()
        self.assertEqual(data["server_ip"], "10.0.0.5")
        self.assertEqual(data["server_port"], 7000)

    def test_config_lives_in_the_data_folder(self):
        self.assertTrue(client_config.client_config_path()
                        .startswith(paths.data_dir()))


if __name__ == "__main__":
    unittest.main()
