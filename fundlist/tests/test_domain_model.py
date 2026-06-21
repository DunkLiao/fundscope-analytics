import math
import unittest
from datetime import date


class ValueObjectTests(unittest.TestCase):
    def test_date_range_rejects_end_before_start(self):
        from domain.value_objects import DateRange

        with self.assertRaisesRegex(ValueError, "start_date"):
            DateRange(date(2026, 6, 20), date(2026, 6, 19))

    def test_return_rate_uses_ratio_and_can_render_percent(self):
        from domain.value_objects import ReturnRate

        rate = ReturnRate.from_percent(5.25, period="1Y")

        self.assertAlmostEqual(rate.value, 0.0525)
        self.assertEqual(rate.to_percent(), 5.25)
        self.assertEqual(rate.period, "1Y")

    def test_volatility_rejects_negative_values(self):
        from domain.value_objects import Volatility

        with self.assertRaisesRegex(ValueError, "Volatility"):
            Volatility(-0.1, period="daily")

    def test_cagr_calculates_annualized_growth(self):
        from domain.value_objects import CAGR, DateRange

        result = CAGR.from_values(
            start_value=100,
            end_value=121,
            date_range=DateRange(date(2024, 1, 1), date(2026, 1, 1)),
        )

        self.assertAlmostEqual(result.value, 0.10, places=3)


class EntityTests(unittest.TestCase):
    def test_fund_requires_code_and_normalizes_identity(self):
        from domain.entities import Fund

        fund = Fund(fund_code=" 0721 ", name="測試基金", market_type="海外")

        self.assertEqual(fund.fund_code, "0721")
        with self.assertRaisesRegex(ValueError, "fund_code"):
            Fund(fund_code=" ", name="測試基金")

    def test_fund_price_requires_positive_nav(self):
        from domain.entities import FundPrice

        with self.assertRaisesRegex(ValueError, "nav"):
            FundPrice(fund_code="0721", price_date=date(2026, 6, 19), nav=0)

    def test_fund_holding_requires_positive_amount(self):
        from domain.entities import FundHolding

        with self.assertRaisesRegex(ValueError, "amount"):
            FundHolding(fund_code="0721", holding_type="holdings", amount=0)

    def test_prediction_and_simulation_require_matching_fund(self):
        from domain.entities import Prediction, SimulationResult
        from domain.value_objects import DateRange, ReturnRate, Volatility, CAGR

        prediction = Prediction(
            fund_code="0721",
            date_range=DateRange(date(2025, 1, 1), date(2026, 1, 1)),
            prediction_horizon=DateRange(date(2026, 1, 2), date(2027, 1, 1)),
            expected_return=ReturnRate(0.08, period="1Y"),
            expected_volatility=Volatility(0.12, period="1Y", annualized=True),
            expected_cagr=CAGR(0.075, DateRange(date(2026, 1, 2), date(2027, 1, 1))),
            method="historical-average",
        )

        result = SimulationResult(
            fund_code="0721",
            date_range=DateRange(date(2026, 1, 1), date(2027, 1, 1)),
            initial_amount=100000,
            recurring_amount=3000,
            final_value=115000,
            total_cost=136000,
            total_return=ReturnRate(-0.1544117647, period="simulation"),
            cagr=CAGR(-0.1544117647, DateRange(date(2026, 1, 1), date(2027, 1, 1))),
            volatility=Volatility(0.1, period="simulation", annualized=True),
            prediction_id=prediction.prediction_id,
        )

        self.assertEqual(prediction.fund_code, result.fund_code)
        with self.assertRaisesRegex(ValueError, "same fund"):
            SimulationResult(
                fund_code="9999",
                date_range=result.date_range,
                initial_amount=100000,
                recurring_amount=0,
                final_value=105000,
                total_cost=100000,
                total_return=ReturnRate(0.05, period="simulation"),
                cagr=CAGR(0.05, result.date_range),
                volatility=Volatility(0.1, period="simulation", annualized=True),
                prediction=prediction,
            )


class DomainServiceTests(unittest.TestCase):
    def test_calculates_return_cagr_and_volatility_from_prices(self):
        from domain.entities import FundPrice
        from domain.services import calculate_cagr, calculate_period_return, calculate_volatility
        from domain.value_objects import DateRange

        prices = [
            FundPrice("0721", date(2026, 1, 1), 100),
            FundPrice("0721", date(2026, 1, 2), 110),
            FundPrice("0721", date(2026, 1, 3), 121),
        ]
        date_range = DateRange(date(2026, 1, 1), date(2026, 1, 3))

        self.assertAlmostEqual(calculate_period_return(prices, date_range).value, 0.21)
        self.assertAlmostEqual(calculate_cagr(prices, date_range).value, (1.21 ** (365 / 2)) - 1)
        self.assertTrue(math.isclose(calculate_volatility(prices, annualized=False).value, 0.0, abs_tol=1e-12))

    def test_calculations_reject_insufficient_price_data(self):
        from domain.entities import FundPrice
        from domain.services import calculate_period_return
        from domain.value_objects import DateRange

        with self.assertRaisesRegex(ValueError, "at least two"):
            calculate_period_return(
                [FundPrice("0721", date(2026, 1, 1), 100)],
                DateRange(date(2026, 1, 1), date(2026, 1, 3)),
            )


class MapperTests(unittest.TestCase):
    def test_maps_existing_rows_to_domain_objects(self):
        from domain.mappers import fund_from_row, fund_holding_from_setting_row, fund_price_from_nav_row

        fund = fund_from_row(
            {
                "fund_code": "0721",
                "fund_name": "",
                "fund_name_main": "測試基金",
                "market": "海外",
                "fund_company": "測試投信",
                "fund_id": "FLZ21",
                "base_code": "BASE123",
                "can_sell": "*",
                "updated_at": "2026-06-21T00:00:00+00:00",
            }
        )
        price = fund_price_from_nav_row("0721", {"date": "2026-06-19", "nav": 10.25, "change": -0.25, "change_percent": -2.38})
        holding = fund_holding_from_setting_row({"id": 1, "fund_code": "0721", "amount": 120000}, "holdings")

        self.assertEqual(fund.name, "測試基金")
        self.assertEqual(price.price_date, date(2026, 6, 19))
        self.assertEqual(holding.holding_type, "holdings")


class DatabaseDomainMappingTests(unittest.TestCase):
    def test_database_can_return_domain_objects_without_changing_existing_rows(self):
        import tempfile
        from pathlib import Path

        import database
        from domain.entities import Fund, FundHolding

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
            created = database.create_investment_setting("holdings", "0721", 120000, db_path)

            fund = database.get_fund_domain_by_code("0721", db_path)
            holdings = database.list_fund_holding_domains("holdings", db_path)

            self.assertIsInstance(fund, Fund)
            self.assertEqual(fund.name, "測試基金")
            self.assertIsInstance(holdings[0], FundHolding)
            self.assertEqual(holdings[0].holding_id, created["id"])
