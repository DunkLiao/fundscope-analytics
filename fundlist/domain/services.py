from math import sqrt

from .entities import FundPrice
from .value_objects import CAGR, DateRange, ReturnRate, Volatility


def prices_in_range(prices, date_range):
    filtered = [
        price
        for price in prices
        if date_range.start_date <= price.price_date <= date_range.end_date
    ]
    return sorted(filtered, key=lambda price: price.price_date)


def _require_two_prices(prices):
    if len(prices) < 2:
        raise ValueError("at least two FundPrice rows are required")


def calculate_period_return(prices, date_range):
    ordered_prices = prices_in_range(prices, date_range)
    _require_two_prices(ordered_prices)
    start_nav = ordered_prices[0].nav
    end_nav = ordered_prices[-1].nav
    return ReturnRate((end_nav / start_nav) - 1, period="date_range")


def calculate_cagr(prices, date_range):
    ordered_prices = prices_in_range(prices, date_range)
    _require_two_prices(ordered_prices)
    return CAGR.from_values(ordered_prices[0].nav, ordered_prices[-1].nav, date_range)


def daily_return_rates(prices):
    ordered_prices = sorted(prices, key=lambda price: price.price_date)
    _require_two_prices(ordered_prices)
    rates = []
    for previous, current in zip(ordered_prices, ordered_prices[1:]):
        if not isinstance(previous, FundPrice) or not isinstance(current, FundPrice):
            raise ValueError("prices must contain FundPrice objects")
        rates.append((current.nav / previous.nav) - 1)
    return rates


def calculate_volatility(prices, annualized=True):
    rates = daily_return_rates(prices)
    mean = sum(rates) / len(rates)
    variance = sum((rate - mean) ** 2 for rate in rates) / len(rates)
    volatility = sqrt(variance)
    if annualized:
        volatility *= sqrt(252)
    return Volatility(volatility, period="daily_returns", annualized=annualized)
