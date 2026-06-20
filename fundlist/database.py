import sqlite3
from datetime import datetime, timezone
from pathlib import Path


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


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_fund_exists(fund_code, db_path):
    normalized_code = _normalize_fund_code(fund_code)
    if get_fund_by_code(normalized_code, db_path) is None:
        raise ValueError("找不到此基金代號，請先更新基金清單")
    return normalized_code


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
