import csv
from pathlib import Path

try:
    from . import database
except ImportError:
    import database
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


DOMESTIC_URL = "https://bankfundinfotool.moneydj.com/w/aspprofile/fundlist.asp?a=1"
OVERSEAS_URL = "https://bankfundinfotool.moneydj.com/w/aspprofile/fundlist.asp?a=2"
LOGIN_URL = "https://bankfundinfotool.moneydj.com/w/aspprofile/index.asp"

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = SCRIPT_DIR / "fund_full_info.csv"

FIELDNAMES = [
    "market",
    "fund_company",
    "fund_id",
    "fund_name_main",
    "base_code",
    "can_sell",
    "fund_code",
    "fund_name",
]

MARKET_LABELS = {
    "Domestic": "國內",
    "Overseas": "海外",
    "國內": "國內",
    "海外": "海外",
}


def build_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    return chrome_options


def read_csv_rows(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in FIELDNAMES} for row in rows])


def remove_blank_and_duplicate_fund_codes(rows):
    result = []
    seen = set()
    for row in rows:
        fund_code = str(row.get("fund_code", "")).strip()
        if not fund_code or fund_code in seen:
            continue
        cleaned = {field: str(row.get(field, "")).strip() for field in FIELDNAMES}
        cleaned["market"] = MARKET_LABELS.get(cleaned["market"], cleaned["market"])
        cleaned["fund_code"] = fund_code
        result.append(cleaned)
        seen.add(fund_code)
    return result


def create_logged_in_driver():
    driver = webdriver.Chrome(options=build_chrome_options())
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 10)

    wait.until(lambda d: d.find_element(By.NAME, "dj_loginid")).send_keys("bot")
    wait.until(lambda d: d.find_element(By.NAME, "dj_loginpwd")).send_keys("bot")
    wait.until(lambda d: d.find_element(By.ID, "BT_login")).click()

    try:
        WebDriverWait(driver, 2).until(lambda d: len(d.window_handles) > 1)
    except Exception:
        pass

    if len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[1])
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

    return driver


def fetch_market(driver, url, market_name):
    print(f"Fetching {market_name}...", flush=True)

    try:
        driver.get(url)
    except Exception:
        driver.execute_script("window.stop();")

    rows = WebDriverWait(driver, 15).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "table:nth-of-type(2) tr")
    )
    result = []
    for row in rows:
        cols = [c.text.strip().replace("\n", " ") for c in row.find_elements(By.TAG_NAME, "td")]
        if len(cols) < 10:
            continue

        result.append(
            {
                "market": market_name,
                "fund_company": cols[0],
                "fund_id": cols[1],
                "fund_name_main": cols[2],
                "base_code": cols[3],
                "can_sell": cols[-5],
                "fund_code": cols[-4],
                "fund_name": cols[-3],
            }
        )

    print(f"  {market_name}: {len(result)} records", flush=True)
    return result


def main():
    driver = create_logged_in_driver()
    try:
        domestic = fetch_market(driver, DOMESTIC_URL, "國內")
        overseas = fetch_market(driver, OVERSEAS_URL, "海外")
    finally:
        driver.quit()

    fetched_rows = remove_blank_and_duplicate_fund_codes(domestic + overseas)

    print(f"Fetched: {len(fetched_rows)} records", flush=True)
    write_csv_rows(OUTPUT_CSV, fetched_rows)
    written_count = database.upsert_funds(fetched_rows)
    print(f"Done! Saved to {OUTPUT_CSV}", flush=True)
    print(f"Done! Upserted {written_count} funds to {database.DB_PATH}", flush=True)


if __name__ == "__main__":
    main()
