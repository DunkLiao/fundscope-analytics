import re

import requests
from bs4 import BeautifulSoup


TIMEOUT = 30
USER_AGENT = "Mozilla/5.0"
PERFORMANCE_URL_BY_MARKET = {
    "國內": "https://fund.bot.com.tw/w/wr/wr03a.djhtm?a={fund_id}-{fund_code}",
    "海外": "https://fund.bot.com.tw/w/wb/wb03a.djhtm?a={fund_id}-{fund_code}",
}


def normalize_cell_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def to_float(value):
    text = normalize_cell_text(value).replace(",", "")
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"無法解析績效數值：{value}") from exc


def extract_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [normalize_cell_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        cells = [cell for cell in cells if cell != ""]
        if cells:
            rows.append(cells)
    return rows


def find_summary(rows):
    for index, cells in enumerate(rows[:-1]):
        joined = "".join(cells)
        if "基金" in joined and "淨值" in joined and "淨值日期" in joined and "Sharpe" in joined:
            values = rows[index + 1]
            if len(values) < 7:
                continue
            try:
                return {
                    "fund_name": values[0],
                    "nav": to_float(values[1]),
                    "nav_date": values[2],
                    "year_to_date_return_percent": to_float(values[3]),
                    "annualized_standard_deviation_percent": to_float(values[4]),
                    "sharpe": to_float(values[5]),
                    "beta": to_float(values[6]),
                }
            except ValueError:
                continue
    raise ValueError("找不到績效摘要表")


def find_cumulative_returns(rows):
    for index, cells in enumerate(rows[:-2]):
        joined = "".join(cells)
        if "基金名稱" not in joined or "累積報酬率" not in joined:
            continue

        period_cells = rows[index + 1]
        value_cells = rows[index + 2]
        if not value_cells:
            continue
        if "累積報酬率" in "".join(period_cells):
            continue

        periods = [period for period in period_cells if period != "基金名稱"]
        values = value_cells[1 : 1 + len(periods)]
        if len(values) != len(periods):
            continue

        try:
            return [
                {"period": period, "return_percent": to_float(value)}
                for period, value in zip(periods, values)
            ]
        except ValueError:
            continue
    raise ValueError("找不到累積報酬率表")


def parse_performance_html(html):
    rows = extract_rows(html)
    if not rows:
        raise ValueError("績效頁沒有可解析的表格資料")
    return {
        "summary": find_summary(rows),
        "cumulative_returns": find_cumulative_returns(rows),
    }


def build_performance_url(fund_id, fund_code, market):
    template = PERFORMANCE_URL_BY_MARKET.get(market, PERFORMANCE_URL_BY_MARKET["海外"])
    return template.format(
        fund_id=str(fund_id).strip().upper(),
        fund_code=str(fund_code).strip().upper(),
    )


def fetch_performance_html(url, timeout=TIMEOUT):
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    encoding = response.encoding or response.apparent_encoding or "big5"
    return response.content.decode(encoding, errors="replace")


def fetch_performance_for_fund(fund_id, fund_code, market, timeout=TIMEOUT):
    url = build_performance_url(fund_id, fund_code, market)
    html = fetch_performance_html(url, timeout=timeout)
    result = parse_performance_html(html)
    result["source_url"] = url
    return result
