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
        conn.commit()
    finally:
        conn.close()


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
