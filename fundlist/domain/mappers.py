from datetime import date

from .entities import Fund, FundHolding, FundPrice
from .value_objects import ReturnRate


def _parse_date(value):
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("/", "-")
    return date.fromisoformat(text)


def fund_from_row(row):
    name = row.get("fund_name") or row.get("fund_name_main") or row.get("fund_code")
    return Fund(
        fund_code=row.get("fund_code", ""),
        name=name,
        market_type=row.get("market", ""),
        issuer=row.get("fund_company", ""),
        source_updated_at=row.get("updated_at", ""),
        fund_id=row.get("fund_id", ""),
        base_code=row.get("base_code", ""),
        can_sell=row.get("can_sell", ""),
    )


def fund_price_from_nav_row(fund_code, row, source="nav"):
    change_percent = row.get("change_percent")
    return FundPrice(
        fund_code=fund_code,
        price_date=_parse_date(row["date"]),
        nav=float(row["nav"]),
        change_amount=row.get("change"),
        change_rate=None
        if change_percent is None
        else ReturnRate.from_percent(change_percent, period="daily"),
        source=source,
    )


def fund_holding_from_setting_row(row, setting_type):
    return FundHolding(
        holding_id=row.get("id"),
        fund_code=row.get("fund_code", ""),
        holding_type=setting_type,
        amount=row.get("amount"),
    )
