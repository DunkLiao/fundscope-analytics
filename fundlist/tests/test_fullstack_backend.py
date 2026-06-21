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

    def test_fund_prices_upsert_and_lookup_uses_latest_price_on_or_before_date(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "FLZ21",
                        "fund_name_main": "測試基金",
                        "base_code": "BASE123",
                        "can_sell": "*",
                        "fund_code": "0721",
                        "fund_name": "",
                    }
                ],
                db_path,
            )
            database.upsert_fund_prices(
                "0721",
                [
                    {"date": date(2026, 6, 18), "nav": 10.5, "change": 0.5, "change_percent": 5.0},
                    {"date": date(2026, 6, 19), "nav": 10.25, "change": -0.25, "change_percent": -2.38},
                ],
                db_path=db_path,
            )

            exact = database.get_fund_price_on_or_before("0721", date(2026, 6, 19), db_path)
            fallback = database.get_fund_price_on_or_before("0721", date(2026, 6, 21), db_path)
            missing = database.get_fund_price_on_or_before("0721", date(2026, 6, 17), db_path)

            self.assertEqual(exact["price_date"], "2026-06-19")
            self.assertEqual(fallback["price_date"], "2026-06-19")
            self.assertIsNone(missing)

    def test_create_lump_sum_transaction_uses_fallback_nav_and_calculates_units(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "FLZ21",
                        "fund_name_main": "測試基金",
                        "base_code": "BASE123",
                        "can_sell": "*",
                        "fund_code": "0721",
                        "fund_name": "",
                    }
                ],
                db_path,
            )
            database.upsert_fund_prices(
                "0721",
                [{"date": date(2026, 6, 19), "nav": 10.25, "change": None, "change_percent": None}],
                db_path=db_path,
            )

            created = database.create_investment_transaction(
                "lump-sum",
                "0721",
                trade_date=date(2026, 6, 21),
                amount=10250,
                db_path=db_path,
                today=date(2026, 6, 21),
            )

            self.assertEqual(created["investment_type"], "lump-sum")
            self.assertEqual(created["trade_date"], "2026-06-21")
            self.assertEqual(created["nav_date"], "2026-06-19")
            self.assertEqual(created["nav"], 10.25)
            self.assertAlmostEqual(created["units"], 1000.0)

    def test_create_holding_transaction_saves_user_units_and_rejects_future_date(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "FLZ21",
                        "fund_name_main": "測試基金",
                        "base_code": "BASE123",
                        "can_sell": "*",
                        "fund_code": "0721",
                        "fund_name": "",
                    }
                ],
                db_path,
            )
            database.upsert_fund_prices(
                "0721",
                [{"date": date(2026, 6, 19), "nav": 10.25, "change": None, "change_percent": None}],
                db_path=db_path,
            )

            created = database.create_investment_transaction(
                "holdings",
                "0721",
                trade_date=date(2026, 6, 20),
                amount=120000,
                units=9876.5432,
                db_path=db_path,
                today=date(2026, 6, 21),
            )

            self.assertEqual(created["units"], 9876.5432)
            with self.assertRaisesRegex(ValueError, "不可晚於今天"):
                database.create_investment_transaction(
                    "holdings",
                    "0721",
                    trade_date=date(2026, 6, 22),
                    amount=120000,
                    units=9876.5432,
                    db_path=db_path,
                    today=date(2026, 6, 21),
                )

    def test_recurring_plan_supports_multiple_days_and_generates_transactions_once(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "FLZ21",
                        "fund_name_main": "測試基金",
                        "base_code": "BASE123",
                        "can_sell": "*",
                        "fund_code": "0721",
                        "fund_name": "",
                    }
                ],
                db_path,
            )
            database.upsert_fund_prices(
                "0721",
                [
                    {"date": date(2026, 6, 6), "nav": 10.0, "change": None, "change_percent": None},
                    {"date": date(2026, 6, 16), "nav": 10.5, "change": None, "change_percent": None},
                ],
                db_path=db_path,
            )
            plan = database.create_recurring_investment_plan(
                "0721",
                amount=3000,
                start_date=date(2026, 6, 1),
                end_date=None,
                days=[6, 16, 26],
                db_path=db_path,
            )

            first_run = database.generate_recurring_transactions(plan["id"], db_path=db_path, today=date(2026, 6, 21))
            second_run = database.generate_recurring_transactions(plan["id"], db_path=db_path, today=date(2026, 6, 21))

            self.assertEqual(plan["days"], [6, 16, 26])
            self.assertEqual([row["trade_date"] for row in first_run], ["2026-06-06", "2026-06-16"])
            self.assertEqual(second_run, [])
            self.assertEqual(len(database.list_investment_transactions("recurring", db_path)), 2)

    def test_recurring_plan_update_and_delete_keep_crud_available(self):
        import database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "funddata.db"
            database.upsert_funds(
                [
                    {
                        "market": "海外",
                        "fund_company": "測試投信",
                        "fund_id": "FLZ21",
                        "fund_name_main": "測試基金",
                        "base_code": "BASE123",
                        "can_sell": "*",
                        "fund_code": "0721",
                        "fund_name": "",
                    }
                ],
                db_path,
            )
            plan = database.create_recurring_investment_plan(
                "0721",
                amount=3000,
                start_date=date(2026, 6, 1),
                end_date=None,
                days=[6, 16],
                db_path=db_path,
            )

            updated = database.update_recurring_investment_plan(
                plan["id"],
                "0721",
                amount=5000,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 12, 31),
                days=[5, 15, 25],
                db_path=db_path,
            )

            self.assertEqual(updated["amount"], 5000)
            self.assertEqual(updated["start_date"], "2026-07-01")
            self.assertEqual(updated["end_date"], "2026-12-31")
            self.assertEqual(updated["days"], [5, 15, 25])
            self.assertTrue(database.delete_recurring_investment_plan(plan["id"], db_path))
            self.assertEqual(database.list_recurring_investment_plans(db_path), [])


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


class FetchPerformanceTests(unittest.TestCase):
    DOMESTIC_HTML = """
    <html><body>
      <table>
        <tr>
          <td class="wfb8c">基金</td>
          <td class="wfb8c">淨值</td>
          <td class="wfb8c">淨值日期</td>
          <td class="wfb8c" colspan="2">自今年以來報酬率(%)</td>
          <td class="wfb8c">年化<br>標準差(%)</td>
          <td class="wfb8c">Sharpe</td>
          <td class="wfb8c"><span>b</span></td>
        </tr>
        <tr>
          <td class="wfb2l">中國信託高評級策略收益債券基金-B分配型(台幣)</td>
          <td class="wfb2r">9.4905</td>
          <td class="wfb2c">2026/06/17</td>
          <td class="wfb2rR" colspan="2">1.31</td>
          <td class="wfb2rR">5.16</td>
          <td class="wfb2rR">0.49</td>
          <td class="wfb2rR">1.38</td>
        </tr>
      </table>
      <table>
        <tr>
          <td rowspan="2" class="wfb8c">基金名稱</td>
          <td colspan="7" class="wfb8c">累積報酬率(%)</td>
        </tr>
        <tr>
          <td class="wfb8c">一個月</td>
          <td class="wfb8c">三個月</td>
          <td class="wfb8c">六個月</td>
          <td class="wfb8c">一年</td>
          <td class="wfb8c">二年</td>
          <td class="wfb8c">三年</td>
          <td class="wfb8c">五年</td>
        </tr>
        <tr>
          <td class="wfb2l">中國信託高評級策略收益債券基金-B分配型(台幣)</td>
          <td class="wfb2rR">1.93</td>
          <td class="wfb2rR">1.12</td>
          <td class="wfb2rR">1.41</td>
          <td class="wfb2rR">10.28</td>
          <td class="wfb2rR">4.44</td>
          <td class="wfb2r">N/A</td>
          <td class="wfb2r">N/A</td>
        </tr>
      </table>
    </body></html>
    """

    OVERSEAS_HTML = """
    <html><body>
      <table>
        <tr>
          <td class="wfb8c">基金</td>
          <td class="wfb8c">淨值</td>
          <td class="wfb8c">淨值日期</td>
          <td class="wfb8c">自今年以來<br>報酬率(%)</td>
          <td class="wfb8c">年化<br>標準差(%)</td>
          <td class="wfb8c">Sharpe</td>
          <td class="wfb8c"><span>b</span></td>
        </tr>
        <tr>
          <td class="wfb2l">聯博-全球非投資等級債券AT級別美元</td>
          <td class="wfb2r">3.0900</td>
          <td class="wfb2c">2026/06/18</td>
          <td class="wfb2rR">1.78</td>
          <td class="wfb2rR">3.88</td>
          <td class="wfb2rR">0.38</td>
          <td class="wfb2rR">1.07</td>
        </tr>
      </table>
      <table>
        <tr>
          <td rowspan="2" class="wfb8c">基金名稱</td>
          <td colspan="11" class="wfb8c">累積報酬率(%)</td>
        </tr>
        <tr>
          <td class="wfb8c">一週</td>
          <td class="wfb8c">一個月</td>
          <td class="wfb8c">本月</td>
          <td class="wfb8c">本季</td>
          <td class="wfb8c">三個月</td>
          <td class="wfb8c">六個月</td>
          <td class="wfb8c">九個月</td>
          <td class="wfb8c">一年</td>
          <td class="wfb8c">二年</td>
          <td class="wfb8c">三年</td>
          <td class="wfb8c">五年</td>
        </tr>
        <tr>
          <td class="wfb2l">聯博-全球非投資等級債券AT級別美元</td>
          <td class="wfb2rR">0.32</td>
          <td class="wfb2rR">1.27</td>
          <td class="wfb2rR">0.32</td>
          <td class="wfb2rR">2.90</td>
          <td class="wfb2rR">2.53</td>
          <td class="wfb2rR">2.07</td>
          <td class="wfb2rR">2.62</td>
          <td class="wfb2rR">6.49</td>
          <td class="wfb2rR">14.46</td>
          <td class="wfb2rR">26.49</td>
          <td class="wfb2rR">16.26</td>
        </tr>
      </table>
    </body></html>
    """

    def test_parse_domestic_performance_tables(self):
        import fetch_performance

        result = fetch_performance.parse_performance_html(self.DOMESTIC_HTML)

        self.assertEqual(result["summary"]["fund_name"], "中國信託高評級策略收益債券基金-B分配型(台幣)")
        self.assertEqual(result["summary"]["nav"], 9.4905)
        self.assertEqual(result["summary"]["nav_date"], "2026/06/17")
        self.assertEqual(result["summary"]["year_to_date_return_percent"], 1.31)
        self.assertEqual(result["summary"]["annualized_standard_deviation_percent"], 5.16)
        self.assertEqual(result["summary"]["sharpe"], 0.49)
        self.assertEqual(result["summary"]["beta"], 1.38)
        self.assertEqual(
            result["cumulative_returns"],
            [
                {"period": "一個月", "return_percent": 1.93},
                {"period": "三個月", "return_percent": 1.12},
                {"period": "六個月", "return_percent": 1.41},
                {"period": "一年", "return_percent": 10.28},
                {"period": "二年", "return_percent": 4.44},
                {"period": "三年", "return_percent": None},
                {"period": "五年", "return_percent": None},
            ],
        )

    def test_parse_overseas_performance_tables_with_short_term_periods(self):
        import fetch_performance

        result = fetch_performance.parse_performance_html(self.OVERSEAS_HTML)

        self.assertEqual(result["summary"]["fund_name"], "聯博-全球非投資等級債券AT級別美元")
        self.assertEqual(result["summary"]["nav"], 3.09)
        self.assertEqual(result["summary"]["nav_date"], "2026/06/18")
        self.assertEqual(result["cumulative_returns"][0], {"period": "一週", "return_percent": 0.32})
        self.assertEqual(result["cumulative_returns"][3], {"period": "本季", "return_percent": 2.9})
        self.assertEqual(result["cumulative_returns"][-1], {"period": "五年", "return_percent": 16.26})

    def test_parse_skips_outer_rows_from_nested_source_tables(self):
        import fetch_performance

        nested_html = f"""
        <html><body>
          <table>
            <tr>
              <td>
                {self.DOMESTIC_HTML}
              </td>
            </tr>
          </table>
        </body></html>
        """

        result = fetch_performance.parse_performance_html(nested_html)

        self.assertEqual(result["summary"]["nav"], 9.4905)
        self.assertEqual(result["cumulative_returns"][3], {"period": "一年", "return_percent": 10.28})

    def test_fetch_performance_for_fund_uses_market_specific_url(self):
        import fetch_performance

        with patch.object(fetch_performance, "fetch_performance_html", return_value=self.OVERSEAS_HTML) as fetch_html:
            result = fetch_performance.fetch_performance_for_fund(
                fund_id="ALZ60",
                fund_code="0922",
                market="海外",
            )

        fetch_html.assert_called_once_with(
            "https://fund.bot.com.tw/w/wb/wb03a.djhtm?a=ALZ60-0922",
            timeout=fetch_performance.TIMEOUT,
        )
        self.assertEqual(result["source_url"], "https://fund.bot.com.tw/w/wb/wb03a.djhtm?a=ALZ60-0922")
        self.assertEqual(result["summary"]["nav"], 3.09)


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

    def test_static_layout_includes_fund_performance_query_view(self):
        static_dir = Path(__file__).resolve().parents[1] / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-view="performance-query"', html)
        self.assertIn('data-view-panel="performance-query"', html)
        self.assertIn("基金績效查詢", html)
        self.assertIn("/performance", js)
        self.assertIn("performance-summary-body", html)
        self.assertIn("performance-returns-head", html)
        self.assertIn("performance-returns-body", html)

    def test_static_layout_uses_transaction_and_recurring_plan_forms(self):
        static_dir = Path(__file__).resolve().parents[1] / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn("基準日期", html)
        self.assertIn("現有單位數", html)
        self.assertIn("每月扣款日", html)
        self.assertIn("產生已到期交易", html)
        self.assertIn("使用淨值日期", html)
        self.assertIn("/api/investments/", js)
        self.assertIn("/transactions", js)
        self.assertIn("/plans", js)
        self.assertIn('data-action="edit"', js)
        self.assertIn('data-action="delete"', js)
        self.assertIn('data-action="generate"', js)
        self.assertIn("api/investments/recurring/plans/${encodeURIComponent(id)}", js)


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
        ), patch.object(app.database, "upsert_fund_prices") as upsert_prices:
            response = client.get("/api/funds/0721/nav")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["fund"]["fund_code"], "0721")
        self.assertEqual(payload["fund"]["fund_id"], "FLZ21")
        self.assertEqual(payload["nav"][0]["date"], "2026-06-19")
        self.assertEqual(payload["nav"][0]["nav"], 10.25)
        upsert_prices.assert_called_once_with("0721", nav_rows)

    def test_api_returns_performance_for_four_character_fund_code(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        fund = {
            "market": "海外",
            "fund_company": "聯博投信",
            "fund_id": "ALZ60",
            "fund_name_main": "聯博-全球非投資等級債券基金AT級別美元",
            "base_code": "BASE123",
            "can_sell": "*",
            "fund_code": "0922",
            "fund_name": "",
        }
        performance = {
            "source_url": "https://fund.bot.com.tw/w/wb/wb03a.djhtm?a=ALZ60-0922",
            "summary": {
                "fund_name": "聯博-全球非投資等級債券AT級別美元",
                "nav": 3.09,
                "nav_date": "2026/06/18",
                "year_to_date_return_percent": 1.78,
                "annualized_standard_deviation_percent": 3.88,
                "sharpe": 0.38,
                "beta": 1.07,
            },
            "cumulative_returns": [{"period": "一週", "return_percent": 0.32}],
        }

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_performance, "fetch_performance_for_fund", return_value=performance
        ) as fetch_performance:
            response = client.get("/api/funds/0922/performance")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["fund"]["fund_code"], "0922")
        self.assertEqual(payload["performance"]["summary"]["nav"], 3.09)
        fetch_performance.assert_called_once_with(
            fund_id="ALZ60",
            fund_code="0922",
            market="海外",
        )

    def test_api_returns_404_for_unknown_fund_code(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        with patch.object(app.database, "get_fund_by_code", return_value=None):
            response = client.get("/api/funds/9999/nav")

        self.assertEqual(response.status_code, 404)

    def test_api_returns_502_when_performance_source_fails(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        fund = {
            "market": "國內",
            "fund_company": "中國信託投信",
            "fund_id": "ACDS134",
            "fund_name_main": "中國信託高評級策略收益債券基金",
            "base_code": "BASE123",
            "can_sell": "*",
            "fund_code": "3916",
            "fund_name": "",
        }

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_performance, "fetch_performance_for_fund", side_effect=ValueError("missing table")
        ):
            response = client.get("/api/funds/3916/performance")

        self.assertEqual(response.status_code, 502)
        self.assertIn("績效來源查詢失敗", response.json()["detail"])

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

    def test_api_crud_investment_transactions(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        created = {
            "id": 1,
            "investment_type": "holdings",
            "fund_code": "0721",
            "fund_name": "測試基金",
            "trade_date": "2026-06-21",
            "nav_date": "2026-06-19",
            "nav": 10.25,
            "amount": 120000,
            "units": 9876.5432,
            "source_plan_id": None,
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }
        updated = dict(created, amount=125000)

        with patch.object(
            app.database, "create_investment_transaction", return_value=created
        ) as create_transaction, patch.object(
            app.database, "list_investment_transactions", side_effect=[[created], []]
        ) as list_transactions, patch.object(
            app.database, "update_investment_transaction", return_value=updated
        ) as update_transaction, patch.object(
            app.database, "delete_investment_transaction", return_value=True
        ) as delete_transaction:
            create_response = client.post(
                "/api/investments/holdings/transactions",
                json={
                    "fund_code": "0721",
                    "trade_date": "2026-06-21",
                    "amount": 120000,
                    "units": 9876.5432,
                },
            )
            list_response = client.get("/api/investments/holdings/transactions")
            update_response = client.put(
                "/api/investments/holdings/transactions/1",
                json={
                    "fund_code": "0721",
                    "trade_date": "2026-06-21",
                    "amount": 125000,
                    "units": 9876.5432,
                },
            )
            delete_response = client.delete("/api/investments/holdings/transactions/1")
            empty_response = client.get("/api/investments/holdings/transactions")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["nav_date"], "2026-06-19")
        self.assertEqual(list_response.json(), [created])
        self.assertEqual(update_response.json()["amount"], 125000)
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(empty_response.json(), [])
        create_transaction.assert_called_once_with(
            "holdings",
            "0721",
            trade_date="2026-06-21",
            amount=120000,
            units=9876.5432,
        )
        update_transaction.assert_called_once_with(
            "holdings",
            1,
            "0721",
            trade_date="2026-06-21",
            amount=125000,
            units=9876.5432,
        )
        delete_transaction.assert_called_once_with("holdings", 1)
        self.assertEqual(list_transactions.call_count, 2)

    def test_api_fetches_nav_when_transaction_has_no_local_price(self):
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
                "date": date(2026, 6, 10),
                "nav": 10.25,
                "change": None,
                "change_percent": None,
            }
        ]
        created = {
            "id": 1,
            "investment_type": "holdings",
            "fund_code": "0721",
            "fund_name": "測試基金",
            "trade_date": "2026-06-10",
            "nav_date": "2026-06-10",
            "nav": 10.25,
            "amount": 10000,
            "units": 33.0,
            "source_plan_id": None,
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_nav, "fetch_nav_for_fund", return_value=nav_rows
        ) as fetch_nav, patch.object(app.database, "upsert_fund_prices") as upsert_prices, patch.object(
            app.database,
            "create_investment_transaction",
            side_effect=[ValueError("找不到交易/基準日前可用淨值"), created],
        ) as create_transaction:
            response = client.post(
                "/api/investments/holdings/transactions",
                json={
                    "fund_code": "0721",
                    "trade_date": "2026-06-10",
                    "amount": 10000,
                    "units": 33,
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["nav_date"], "2026-06-10")
        fetch_nav.assert_called_once()
        upsert_prices.assert_called_once_with("0721", nav_rows)
        self.assertEqual(create_transaction.call_count, 2)

    def test_api_recurring_plan_create_and_generate_transactions(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        plan = {
            "id": 7,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 3000,
            "start_date": "2026-06-01",
            "end_date": None,
            "status": "active",
            "days": [6, 16, 26],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }
        generated = [
            {
                "id": 11,
                "investment_type": "recurring",
                "fund_code": "0721",
                "fund_name": "測試基金",
                "trade_date": "2026-06-06",
                "nav_date": "2026-06-06",
                "nav": 10.0,
                "amount": 3000,
                "units": 300.0,
                "source_plan_id": 7,
                "created_at": "2026-06-21T00:00:00+00:00",
                "updated_at": "2026-06-21T00:00:00+00:00",
            }
        ]

        with patch.object(
            app.database, "create_recurring_investment_plan", return_value=plan
        ) as create_plan, patch.object(
            app.database, "list_recurring_investment_plans", return_value=[plan]
        ), patch.object(
            app.database, "generate_recurring_transactions", return_value=generated
        ) as generate_transactions:
            create_response = client.post(
                "/api/investments/recurring/plans",
                json={
                    "fund_code": "0721",
                    "amount": 3000,
                    "start_date": "2026-06-01",
                    "end_date": None,
                    "days": [6, 16, 26],
                },
            )
            list_response = client.get("/api/investments/recurring/plans")
            generate_response = client.post("/api/investments/recurring/plans/7/generate-transactions")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["days"], [6, 16, 26])
        self.assertEqual(list_response.json(), [plan])
        self.assertEqual(generate_response.json(), generated)
        create_plan.assert_called_once_with(
            "0721",
            amount=3000,
            start_date="2026-06-01",
            end_date=None,
            days=[6, 16, 26],
        )
        generate_transactions.assert_called_once_with(7)

    def test_api_fetches_nav_when_creating_recurring_plan(self):
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
        nav_rows = [{"date": date(2026, 6, 1), "nav": 10.25, "change": None, "change_percent": None}]
        plan = {
            "id": 7,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 3000,
            "start_date": "2026-06-01",
            "end_date": None,
            "status": "active",
            "days": [6, 16, 26],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_nav, "fetch_nav_for_fund", return_value=nav_rows
        ) as fetch_nav, patch.object(app.database, "upsert_fund_prices") as upsert_prices, patch.object(
            app.database, "create_recurring_investment_plan", return_value=plan
        ):
            response = client.post(
                "/api/investments/recurring/plans",
                json={
                    "fund_code": "0721",
                    "amount": 3000,
                    "start_date": "2026-06-01",
                    "end_date": None,
                    "days": [6, 16, 26],
                },
            )

        self.assertEqual(response.status_code, 201)
        fetch_nav.assert_called_once()
        upsert_prices.assert_called_once_with("0721", nav_rows)

    def test_api_recurring_plan_update_and_delete(self):
        app = self.load_app()
        from fastapi.testclient import TestClient

        client = TestClient(app.app)
        updated = {
            "id": 7,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 5000,
            "start_date": "2026-07-01",
            "end_date": "2026-12-31",
            "status": "active",
            "days": [5, 15, 25],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

        with patch.object(
            app.database, "update_recurring_investment_plan", return_value=updated
        ) as update_plan, patch.object(
            app.database, "delete_recurring_investment_plan", return_value=True
        ) as delete_plan:
            update_response = client.put(
                "/api/investments/recurring/plans/7",
                json={
                    "fund_code": "0721",
                    "amount": 5000,
                    "start_date": "2026-07-01",
                    "end_date": "2026-12-31",
                    "days": [5, 15, 25],
                },
            )
            delete_response = client.delete("/api/investments/recurring/plans/7")

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["days"], [5, 15, 25])
        self.assertEqual(delete_response.status_code, 204)
        update_plan.assert_called_once_with(
            7,
            "0721",
            amount=5000,
            start_date="2026-07-01",
            end_date="2026-12-31",
            days=[5, 15, 25],
        )
        delete_plan.assert_called_once_with(7)

    def test_api_fetches_nav_when_updating_recurring_plan(self):
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
        nav_rows = [{"date": date(2026, 7, 1), "nav": 10.5, "change": None, "change_percent": None}]
        updated = {
            "id": 7,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 5000,
            "start_date": "2026-07-01",
            "end_date": None,
            "status": "active",
            "days": [5, 15, 25],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

        with patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_nav, "fetch_nav_for_fund", return_value=nav_rows
        ) as fetch_nav, patch.object(app.database, "upsert_fund_prices") as upsert_prices, patch.object(
            app.database, "update_recurring_investment_plan", return_value=updated
        ):
            response = client.put(
                "/api/investments/recurring/plans/7",
                json={
                    "fund_code": "0721",
                    "amount": 5000,
                    "start_date": "2026-07-01",
                    "end_date": None,
                    "days": [5, 15, 25],
                },
            )

        self.assertEqual(response.status_code, 200)
        fetch_nav.assert_called_once()
        upsert_prices.assert_called_once_with("0721", nav_rows)

    def test_api_fetches_nav_when_generating_recurring_transactions_has_no_local_price(self):
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
        plan = {
            "id": 7,
            "fund_code": "0721",
            "fund_name": "測試基金",
            "amount": 3000,
            "start_date": "2026-06-01",
            "end_date": None,
            "status": "active",
            "days": [6],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }
        nav_rows = [{"date": date(2026, 6, 6), "nav": 10.0, "change": None, "change_percent": None}]
        generated = [
            {
                "id": 11,
                "investment_type": "recurring",
                "fund_code": "0721",
                "fund_name": "測試基金",
                "trade_date": "2026-06-06",
                "nav_date": "2026-06-06",
                "nav": 10.0,
                "amount": 3000,
                "units": 300.0,
                "source_plan_id": 7,
                "created_at": "2026-06-21T00:00:00+00:00",
                "updated_at": "2026-06-21T00:00:00+00:00",
            }
        ]

        with patch.object(
            app.database,
            "generate_recurring_transactions",
            side_effect=[ValueError("找不到交易/基準日前可用淨值"), generated],
        ) as generate_transactions, patch.object(
            app.database, "list_recurring_investment_plans", return_value=[plan]
        ), patch.object(app.database, "get_fund_by_code", return_value=fund), patch.object(
            app.fetch_nav, "fetch_nav_for_fund", return_value=nav_rows
        ) as fetch_nav, patch.object(app.database, "upsert_fund_prices") as upsert_prices:
            response = client.post("/api/investments/recurring/plans/7/generate-transactions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), generated)
        fetch_nav.assert_called_once()
        upsert_prices.assert_called_once_with("0721", nav_rows)
        self.assertEqual(generate_transactions.call_count, 2)

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
