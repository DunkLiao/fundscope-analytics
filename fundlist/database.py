import sqlite3
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from .domain.mappers import fund_from_row, fund_holding_from_setting_row
except ImportError:
    from domain.mappers import fund_from_row, fund_holding_from_setting_row


SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR.parent / "db" / "funddata.db"

FUND_FIELDS = [
    "market",
    "fund_company",
    "fund_id",
    "fund_name_main",
    "base_code",
    "can_sell",
    "fund_code",
    "fund_name",
]

INVESTMENT_SETTING_TYPES = {
    "holdings": {
        "table": "holding_fund_settings",
        "amount_column": "cost_amount",
    },
    "recurring": {
        "table": "recurring_fund_settings",
        "amount_column": "periodic_amount",
    },
    "lump-sum": {
        "table": "lump_sum_fund_settings",
        "amount_column": "single_amount",
    },
}

INVESTMENT_TRANSACTION_TYPES = {"holdings", "recurring", "lump-sum"}


def init_db(db_path=DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS funds (
                fund_code TEXT PRIMARY KEY,
                market TEXT NOT NULL DEFAULT '',
                fund_company TEXT NOT NULL DEFAULT '',
                fund_id TEXT NOT NULL DEFAULT '',
                fund_name_main TEXT NOT NULL DEFAULT '',
                base_code TEXT NOT NULL DEFAULT '',
                can_sell TEXT NOT NULL DEFAULT '',
                fund_name TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_list_update_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        for config in INVESTMENT_SETTING_TYPES.values():
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {config["table"]} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fund_code TEXT NOT NULL UNIQUE,
                    {config["amount_column"]} INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code TEXT NOT NULL,
                price_date TEXT NOT NULL,
                nav REAL NOT NULL,
                change_amount REAL,
                change_percent REAL,
                source TEXT NOT NULL DEFAULT 'nav',
                created_at TEXT NOT NULL,
                UNIQUE(fund_code, price_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS investment_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_type TEXT NOT NULL,
                fund_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                nav_date TEXT NOT NULL,
                nav REAL NOT NULL,
                amount INTEGER NOT NULL,
                units REAL NOT NULL,
                source_plan_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_plan_id, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_investment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code TEXT NOT NULL,
                amount INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_investment_plan_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                day_of_month INTEGER NOT NULL,
                UNIQUE(plan_id, day_of_month)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _investment_config(setting_type):
    try:
        return INVESTMENT_SETTING_TYPES[str(setting_type).strip()]
    except KeyError as exc:
        raise ValueError("未知的投資設定類型") from exc


def _normalize_fund_code(fund_code):
    return str(fund_code).strip().upper()


def _coerce_positive_int(value):
    if isinstance(value, bool):
        raise ValueError("投資金額必須是大於 0 的整數")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.strip().isdigit():
        amount = int(value.strip())
    else:
        raise ValueError("投資金額必須是大於 0 的整數")

    if amount <= 0:
        raise ValueError("投資金額必須是大於 0 的整數")
    return amount


def _coerce_positive_float(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name}必須大於 0")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}必須大於 0") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name}必須大於 0")
    return normalized


def _parse_date(value, field_name="日期"):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name}格式必須是 YYYY-MM-DD") from exc


def _today(today=None):
    return _parse_date(today, "今天") if today is not None else date.today()


def _investment_transaction_type(setting_type):
    normalized = str(setting_type).strip()
    if normalized not in INVESTMENT_TRANSACTION_TYPES:
        raise ValueError("未知的投資類型")
    return normalized


def _normalize_days(days):
    if not isinstance(days, (list, tuple)) or not days:
        raise ValueError("每月扣款日不可為空")
    normalized = sorted({int(day) for day in days})
    if any(day < 1 or day > 31 for day in normalized):
        raise ValueError("每月扣款日必須介於 1 到 31")
    return normalized


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_fund_exists(fund_code, db_path):
    normalized_code = _normalize_fund_code(fund_code)
    if get_fund_by_code(normalized_code, db_path) is None:
        raise ValueError("找不到此基金代號，請先更新基金清單")
    return normalized_code


def _fetch_transaction(row_id, db_path):
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT
                t.id,
                t.investment_type,
                t.fund_code,
                COALESCE(NULLIF(f.fund_name_main, ''), NULLIF(f.fund_name, ''), '') AS fund_name,
                t.trade_date,
                t.nav_date,
                t.nav,
                t.amount,
                t.units,
                t.source_plan_id,
                t.created_at,
                t.updated_at
            FROM investment_transactions AS t
            LEFT JOIN funds AS f ON f.fund_code = t.fund_code
            WHERE t.id = ?
            """,
            (int(row_id),),
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
        cursor.close()
    finally:
        conn.close()
    return result


def _fetch_recurring_plan(row_id, db_path):
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT
                p.id,
                p.fund_code,
                COALESCE(NULLIF(f.fund_name_main, ''), NULLIF(f.fund_name, ''), '') AS fund_name,
                p.amount,
                p.start_date,
                p.end_date,
                p.status,
                p.created_at,
                p.updated_at
            FROM recurring_investment_plans AS p
            LEFT JOIN funds AS f ON f.fund_code = p.fund_code
            WHERE p.id = ?
            """,
            (int(row_id),),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return None
        result = dict(row)
        cursor.close()
        cursor = conn.execute(
            """
            SELECT day_of_month
            FROM recurring_investment_plan_days
            WHERE plan_id = ?
            ORDER BY day_of_month
            """,
            (int(row_id),),
        )
        result["days"] = [item["day_of_month"] for item in cursor.fetchall()]
        cursor.close()
    finally:
        conn.close()
    return result


def _fetch_investment_setting(setting_type, row_id, db_path):
    config = _investment_config(setting_type)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"""
            SELECT
                s.id,
                s.fund_code,
                COALESCE(NULLIF(f.fund_name_main, ''), NULLIF(f.fund_name, ''), '') AS fund_name,
                s.{config["amount_column"]} AS amount,
                s.created_at,
                s.updated_at
            FROM {config["table"]} AS s
            LEFT JOIN funds AS f ON f.fund_code = s.fund_code
            WHERE s.id = ?
            """,
            (int(row_id),),
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
        cursor.close()
    finally:
        conn.close()
    return result


def list_investment_settings(setting_type, db_path=DB_PATH):
    init_db(db_path)
    config = _investment_config(setting_type)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"""
            SELECT
                s.id,
                s.fund_code,
                COALESCE(NULLIF(f.fund_name_main, ''), NULLIF(f.fund_name, ''), '') AS fund_name,
                s.{config["amount_column"]} AS amount,
                s.created_at,
                s.updated_at
            FROM {config["table"]} AS s
            LEFT JOIN funds AS f ON f.fund_code = s.fund_code
            ORDER BY s.id
            """
        )
        result = [dict(row) for row in cursor.fetchall()]
        cursor.close()
    finally:
        conn.close()
    return result


def create_investment_setting(setting_type, fund_code, amount, db_path=DB_PATH):
    init_db(db_path)
    config = _investment_config(setting_type)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_amount = _coerce_positive_int(amount)
    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            f"""
            INSERT INTO {config["table"]} (
                fund_code, {config["amount_column"]}, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (normalized_code, normalized_amount, timestamp, timestamp),
        )
        conn.commit()
        row_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("基金代號已存在於此投資設定") from exc
    finally:
        conn.close()
    return _fetch_investment_setting(setting_type, row_id, db_path)


def update_investment_setting(setting_type, row_id, fund_code, amount, db_path=DB_PATH):
    init_db(db_path)
    config = _investment_config(setting_type)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_amount = _coerce_positive_int(amount)
    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            f"""
            UPDATE {config["table"]}
            SET fund_code = ?, {config["amount_column"]} = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_code, normalized_amount, timestamp, int(row_id)),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise ValueError("找不到投資設定資料")
    except sqlite3.IntegrityError as exc:
        raise ValueError("基金代號已存在於此投資設定") from exc
    finally:
        conn.close()
    return _fetch_investment_setting(setting_type, row_id, db_path)


def delete_investment_setting(setting_type, row_id, db_path=DB_PATH):
    init_db(db_path)
    config = _investment_config(setting_type)
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            f"DELETE FROM {config['table']} WHERE id = ?",
            (int(row_id),),
        )
        conn.commit()
        deleted = cursor.rowcount > 0
    finally:
        conn.close()
    return deleted


def upsert_fund_prices(fund_code, rows, db_path=DB_PATH, source="nav"):
    init_db(db_path)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    timestamp = _utc_now_text()
    values = []
    for row in rows:
        price_date = _parse_date(row.get("date") or row.get("price_date"), "淨值日期").isoformat()
        nav = _coerce_positive_float(row.get("nav"), "淨值")
        values.append(
            (
                normalized_code,
                price_date,
                nav,
                row.get("change"),
                row.get("change_percent"),
                str(row.get("source") or source),
                timestamp,
            )
        )

    if not values:
        return 0

    conn = sqlite3.connect(Path(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO fund_prices (
                fund_code, price_date, nav, change_amount, change_percent, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fund_code, price_date) DO UPDATE SET
                nav = excluded.nav,
                change_amount = excluded.change_amount,
                change_percent = excluded.change_percent,
                source = excluded.source
            """,
            values,
        )
        conn.commit()
    finally:
        conn.close()
    return len(values)


def get_fund_price_on_or_before(fund_code, target_date, db_path=DB_PATH):
    init_db(db_path)
    normalized_code = _normalize_fund_code(fund_code)
    normalized_date = _parse_date(target_date).isoformat()
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT fund_code, price_date, nav, change_amount, change_percent, source, created_at
            FROM fund_prices
            WHERE fund_code = ? AND price_date <= ?
            ORDER BY price_date DESC
            LIMIT 1
            """,
            (normalized_code, normalized_date),
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
        cursor.close()
    finally:
        conn.close()
    return result


def list_investment_transactions(investment_type, db_path=DB_PATH):
    init_db(db_path)
    normalized_type = _investment_transaction_type(investment_type)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT
                t.id,
                t.investment_type,
                t.fund_code,
                COALESCE(NULLIF(f.fund_name_main, ''), NULLIF(f.fund_name, ''), '') AS fund_name,
                t.trade_date,
                t.nav_date,
                t.nav,
                t.amount,
                t.units,
                t.source_plan_id,
                t.created_at,
                t.updated_at
            FROM investment_transactions AS t
            LEFT JOIN funds AS f ON f.fund_code = t.fund_code
            WHERE t.investment_type = ?
            ORDER BY t.trade_date DESC, t.id DESC
            """,
            (normalized_type,),
        )
        result = [dict(row) for row in cursor.fetchall()]
        cursor.close()
    finally:
        conn.close()
    return result


def create_investment_transaction(
    investment_type,
    fund_code,
    trade_date,
    amount,
    units=None,
    source_plan_id=None,
    db_path=DB_PATH,
    today=None,
):
    init_db(db_path)
    normalized_type = _investment_transaction_type(investment_type)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_date = _parse_date(trade_date, "交易日期")
    if normalized_date > _today(today):
        raise ValueError("交易/基準日期不可晚於今天")
    normalized_amount = _coerce_positive_int(amount)
    price = get_fund_price_on_or_before(normalized_code, normalized_date, db_path)
    if price is None:
        raise ValueError("找不到交易/基準日前可用淨值")
    nav = _coerce_positive_float(price["nav"], "淨值")

    if normalized_type == "holdings":
        normalized_units = _coerce_positive_float(units, "現有單位數")
    else:
        normalized_units = normalized_amount / nav

    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            """
            INSERT INTO investment_transactions (
                investment_type, fund_code, trade_date, nav_date, nav,
                amount, units, source_plan_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_type,
                normalized_code,
                normalized_date.isoformat(),
                price["price_date"],
                nav,
                normalized_amount,
                normalized_units,
                source_plan_id,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("投資交易已存在") from exc
    finally:
        conn.close()
    return _fetch_transaction(row_id, db_path)


def update_investment_transaction(
    investment_type,
    row_id,
    fund_code,
    trade_date,
    amount,
    units=None,
    db_path=DB_PATH,
    today=None,
):
    init_db(db_path)
    normalized_type = _investment_transaction_type(investment_type)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_date = _parse_date(trade_date, "交易日期")
    if normalized_date > _today(today):
        raise ValueError("交易/基準日期不可晚於今天")
    normalized_amount = _coerce_positive_int(amount)
    price = get_fund_price_on_or_before(normalized_code, normalized_date, db_path)
    if price is None:
        raise ValueError("找不到交易/基準日前可用淨值")
    nav = _coerce_positive_float(price["nav"], "淨值")
    normalized_units = (
        _coerce_positive_float(units, "現有單位數")
        if normalized_type == "holdings"
        else normalized_amount / nav
    )
    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            """
            UPDATE investment_transactions
            SET fund_code = ?, trade_date = ?, nav_date = ?, nav = ?,
                amount = ?, units = ?, updated_at = ?
            WHERE id = ? AND investment_type = ?
            """,
            (
                normalized_code,
                normalized_date.isoformat(),
                price["price_date"],
                nav,
                normalized_amount,
                normalized_units,
                timestamp,
                int(row_id),
                normalized_type,
            ),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise ValueError("找不到投資交易資料")
    except sqlite3.IntegrityError as exc:
        raise ValueError("投資交易已存在") from exc
    finally:
        conn.close()
    return _fetch_transaction(row_id, db_path)


def delete_investment_transaction(investment_type, row_id, db_path=DB_PATH):
    init_db(db_path)
    normalized_type = _investment_transaction_type(investment_type)
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            "DELETE FROM investment_transactions WHERE id = ? AND investment_type = ?",
            (int(row_id), normalized_type),
        )
        conn.commit()
        deleted = cursor.rowcount > 0
    finally:
        conn.close()
    return deleted


def create_recurring_investment_plan(fund_code, amount, start_date, end_date=None, days=None, db_path=DB_PATH):
    init_db(db_path)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_amount = _coerce_positive_int(amount)
    normalized_start = _parse_date(start_date, "開始日")
    normalized_end = None if end_date in (None, "") else _parse_date(end_date, "結束日")
    if normalized_end is not None and normalized_end < normalized_start:
        raise ValueError("結束日不可早於開始日")
    normalized_days = _normalize_days(days)
    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            """
            INSERT INTO recurring_investment_plans (
                fund_code, amount, start_date, end_date, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                normalized_code,
                normalized_amount,
                normalized_start.isoformat(),
                normalized_end.isoformat() if normalized_end else None,
                timestamp,
                timestamp,
            ),
        )
        plan_id = cursor.lastrowid
        conn.executemany(
            """
            INSERT INTO recurring_investment_plan_days (plan_id, day_of_month)
            VALUES (?, ?)
            """,
            [(plan_id, day) for day in normalized_days],
        )
        conn.commit()
    finally:
        conn.close()
    return _fetch_recurring_plan(plan_id, db_path)


def list_recurring_investment_plans(db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT id
            FROM recurring_investment_plans
            ORDER BY id
            """
        )
        plan_ids = [row["id"] for row in cursor.fetchall()]
        cursor.close()
    finally:
        conn.close()
    return [_fetch_recurring_plan(plan_id, db_path) for plan_id in plan_ids]


def update_recurring_investment_plan(row_id, fund_code, amount, start_date, end_date=None, days=None, db_path=DB_PATH):
    init_db(db_path)
    normalized_code = _ensure_fund_exists(fund_code, db_path)
    normalized_amount = _coerce_positive_int(amount)
    normalized_start = _parse_date(start_date, "開始日")
    normalized_end = None if end_date in (None, "") else _parse_date(end_date, "結束日")
    if normalized_end is not None and normalized_end < normalized_start:
        raise ValueError("結束日不可早於開始日")
    normalized_days = _normalize_days(days)
    timestamp = _utc_now_text()
    conn = sqlite3.connect(Path(db_path))
    try:
        cursor = conn.execute(
            """
            UPDATE recurring_investment_plans
            SET fund_code = ?, amount = ?, start_date = ?, end_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized_code,
                normalized_amount,
                normalized_start.isoformat(),
                normalized_end.isoformat() if normalized_end else None,
                timestamp,
                int(row_id),
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError("找不到定期定額計畫")
        conn.execute(
            "DELETE FROM recurring_investment_plan_days WHERE plan_id = ?",
            (int(row_id),),
        )
        conn.executemany(
            """
            INSERT INTO recurring_investment_plan_days (plan_id, day_of_month)
            VALUES (?, ?)
            """,
            [(int(row_id), day) for day in normalized_days],
        )
        conn.commit()
    finally:
        conn.close()
    return _fetch_recurring_plan(row_id, db_path)


def delete_recurring_investment_plan(row_id, db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.execute(
            "DELETE FROM recurring_investment_plan_days WHERE plan_id = ?",
            (int(row_id),),
        )
        cursor = conn.execute(
            "DELETE FROM recurring_investment_plans WHERE id = ?",
            (int(row_id),),
        )
        conn.commit()
        deleted = cursor.rowcount > 0
    finally:
        conn.close()
    return deleted


def _iter_months(start, end):
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def generate_recurring_transactions(plan_id, db_path=DB_PATH, today=None):
    init_db(db_path)
    plan = _fetch_recurring_plan(plan_id, db_path)
    if plan is None:
        raise ValueError("找不到定期定額計畫")
    if plan["status"] != "active":
        return []

    start = _parse_date(plan["start_date"], "開始日")
    end = _today(today)
    if plan["end_date"]:
        end = min(end, _parse_date(plan["end_date"], "結束日"))
    if end < start:
        return []

    created = []
    for year, month in _iter_months(start, end):
        last_day = monthrange(year, month)[1]
        for day in plan["days"]:
            if day > last_day:
                continue
            trade_date = date(year, month, day)
            if trade_date < start or trade_date > end:
                continue
            try:
                created.append(
                    create_investment_transaction(
                        "recurring",
                        plan["fund_code"],
                        trade_date=trade_date,
                        amount=plan["amount"],
                        source_plan_id=plan["id"],
                        db_path=db_path,
                        today=end,
                    )
                )
            except ValueError as exc:
                if "已存在" not in str(exc):
                    raise
    return created


def upsert_funds(rows, db_path=DB_PATH):
    init_db(db_path)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = []
    for row in rows:
        cleaned = {field: str(row.get(field, "")).strip() for field in FUND_FIELDS}
        if not cleaned["fund_code"]:
            continue
        values.append(
            (
                cleaned["fund_code"],
                cleaned["market"],
                cleaned["fund_company"],
                cleaned["fund_id"],
                cleaned["fund_name_main"],
                cleaned["base_code"],
                cleaned["can_sell"],
                cleaned["fund_name"],
                updated_at,
            )
        )

    if not values:
        return 0

    conn = sqlite3.connect(Path(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO funds (
                fund_code, market, fund_company, fund_id, fund_name_main,
                base_code, can_sell, fund_name, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fund_code) DO UPDATE SET
                market = excluded.market,
                fund_company = excluded.fund_company,
                fund_id = excluded.fund_id,
                fund_name_main = excluded.fund_name_main,
                base_code = excluded.base_code,
                can_sell = excluded.can_sell,
                fund_name = excluded.fund_name,
                updated_at = excluded.updated_at
            """,
            values,
        )
        conn.commit()
    finally:
        conn.close()
    return len(values)


def get_fund_by_code(fund_code, db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT
                market, fund_company, fund_id, fund_name_main, base_code,
                can_sell, fund_code, fund_name, updated_at
            FROM funds
            WHERE fund_code = ?
            """,
            (str(fund_code).strip().upper(),),
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
        cursor.close()
    finally:
        conn.close()
    return result


def get_fund_domain_by_code(fund_code, db_path=DB_PATH):
    row = get_fund_by_code(fund_code, db_path)
    if row is None:
        return None
    return fund_from_row(row)


def list_fund_holding_domains(setting_type, db_path=DB_PATH):
    rows = list_investment_settings(setting_type, db_path)
    return [fund_holding_from_setting_row(row, setting_type) for row in rows]


def save_fund_list_update_status(status, message, started_at=None, finished_at=None, db_path=DB_PATH):
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fund_list_update_runs (
                status, message, started_at, finished_at, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(status).strip(),
                str(message).strip(),
                started_at,
                finished_at,
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_fund_list_update_status(db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(Path(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT status, message, started_at, finished_at
            FROM fund_list_update_runs
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
        cursor.close()
    finally:
        conn.close()
    return result
