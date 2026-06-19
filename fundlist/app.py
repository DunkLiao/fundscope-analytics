import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from . import database, fetch_nav
except ImportError:
    import database
    import fetch_nav


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
FUND_CODE_RE = re.compile(r"^[A-Za-z0-9]{4}$")

app = FastAPI(title="基金淨值查詢")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/funds/{fund_code}/nav")
def get_fund_nav(fund_code):
    normalized_code = fund_code.strip().upper()
    if not FUND_CODE_RE.fullmatch(normalized_code):
        raise HTTPException(status_code=400, detail="基金代號必須是四碼英數字")

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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"淨值來源查詢失敗：{exc}") from exc

    return {"fund": fund, "nav": nav_rows}
