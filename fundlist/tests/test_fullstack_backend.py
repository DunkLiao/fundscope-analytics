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

    def test_investment_settings_crud_joins_fund_names(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "國內",
                        "fund_company": "測試投信",
                        "fund_id": "ABCD1",
                        "fund_name_main": "測試一號基金",
                        "base_code": "BASE1",
                        "can_sell": "*",
                        "fund_code": "1111",
                        "fund_name": "",
                    },
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "ABCD2",
                        "fund_name_main": "",
                        "base_code": "BASE2",
                        "can_sell": "*",
                        "fund_code": "2222",
                        "fund_name": "測試二號別名",
                    },
                ],
                db_path,
            )

            created = database.create_investment_setting("holdings", "1111", 120000, db_path)
            self.assertEqual(created["fund_code"], "1111")
            self.assertEqual(created["fund_name"], "測試一號基金")
            self.assertEqual(created["amount"], 120000)

            updated = database.update_investment_setting("holdings", created["id"], "2222", 250000, db_path)
            self.assertEqual(updated["fund_code"], "2222")
            self.assertEqual(updated["fund_name"], "測試二號別名")
            self.assertEqual(updated["amount"], 250000)

            rows = database.list_investment_settings("holdings", db_path)
            self.assertEqual([row["id"] for row in rows], [created["id"]])
            self.assertEqual(rows[0]["fund_code"], "2222")

            self.assertTrue(database.delete_investment_setting("holdings", created["id"], db_path))
            self.assertEqual(database.list_investment_settings("holdings", db_path), [])

    def test_investment_settings_reject_unknown_type_duplicate_fund_and_bad_amount(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "國內",
                        "fund_company": "測試投信",
                        "fund_id": "ABCD1",
                        "fund_name_main": "測試一號基金",
                        "base_code": "BASE1",
                        "can_sell": "*",
                        "fund_code": "1111",
                        "fund_name": "",
                    }
                ],
                db_path,
            )

            database.create_investment_setting("recurring", "1111", 3000, db_path)

            with self.assertRaisesRegex(ValueError, "未知的投資設定類型"):
                database.list_investment_settings("bad-type", db_path)
            with self.assertRaisesRegex(ValueError, "投資金額必須是大於 0 的整數"):
                database.create_investment_setting("recurring", "1111", 0, db_path)
            with self.assertRaisesRegex(ValueError, "基金代號已存在"):
                database.create_investment_setting("recurring", "1111", 5000, db_path)
            with self.assertRaisesRegex(ValueError, "找不到此基金代號"):
                database.create_investment_setting("lump-sum", "9999", 5000, db_path)


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


class BatchFileTests(unittest.TestCase):
    def test_start_website_stops_existing_service_before_starting(self):
        script_path = Path(__file__).resolve().parents[2] / "start_website.bat"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("OwningProcess", script)
        self.assertIn("Stop-Process", script)
        self.assertIn("Existing service on port %PORT% was stopped.", script)
        self.assertNotIn("Website is already running", script)


class StaticLayoutTests(unittest.TestCase):
    def test_mobile_navigation_stacks_without_absolute_dropdowns(self):
        css_path = Path(__file__).resolve().parents[1] / "static" / "styles.css"
        css = css_path.read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 640px)", css)
        self.assertIn("flex-direction: column;", css)
        self.assertIn(".menu-list {\n    position: static;", css)
        self.assertIn(".nav-menu[open] .menu-list", css)
        self.assertIn("h1,\nh2,\nh3,\np {", css)
        self.assertIn("line-break: anywhere;", css)
        self.assertIn("overflow-wrap: anywhere;", css)
        self.assertIn("word-break: break-word;", css)
        self.assertIn("word-break: break-all;", css)

    def test_investment_tables_use_mobile_card_layout(self):
        static_dir = Path(__file__).resolve().parents[1] / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")

        self.assertEqual(html.count('class="investment-table"'), 3)
        self.assertIn(".investment-table thead", css)
        self.assertIn(".investment-table tbody", css)
        self.assertIn(".investment-table td::before", css)
        self.assertIn(".investment-table td:nth-child(4)", css)
        self.assertIn(".investment-table .table-actions", css)


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

    def test_api_returns_fund_profile_for_four_character_fund_code(self):
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

        with patch.object(app.database, "get_fund_by_code", return_value=fund):
            response = client.get("/api/funds/0721")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["fund_code"], "0721")
        self.assertEqual(payload["fund_name_main"], "測試基金")

    def test_api_crud_investment_settings(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        created = {
            "id": 1,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 120000,
            "created_at": "2026-06-20T04:00:00+00:00",
            "updated_at": "2026-06-20T04:00:00+00:00",
        }
        updated = dict(created, amount=150000)

        with patch.object(app.database, "get_fund_by_code", return_value={"fund_code": "0721"}), patch.object(
            app.database, "create_investment_setting", return_value=created
        ) as create_setting, patch.object(
            app.database, "list_investment_settings", side_effect=[[created], []]
        ) as list_settings, patch.object(
            app.database, "update_investment_setting", return_value=updated
        ) as update_setting, patch.object(
            app.database, "delete_investment_setting", return_value=True
        ) as delete_setting:
            create_response = client.post(
                "/api/investment-settings/holdings",
                json={"fund_code": "0721", "amount": 120000},
            )
            list_response = client.get("/api/investment-settings/holdings")
            update_response = client.put(
                "/api/investment-settings/holdings/1",
                json={"fund_code": "0721", "amount": 150000},
            )
            delete_response = client.delete("/api/investment-settings/holdings/1")
            empty_response = client.get("/api/investment-settings/holdings")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["amount"], 120000)
        self.assertEqual(list_response.json(), [created])
        self.assertEqual(update_response.json()["amount"], 150000)
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(empty_response.json(), [])
        create_setting.assert_called_once_with("holdings", "0721", 120000)
        update_setting.assert_called_once_with("holdings", 1, "0721", 150000)
        delete_setting.assert_called_once_with("holdings", 1)
        self.assertEqual(list_settings.call_count, 2)

    def test_api_rejects_invalid_investment_setting_payload(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)

        response = client.post(
            "/api/investment-settings/holdings",
            json={"fund_code": "0721", "amount": 0},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "投資金額必須是大於 0 的整數")

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
