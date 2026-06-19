# Fundscope Analytics

本專案提供基金清單更新與基金逐日淨值查詢網站。基金清單由 Selenium 從 MoneyDJ/臺銀基金資訊頁抓取，輸出 CSV 並同步寫入 SQLite；網站使用 FastAPI 提供 API，前端可輸入四碼基金代號查詢近一年逐日淨值。

## 專案結構

```text
fundscope-analytics/
├─ db/
│  └─ funddata.db                 # 本機 SQLite 資料庫，不提交版控
├─ fundlist/
│  ├─ GetFundBackSiteToCsv.py     # 更新基金清單，輸出 CSV 並寫入 SQLite
│  ├─ app.py                      # FastAPI 網站後端
│  ├─ database.py                 # SQLite 建表、upsert、查詢
│  ├─ fetch_nav.py                # 基金逐日淨值查詢與解析
│  ├─ static/                     # 前端 HTML/CSS/JS
│  └─ tests/                      # unittest 測試
├─ requirements.txt
├─ 執行基金清單更新.bat
└─ 開啟基金淨值查詢網站.bat
```

## 安裝環境

```powershell
cd D:\VIbeCoding\fundscope-analytics
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

如果 `uvicorn.exe` 不在 PATH，仍可使用 `python -m uvicorn ...` 啟動，不需要額外設定 PATH。

## 更新基金清單

雙擊根目錄的：

```text
執行基金清單更新.bat
```

或用命令列執行：

```powershell
cd D:\VIbeCoding\fundscope-analytics
.\venv\Scripts\activate
python fundlist\GetFundBackSiteToCsv.py
```

更新後會產生：

- `fundlist\fund_full_info.csv`
- `db\funddata.db`

正式流程不使用 `old_fund_full_info.csv`。

## 開啟網站

雙擊根目錄的：

```text
開啟基金淨值查詢網站.bat
```

批次檔會啟動 FastAPI server，並自動開啟：

```text
http://127.0.0.1:8000/
```

關閉網站時，在批次檔視窗按 `Ctrl+C`。

也可以手動啟動：

```powershell
cd D:\VIbeCoding\fundscope-analytics
.\venv\Scripts\activate
python -m uvicorn fundlist.app:app --host 127.0.0.1 --port 8000
```

## 使用方式

1. 先更新基金清單，確保 `db\funddata.db` 存在。
2. 開啟網站。
3. 在前端輸入四碼基金代號，例如 `0721`。
4. 網站會顯示基金基本資料與近一年逐日淨值，日期由最新到最舊排列。

## API

查詢基金逐日淨值：

```http
GET /api/funds/{fund_code}/nav
```

範例：

```text
http://127.0.0.1:8000/api/funds/0721/nav
```

回傳內容包含：

- `fund`：基金清單資料
- `nav`：近一年逐日淨值、漲跌、漲跌幅

## 測試

```powershell
cd D:\VIbeCoding\fundscope-analytics\fundlist
python -m unittest discover -s tests -v
python -m py_compile GetFundBackSiteToCsv.py database.py fetch_nav.py app.py tests\test_fullstack_backend.py
```
