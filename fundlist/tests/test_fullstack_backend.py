import tempfile
import unittest
from datetime import date
from importlib import reload
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

    def test_save_and_get_latest_fund_list_update_status(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.save_fund_list_update_status(
                status="succeeded",
                message="基金清單更新完成",
                started_at="2026-06-20T04:14:56+00:00",
                finished_at="2026-06-20T04:21:38+00:00",
                db_path=db_path,
            )

            result = database.get_latest_fund_list_update_status(db_path)

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["message"], "基金清單更新完成")
            self.assertEqual(result["started_at"], "2026-06-20T04:14:56+00:00")
            self.assertEqual(result["finished_at"], "2026-06-20T04:21:38+00:00")


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
    def load_app(self):
        import app

        loaded_app = reload(app)
        loaded_app.fund_list_update_status.update(loaded_app.DEFAULT_FUND_LIST_UPDATE_STATUS)
        return loaded_app

    def test_api_returns_nav_for_four_character_fund_code(self):
        app = self.load_app()
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
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        with patch.object(app.database, "get_fund_by_code", return_value=None):
            response = client.get("/api/funds/9999/nav")

        self.assertEqual(response.status_code, 404)

    def test_api_rejects_invalid_fund_code_format(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        response = client.get("/api/funds/12345/nav")

        self.assertEqual(response.status_code, 400)

    def test_api_starts_fund_list_update_and_reports_success(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        with patch.object(app.fund_list_updater, "main", return_value=None), patch.object(
            app.database, "save_fund_list_update_status"
        ) as save_status:
            response = client.post("/api/fund-list/update")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "running")

        status_response = client.get("/api/fund-list/update-status")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["message"], "基金清單更新完成")
        self.assertIsNotNone(payload["started_at"])
        self.assertIsNotNone(payload["finished_at"])
        self.assertEqual(save_status.call_count, 2)
        self.assertEqual(save_status.call_args_list[-1].kwargs["status"], "succeeded")

    def test_api_rejects_duplicate_fund_list_update_while_running(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        app.fund_list_update_status["status"] = "running"
        client = TestClient(app.app)
        response = client.post("/api/fund-list/update")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "基金清單更新已在執行中")

    def test_api_reports_failed_fund_list_update(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        with patch.object(app.fund_list_updater, "main", side_effect=RuntimeError("boom")), patch.object(
            app.database, "save_fund_list_update_status"
        ) as save_status:
            response = client.post("/api/fund-list/update")

        self.assertEqual(response.status_code, 202)

        status_response = client.get("/api/fund-list/update-status")
        payload = status_response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertIn("boom", payload["message"])
        self.assertIsNotNone(payload["finished_at"])
        self.assertEqual(save_status.call_count, 2)
        self.assertEqual(save_status.call_args_list[-1].kwargs["status"], "failed")

    def test_api_loads_last_fund_list_update_status_from_database_after_reload(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        saved = {
            "status": "succeeded",
            "message": "基金清單更新完成",
            "started_at": "2026-06-20T04:14:56+00:00",
            "finished_at": "2026-06-20T04:21:38+00:00",
        }
        with patch.object(app.database, "get_latest_fund_list_update_status", return_value=saved):
            app = reload(app)
            client = TestClient(app.app)
            response = client.get("/api/fund-list/update-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), saved)


if __name__ == "__main__":
    unittest.main()
