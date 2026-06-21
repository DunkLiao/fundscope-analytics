# Repository Guidelines

## Project Structure & Module Organization

此專案是本機基金分析網站。主要後端程式位於 `fundlist/`：`app.py` 提供 FastAPI API 與靜態頁入口，`database.py` 管理 SQLite schema 與 CRUD，`GetFundBackSiteToCsv.py` 以 Selenium 更新基金清單，`fetch_nav.py` 與 `fetch_performance.py` 負責外部資料查詢與解析。前端資產位於 `fundlist/static/`，測試位於 `fundlist/tests/`。本機資料庫位於 `db/funddata.db`，屬 runtime output，不應提交。

## Build, Test, and Development Commands

先建立或啟用 Python 環境後安裝依賴：

```powershell
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

啟動網站：

```powershell
python -m uvicorn fundlist.app:app --host 127.0.0.1 --port 8000
```

更新基金清單：

```powershell
python fundlist\GetFundBackSiteToCsv.py
```

Windows 使用者也可執行 `start_website.bat` 與 `update_fundlist.bat`。

## Coding Style & Naming Conventions

Python 使用 4 空格縮排，函式與變數採 `snake_case`，常數採 `UPPER_SNAKE_CASE`。API path、資料表欄位與 JSON key 應保持語意穩定，避免破壞前端既有呼叫。前端檔案集中維護於 `fundlist/static/`；新增互動邏輯時優先延伸既有 `app.js` 結構，而非分散到 inline script。

## Testing Guidelines

測試使用標準 `unittest`。從 `fundlist/` 執行：

```powershell
python -m unittest discover -s tests -v
python -m py_compile GetFundBackSiteToCsv.py database.py fetch_nav.py fetch_performance.py app.py tests\test_fullstack_backend.py
```

新增測試檔命名為 `test_*.py`，並優先覆蓋 API 行為、SQLite 寫入/讀取、外部 HTML 解析與錯誤狀態處理。

## Commit & Pull Request Guidelines

既有 commit 採簡短祈使句，例如 `Add investment settings CRUD`、`Update README and 7 other files`。提交訊息請描述使用者可見變更或主要技術變更。PR 應包含變更摘要、測試結果、資料庫或 CSV 影響；若改動前端畫面，附上截圖或本機驗證 URL。

## Security & Configuration Tips

不要提交 `venv/`、`db/*.db`、`fundlist/fund_full_info.csv`、log 或 cache 檔。外部網站抓取邏輯需保留明確 timeout 與錯誤回報，避免讓 FastAPI request 或批次更新長時間無聲卡住。
