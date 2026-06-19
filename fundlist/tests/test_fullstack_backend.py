import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


class DatabaseTests(unittest.TestCase):
    def test_upsert_and_get_fund_by_code(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            rows = [
                {
                    "market": "海外",
                    "fund_company": "測試投信",
                    "fund_id": "FLZ21",
                    "fund_name_main": "測試基金",
                    "base_code": "BASE123",
                    "can_sell": "*",
                    "fund_code": "0721",
                    "fund_name": "測試基金別名",
                }
            ]

            database.init_db(db_path)
            database.upsert_funds(rows, db_path)
            fund = database.get_fund_by_code("0721", db_path)

            self.assertEqual(fund["fund_code"], "0721")
            self.assertEqual(fund["fund_id"], "FLZ21")
            self.assertEqual(fund["market"], "海外")


class FetchNavTests(unittest.TestCase):
    def test_parse_bcd_nav_and_compute_changes(self):
        import fetch_nav

        rows = fetch_nav.parse_bcd_nav("20260617,20260618,20260619 10.00,10.50,10.25")
        with_changes = fetch_nav.compute_change_cols(rows)

        self.assertEqual(rows[0]["date"], date(2026, 6, 17))
        self.assertEqual(rows[1]["nav"], 10.5)
        self.assertIsNone(with_changes[0]["change"])
        self.assertEqual(with_changes[1]["change"], 0.5)
        self.assertAlmostEqual(with_changes[2]["change_percent"], -2.380952, places=5)

    def test_parse_bcd_nav_rejects_mismatched_lengths(self):
        import fetch_nav

        with self.assertRaisesRegex(ValueError, "日期/淨值筆數不一致"):
            fetch_nav.parse_bcd_nav("20260617,20260618 10.00")

    def test_fetch_nav_for_fund_returns_latest_date_first(self):
        import fetch_nav

        with patch.object(
            fetch_nav,
            "fetch_bcd_raw",
            return_value="20260617,20260618,20260619 10.00,10.50,10.25",
        ):
            rows = fetch_nav.fetch_nav_for_fund(
                fund_id="FLZ21",
                market="海外",
                today=date(2026, 6, 19),
            )

        self.assertEqual([row["date"] for row in rows], [
            date(2026, 6, 19),
            date(2026, 6, 18),
            date(2026, 6, 17),
        ])
        self.assertEqual(rows[0]["change"], -0.25)


class ApiTests(unittest.TestCase):
    def test_api_returns_nav_for_four_character_fund_code(self):
        import app
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        fund = {
            "market": "海外",
            "fund_company": "測試投信",
            "fund_id": "FLZ21",
            "fund_name_main": "測試基金",
            "base_code": "BASE123",
            "can_sell": "*",
            "fund_code": "0721",
            "fund_name": "",
        }
        nav_rows = [
            {
                "date": date(2026, 6, 19),
                "nav": 10.25,
                "change": -0.25,
                "change_percent": -2.380952380952381,
            }
        ]

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_nav, "fetch_nav_for_fund", return_value=nav_rows
        ):
            response = client.get("/api/funds/0721/nav")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["fund"]["fund_code"], "0721")
        self.assertEqual(payload["fund"]["fund_id"], "FLZ21")
        self.assertEqual(payload["nav"][0]["date"], "2026-06-19")
        self.assertEqual(payload["nav"][0]["nav"], 10.25)

    def test_api_returns_404_for_unknown_fund_code(self):
        import app
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        with patch.object(app.database, "get_fund_by_code", return_value=None):
            response = client.get("/api/funds/9999/nav")

        self.assertEqual(response.status_code, 404)

    def test_api_rejects_invalid_fund_code_format(self):
        import app
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        response = client.get("/api/funds/12345/nav")

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
