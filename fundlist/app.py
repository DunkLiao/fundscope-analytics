import re
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from . import GetFundBackSiteToCsv as fund_list_updater
    from . import database, fetch_nav, fetch_performance
except ImportError:
    import GetFundBackSiteToCsv as fund_list_updater
    import database
    import fetch_nav
    import fetch_performance


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
FUND_CODE_RE = re.compile(r"^[A-Za-z0-9]{4}$")

app = FastAPI(title="基金績效管理及預估")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

fund_list_update_lock = Lock()
DEFAULT_FUND_LIST_UPDATE_STATUS = {
    "status": "idle",
    "message": "尚未執行基金清單更新",
    "started_at": None,
    "finished_at": None,
}
fund_list_update_status = (
    database.get_latest_fund_list_update_status() or dict(DEFAULT_FUND_LIST_UPDATE_STATUS)
)


def utc_now_text():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_fund_code(fund_code):
    normalized_code = str(fund_code).strip().upper()
    if not FUND_CODE_RE.fullmatch(normalized_code):
        raise HTTPException(status_code=400, detail="基金代號必須是四碼英數字")
    return normalized_code


def parse_investment_setting_payload(payload):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="請提供投資設定資料")

    fund_code = normalize_fund_code(payload.get("fund_code", ""))
    amount = payload.get("amount")

    if isinstance(amount, bool):
        raise HTTPException(status_code=400, detail="投資金額必須是大於 0 的整數")
    if isinstance(amount, int):
        normalized_amount = amount
    elif isinstance(amount, str) and amount.strip().isdigit():
        normalized_amount = int(amount.strip())
    else:
        raise HTTPException(status_code=400, detail="投資金額必須是大於 0 的整數")

    if normalized_amount <= 0:
        raise HTTPException(status_code=400, detail="投資金額必須是大於 0 的整數")

    return fund_code, normalized_amount


def parse_positive_int(value, message="金額必須是大於 0 的整數"):
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=message)
    if isinstance(value, int):
        normalized_value = value
    elif isinstance(value, str) and value.strip().isdigit():
        normalized_value = int(value.strip())
    else:
        raise HTTPException(status_code=400, detail=message)
    if normalized_value <= 0:
        raise HTTPException(status_code=400, detail=message)
    return normalized_value


def parse_positive_float(value, message="單位數必須大於 0"):
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=message)
    try:
        normalized_value = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc
    if normalized_value <= 0:
        raise HTTPException(status_code=400, detail=message)
    return normalized_value


def parse_transaction_payload(investment_type, payload):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="請提供投資交易資料")
    fund_code = normalize_fund_code(payload.get("fund_code", ""))
    trade_date = str(payload.get("trade_date", "")).strip()
    if not trade_date:
        raise HTTPException(status_code=400, detail="交易/基準日期必填")
    amount = parse_positive_int(payload.get("amount"), "投資金額必須是大於 0 的整數")
    units = None
    if investment_type == "holdings":
        units = parse_positive_float(payload.get("units"), "現有單位數必須大於 0")
    return fund_code, trade_date, amount, units


def parse_recurring_plan_payload(payload):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="請提供定期定額計畫資料")
    fund_code = normalize_fund_code(payload.get("fund_code", ""))
    amount = parse_positive_int(payload.get("amount"), "每期金額必須是大於 0 的整數")
    start_date = str(payload.get("start_date", "")).strip()
    if not start_date:
        raise HTTPException(status_code=400, detail="開始日必填")
    end_date = payload.get("end_date")
    if isinstance(end_date, str):
        end_date = end_date.strip() or None
    days = payload.get("days")
    if not isinstance(days, list) or not days:
        raise HTTPException(status_code=400, detail="每月扣款日不可為空")
    return fund_code, amount, start_date, end_date, days


def raise_investment_setting_error(exc):
    message = str(exc)
    if "已存在" in message:
        raise HTTPException(status_code=409, detail=message) from exc
    if "找不到" in message:
        raise HTTPException(status_code=404, detail=message) from exc
    if "未知的投資設定類型" in message:
        raise HTTPException(status_code=404, detail=message) from exc
    raise HTTPException(status_code=400, detail=message) from exc


def raise_investment_data_error(exc):
    message = str(exc)
    if "已存在" in message:
        raise HTTPException(status_code=409, detail=message) from exc
    if "找不到" in message:
        raise HTTPException(status_code=404, detail=message) from exc
    if "未知" in message:
        raise HTTPException(status_code=404, detail=message) from exc
    raise HTTPException(status_code=400, detail=message) from exc


def days_back_for_trade_date(trade_date):
    try:
        parsed = date.fromisoformat(str(trade_date).strip())
    except ValueError:
        return 365
    return max(365, (date.today() - parsed).days + 7)


def refresh_nav_prices_for_transaction(fund_code, trade_date):
    fund = database.get_fund_by_code(fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="找不到此基金代號，請先更新基金清單")
    if not fund.get("fund_id"):
        raise HTTPException(status_code=502, detail="此基金缺少查詢傳輸代號，無法查詢淨值")

    try:
        nav_rows = fetch_nav.fetch_nav_for_fund(
            fund_id=fund["fund_id"],
            market=fund.get("market", ""),
            days_back=days_back_for_trade_date(trade_date),
        )
        database.upsert_fund_prices(fund_code, nav_rows)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"淨值來源查詢失敗：{exc}") from exc


def should_retry_after_nav_refresh(exc):
    return "找不到交易/基準日前可用淨值" in str(exc)


def get_recurring_plan_or_404(plan_id):
    for plan in database.list_recurring_investment_plans():
        if int(plan["id"]) == int(plan_id):
            return plan
    raise HTTPException(status_code=404, detail="找不到定期定額計畫")


def get_fund_list_update_status():
    with fund_list_update_lock:
        return dict(fund_list_update_status)


def set_fund_list_update_status(status, message, started_at=None, finished_at=None, persist=True):
    update = {
        "status": status,
        "message": message,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    with fund_list_update_lock:
        fund_list_update_status.update(update)
        result = dict(fund_list_update_status)

    if persist:
        database.save_fund_list_update_status(**result)

    return result


def run_fund_list_update():
    try:
        fund_list_updater.main()
    except Exception as exc:
        current = get_fund_list_update_status()
        set_fund_list_update_status(
            status="failed",
            message=f"基金清單更新失敗：{exc}",
            started_at=current.get("started_at"),
            finished_at=utc_now_text(),
        )
        return

    current = get_fund_list_update_status()
    set_fund_list_update_status(
        status="succeeded",
        message="基金清單更新完成",
        started_at=current.get("started_at"),
        finished_at=utc_now_text(),
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/fund-list/update", status_code=202)
def start_fund_list_update(background_tasks: BackgroundTasks):
    with fund_list_update_lock:
        if fund_list_update_status["status"] == "running":
            raise HTTPException(status_code=409, detail="基金清單更新已在執行中")

    response = set_fund_list_update_status(
        status="running",
        message="基金清單更新中",
        started_at=utc_now_text(),
        finished_at=None,
    )

    background_tasks.add_task(run_fund_list_update)
    return response


@app.get("/api/fund-list/update-status")
def read_fund_list_update_status():
    return get_fund_list_update_status()


@app.get("/api/funds/{fund_code}")
def get_fund_profile(fund_code):
    normalized_code = normalize_fund_code(fund_code)
    fund = database.get_fund_by_code(normalized_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="找不到此基金代號，請先更新基金清單")
    return fund


@app.get("/api/funds/{fund_code}/nav")
def get_fund_nav(fund_code):
    normalized_code = normalize_fund_code(fund_code)

    fund = database.get_fund_by_code(normalized_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="找不到此基金代號，請先更新基金清單")
    if not fund.get("fund_id"):
        raise HTTPException(status_code=502, detail="此基金缺少查詢傳輸代號，無法查詢淨值")

    try:
        nav_rows = fetch_nav.fetch_nav_for_fund(
            fund_id=fund["fund_id"],
            market=fund.get("market", ""),
            days_back=365,
        )
        database.upsert_fund_prices(normalized_code, nav_rows)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"淨值來源查詢失敗：{exc}") from exc

    return {"fund": fund, "nav": nav_rows}


@app.get("/api/funds/{fund_code}/performance")
def get_fund_performance(fund_code):
    normalized_code = normalize_fund_code(fund_code)

    fund = database.get_fund_by_code(normalized_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="找不到此基金代號，請先更新基金清單")
    if not fund.get("fund_id"):
        raise HTTPException(status_code=502, detail="此基金缺少查詢傳輸代號，無法查詢績效")

    try:
        performance = fetch_performance.fetch_performance_for_fund(
            fund_id=fund["fund_id"],
            fund_code=fund["fund_code"],
            market=fund.get("market", ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"績效來源查詢失敗：{exc}") from exc

    return {"fund": fund, "performance": performance}


@app.get("/api/investment-settings/{setting_type}")
def list_investment_settings(setting_type):
    try:
        return database.list_investment_settings(setting_type)
    except ValueError as exc:
        raise_investment_setting_error(exc)


@app.post("/api/investment-settings/{setting_type}", status_code=201)
def create_investment_setting(setting_type, payload=Body(...)):
    fund_code, amount = parse_investment_setting_payload(payload)
    try:
        return database.create_investment_setting(setting_type, fund_code, amount)
    except ValueError as exc:
        raise_investment_setting_error(exc)


@app.put("/api/investment-settings/{setting_type}/{row_id}")
def update_investment_setting(setting_type, row_id: int, payload=Body(...)):
    fund_code, amount = parse_investment_setting_payload(payload)
    try:
        return database.update_investment_setting(setting_type, row_id, fund_code, amount)
    except ValueError as exc:
        raise_investment_setting_error(exc)


@app.delete("/api/investment-settings/{setting_type}/{row_id}", status_code=204)
def delete_investment_setting(setting_type, row_id: int):
    try:
        deleted = database.delete_investment_setting(setting_type, row_id)
    except ValueError as exc:
        raise_investment_setting_error(exc)

    if not deleted:
        raise HTTPException(status_code=404, detail="找不到投資設定資料")
    return Response(status_code=204)


@app.get("/api/investments/{investment_type}/transactions")
def list_investment_transactions(investment_type):
    try:
        return database.list_investment_transactions(investment_type)
    except ValueError as exc:
        raise_investment_data_error(exc)


@app.post("/api/investments/{investment_type}/transactions", status_code=201)
def create_investment_transaction(investment_type, payload=Body(...)):
    fund_code, trade_date, amount, units = parse_transaction_payload(investment_type, payload)
    try:
        return database.create_investment_transaction(
            investment_type,
            fund_code,
            trade_date=trade_date,
            amount=amount,
            units=units,
        )
    except ValueError as exc:
        if should_retry_after_nav_refresh(exc):
            refresh_nav_prices_for_transaction(fund_code, trade_date)
            try:
                return database.create_investment_transaction(
                    investment_type,
                    fund_code,
                    trade_date=trade_date,
                    amount=amount,
                    units=units,
                )
            except ValueError as retry_exc:
                raise_investment_data_error(retry_exc)
        raise_investment_data_error(exc)


@app.put("/api/investments/{investment_type}/transactions/{row_id}")
def update_investment_transaction(investment_type, row_id: int, payload=Body(...)):
    fund_code, trade_date, amount, units = parse_transaction_payload(investment_type, payload)
    try:
        return database.update_investment_transaction(
            investment_type,
            row_id,
            fund_code,
            trade_date=trade_date,
            amount=amount,
            units=units,
        )
    except ValueError as exc:
        if should_retry_after_nav_refresh(exc):
            refresh_nav_prices_for_transaction(fund_code, trade_date)
            try:
                return database.update_investment_transaction(
                    investment_type,
                    row_id,
                    fund_code,
                    trade_date=trade_date,
                    amount=amount,
                    units=units,
                )
            except ValueError as retry_exc:
                raise_investment_data_error(retry_exc)
        raise_investment_data_error(exc)


@app.delete("/api/investments/{investment_type}/transactions/{row_id}", status_code=204)
def delete_investment_transaction(investment_type, row_id: int):
    try:
        deleted = database.delete_investment_transaction(investment_type, row_id)
    except ValueError as exc:
        raise_investment_data_error(exc)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到投資交易資料")
    return Response(status_code=204)


@app.get("/api/investments/recurring/plans")
def list_recurring_investment_plans():
    return database.list_recurring_investment_plans()


@app.post("/api/investments/recurring/plans", status_code=201)
def create_recurring_investment_plan(payload=Body(...)):
    fund_code, amount, start_date, end_date, days = parse_recurring_plan_payload(payload)
    refresh_nav_prices_for_transaction(fund_code, start_date)
    try:
        return database.create_recurring_investment_plan(
            fund_code,
            amount=amount,
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
    except ValueError as exc:
        raise_investment_data_error(exc)


@app.put("/api/investments/recurring/plans/{plan_id}")
def update_recurring_investment_plan(plan_id: int, payload=Body(...)):
    fund_code, amount, start_date, end_date, days = parse_recurring_plan_payload(payload)
    refresh_nav_prices_for_transaction(fund_code, start_date)
    try:
        return database.update_recurring_investment_plan(
            plan_id,
            fund_code,
            amount=amount,
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
    except ValueError as exc:
        raise_investment_data_error(exc)


@app.delete("/api/investments/recurring/plans/{plan_id}", status_code=204)
def delete_recurring_investment_plan(plan_id: int):
    try:
        deleted = database.delete_recurring_investment_plan(plan_id)
    except ValueError as exc:
        raise_investment_data_error(exc)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到定期定額計畫")
    return Response(status_code=204)


@app.post("/api/investments/recurring/plans/{plan_id}/generate-transactions")
def generate_recurring_transactions(plan_id: int):
    try:
        return database.generate_recurring_transactions(plan_id)
    except ValueError as exc:
        if should_retry_after_nav_refresh(exc):
            plan = get_recurring_plan_or_404(plan_id)
            refresh_nav_prices_for_transaction(plan["fund_code"], plan["start_date"])
            try:
                return database.generate_recurring_transactions(plan_id)
            except ValueError as retry_exc:
                raise_investment_data_error(retry_exc)
        raise_investment_data_error(exc)
