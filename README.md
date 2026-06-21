# Fundscope Analytics

本專案提供基金績效管理及預估的本機網站入口。第一版整合基金基本資料流程：基金清單由 Selenium 從 MoneyDJ/臺銀基金資訊頁抓取，輸出 CSV 並同步寫入 SQLite；網站使用 FastAPI 提供 API，前端可從「基本資料」選單更新基金清單，或輸入四碼基金代號查詢近一年逐日淨值與臺銀績效資料。首頁也提供「投資設定」功能，可管理庫存、定期定額計畫與單筆申購交易，並將交易使用的淨值落地到 SQLite，作為後續報酬與預估計算資料底座。

## 專案結構

```text
fundscope-analytics/
├─ db/
│  └─ funddata.db                 # 本機 SQLite 資料庫，不提交版控
├─ fundlist/
│  ├─ GetFundBackSiteToCsv.py     # 更新基金清單，輸出 CSV 並寫入 SQLite
│  ├─ app.py                      # FastAPI 網站後端與基金清單更新 API
│  ├─ database.py                 # SQLite 建表、upsert、查詢
│  ├─ fetch_nav.py                # 基金逐日淨值查詢與解析
│  ├─ fetch_performance.py        # 基金績效查詢與解析
│  ├─ static/                     # 前端 HTML/CSS/JS
│  └─ tests/                      # unittest 測試
├─ requirements.txt
├─ update_fundlist.bat
└─ start_website.bat
```

## Domain Model

`fundlist/domain/` 保存基金分析的內部領域模型，與 FastAPI response、SQLite row 分離：

- `entities.py`：`Fund`、`FundPrice`、`FundHolding`、`Prediction`、`SimulationResult`。
- `value_objects.py`：`DateRange`、`ReturnRate`、`Volatility`、`CAGR`。
- `services.py`：依基金淨值序列計算區間報酬率、CAGR、波動度。
- `mappers.py`：把現有 `funds` table row、投資設定 row、NAV row 轉成領域物件。

目前 Domain Model 是內部邊界；既有 API 回傳格式不變，也尚未新增 `Prediction` 或 `SimulationResult` 的正式資料表。

## 安裝環境

```powershell
cd D:\VIbeCoding\fundscope-analytics
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

如果 `uvicorn.exe` 不在 PATH，仍可使用 `python -m uvicorn ...` 啟動，不需要額外設定 PATH。

## 更新基金清單

開啟網站後，使用首頁「基本資料」選單中的「讀取基金清單」，即可從站內啟動更新並查看狀態。更新狀態會寫入 SQLite，重開網站後仍會顯示最後一次成功或失敗的時間與訊息。

也可以雙擊根目錄的批次檔作為備援：

```text
update_fundlist.bat
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

`db\funddata.db` 也會保存基金清單更新紀錄，用於首頁「讀取基金清單」的最後更新狀態。

正式流程不使用 `old_fund_full_info.csv`。

## 開啟網站

雙擊根目錄的：

```text
start_website.bat
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

1. 開啟網站。
2. 在首頁進入「基本資料 > 讀取基金清單」，更新 `db\funddata.db`。
3. 進入「基本資料 > 基金淨值查詢」或「基本資料 > 基金績效查詢」。
4. 輸入四碼基金代號，例如 `0721`。
5. 淨值查詢會顯示基金基本資料與近一年逐日淨值，日期由最新到最舊排列，並同步寫入 `fund_prices`；績效查詢會顯示臺銀績效頁的基本績效與累積報酬率。
6. 進入「投資設定」選單，可管理：
   - 「庫存基金設定」：基金代號、基準日期、成本金額、現有單位數。
   - 「定期定額申購基金設定」：基金代號、每期金額、開始日、選填結束日、每月扣款日。
   - 「單筆申購設定」：基金代號、申購日期、單次申購金額。

投資設定輸入基金代號後會即時查詢本機 `funds` 表並帶出基金名稱；如果查不到，請先更新基金清單。建立庫存或單筆交易前，請先查詢該基金淨值，讓系統把歷史淨值寫入 `fund_prices`。若交易/基準日期沒有當日淨值，系統會使用該日前最近一筆淨值，並在表格顯示實際採用的「使用淨值日期」；交易/基準日期不可晚於今天。

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

查詢成功後會同步 upsert 到 `fund_prices`，供投資交易落地使用。

查詢基金績效：

```http
GET /api/funds/{fund_code}/performance
```

範例：

```text
http://127.0.0.1:8000/api/funds/0922/performance
```

回傳內容包含：

- `fund`：基金清單資料
- `performance.summary`：基金、淨值、淨值日期、今年以來報酬率、年化標準差、Sharpe、β
- `performance.cumulative_returns`：依來源頁實際欄位回傳的累積報酬率
- `performance.source_url`：臺銀績效來源頁

查詢單一基金基本資料：

```http
GET /api/funds/{fund_code}
```

啟動基金清單更新：

```http
POST /api/fund-list/update
```

查詢基金清單更新狀態：

```http
GET /api/fund-list/update-status
```

舊版投資設定 CRUD 仍保留：

```http
GET /api/investment-settings/{setting_type}
POST /api/investment-settings/{setting_type}
PUT /api/investment-settings/{setting_type}/{id}
DELETE /api/investment-settings/{setting_type}/{id}
```

`setting_type` 可用值：

- `holdings`：庫存基金設定，保存成本金額。
- `recurring`：定期定額申購基金設定，保存每期預計申購金額。
- `lump-sum`：單筆申購設定，保存單次申購金額。

新增與更新 payload：

```json
{
  "fund_code": "0721",
  "amount": 120000
}
```

投資設定會寫入 `db\funddata.db` 的三張表：

- `holding_fund_settings`
- `recurring_fund_settings`
- `lump_sum_fund_settings`

新版投資交易 API：

```http
GET /api/investments/{investment_type}/transactions
POST /api/investments/{investment_type}/transactions
PUT /api/investments/{investment_type}/transactions/{id}
DELETE /api/investments/{investment_type}/transactions/{id}
```

`investment_type` 可用值：

- `holdings`：庫存交易，需提供現有單位數。
- `recurring`：定期定額產生的交易。
- `lump-sum`：單筆申購交易。

庫存交易 payload：

```json
{
  "fund_code": "0721",
  "trade_date": "2026-06-21",
  "amount": 120000,
  "units": 9876.5432
}
```

單筆交易 payload：

```json
{
  "fund_code": "0721",
  "trade_date": "2026-06-21",
  "amount": 100000
}
```

定期定額計畫 API：

```http
GET /api/investments/recurring/plans
POST /api/investments/recurring/plans
POST /api/investments/recurring/plans/{id}/generate-transactions
```

定期定額計畫 payload：

```json
{
  "fund_code": "0721",
  "amount": 3000,
  "start_date": "2026-06-01",
  "end_date": null,
  "days": [6, 16, 26]
}
```

新版投資資料會寫入：

- `fund_prices`
- `investment_transactions`
- `recurring_investment_plans`
- `recurring_investment_plan_days`

## 測試

```powershell
cd D:\VIbeCoding\fundscope-analytics\fundlist
python -m unittest discover -s tests -v
python -m py_compile GetFundBackSiteToCsv.py database.py fetch_nav.py fetch_performance.py app.py tests\test_fullstack_backend.py
```
