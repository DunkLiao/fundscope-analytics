import re
from datetime import date, datetime, timedelta

import requests


TIMEOUT = 30
USER_AGENT = "Mozilla/5.0"
ENDPOINT_BY_MARKET = {
    "國內": ("tBCDNavList", "BCDNavList"),
    "海外": ("BCDNavList", "tBCDNavList"),
}


def fmt_ymd(value):
    return f"{value.year}-{value.month}-{value.day}"


def fetch_bcd_raw(endpoint, a, start, end, b=1, timeout=TIMEOUT):
    url = f"https://fund.bot.com.tw/w/bcd/{endpoint}.djbcd"
    response = requests.get(
        url,
        params={"a": a, "b": b, "c": start, "d": end},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text.strip()


def parse_bcd_nav(raw):
    raw = raw.strip()
    parts = re.split(r"\s+", raw, maxsplit=1)
    if len(parts) < 2:
        raise ValueError("BCD 回傳無法分成兩段（日期段/數值段）")

    dates = [item for item in parts[0].split(",") if item]
    navs = [item for item in parts[1].split(",") if item]
    if not dates or not navs:
        raise ValueError("日期或淨值序列為空")
    if len(dates) != len(navs):
        raise ValueError(f"日期/淨值筆數不一致：dates={len(dates)} navs={len(navs)}")

    rows = []
    for raw_date, raw_nav in zip(dates, navs):
        try:
            parsed_date = datetime.strptime(raw_date, "%Y%m%d").date()
            nav = float(raw_nav)
        except ValueError as exc:
            raise ValueError(f"BCD 回傳含無法解析的日期或淨值：{raw_date}, {raw_nav}") from exc
        rows.append({"date": parsed_date, "nav": nav})

    if not rows:
        raise ValueError("解析後資料為空")
    return sorted(rows, key=lambda row: row["date"])


def compute_change_cols(rows):
    result = []
    previous_nav = None
    for row in rows:
        nav = row["nav"]
        change = None if previous_nav is None else nav - previous_nav
        change_percent = None
        if previous_nav not in (None, 0):
            change_percent = (change / previous_nav) * 100
        result.append(
            {
                "date": row["date"],
                "nav": nav,
                "change": change,
                "change_percent": change_percent,
            }
        )
        previous_nav = nav
    return result


def fetch_nav_for_fund(fund_id, market, days_back=365, timeout=TIMEOUT, today=None):
    end_date = today or date.today()
    start_date = end_date - timedelta(days=days_back)
    start = fmt_ymd(start_date)
    end = fmt_ymd(end_date)
    endpoints = ENDPOINT_BY_MARKET.get(market, ("tBCDNavList", "BCDNavList"))
    errors = []

    for endpoint in endpoints:
        try:
            raw = fetch_bcd_raw(endpoint, a=fund_id, start=start, end=end, timeout=timeout)
            rows = parse_bcd_nav(raw)
            return list(reversed(compute_change_cols(rows)))
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")

    raise ValueError("無法取得基金淨值：" + "；".join(errors))
