from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient

LOGGER = logging.getLogger(__name__)

HKEX_NEWLY_LISTED_URL = (
    "https://www.hkex.com.hk/Services/Trading/Securities/Trading-News/"
    "Newly-Listed-Securities?sc_lang=zh-HK"
)

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_ipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    company_name TEXT NOT NULL,
    sector TEXT,
    listing_date TEXT NOT NULL,
    offer_price REAL,
    first_day_close REAL,
    first_day_return_pct REAL,
    first_day_high REAL,
    first_day_low REAL,
    first_day_volume INTEGER,
    market_cap_hkd REAL,
    offer_size_hkd REAL,
    public_oversubscription REAL,
    fetched_at TEXT NOT NULL,
    source_url TEXT,
    UNIQUE(stock_code)
);

CREATE TABLE IF NOT EXISTS peer_statistics (
    sector TEXT NOT NULL PRIMARY KEY,
    ipo_count INTEGER,
    median_first_day_return REAL,
    mean_first_day_return REAL,
    break_even_rate REAL,
    avg_oversubscription REAL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_historical_sector ON historical_ipos(sector);
CREATE INDEX IF NOT EXISTS idx_historical_date ON historical_ipos(listing_date);
"""


def _safe_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(text).strip())
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class HistoricalDB:
    """历史 IPO 数据库：存储已上市公司首日表现并计算板块同行统计。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            conn.executescript(DB_SCHEMA)
            conn.commit()

    def insert_ipo(self, data: dict[str, Any]) -> None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO historical_ipos
                   (stock_code, company_name, sector, listing_date, offer_price,
                    first_day_close, first_day_return_pct, first_day_high, first_day_low,
                    first_day_volume, market_cap_hkd, offer_size_hkd, public_oversubscription,
                    fetched_at, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["stock_code"], data["company_name"], data.get("sector"),
                    data["listing_date"], data.get("offer_price"),
                    data.get("first_day_close"), data.get("first_day_return_pct"),
                    data.get("first_day_high"), data.get("first_day_low"),
                    data.get("first_day_volume"), data.get("market_cap_hkd"),
                    data.get("offer_size_hkd"), data.get("public_oversubscription"),
                    data["fetched_at"], data.get("source_url"),
                ),
            )
            conn.commit()

    def recompute_peer_stats(self) -> None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            conn.execute("DELETE FROM peer_statistics")
            conn.execute(
                """INSERT INTO peer_statistics
                   SELECT sector, COUNT(*) AS ipo_count,
                          COALESCE(AVG(CASE WHEN first_day_return_pct IS NOT NULL
                              THEN first_day_return_pct END), 0) AS median_first_day,
                          ROUND(AVG(CASE WHEN first_day_return_pct IS NOT NULL
                              THEN first_day_return_pct END), 2) AS mean_first_day,
                          ROUND(SUM(CASE WHEN first_day_return_pct IS NOT NULL
                              AND first_day_return_pct < 0 THEN 1 ELSE 0 END) * 100.0 /
                              NULLIF(COUNT(*), 0), 1) AS break_even_rate,
                          ROUND(AVG(public_oversubscription), 1) AS avg_oversubscription,
                          datetime('now') AS updated_at
                   FROM historical_ipos
                   WHERE sector IS NOT NULL AND first_day_return_pct IS NOT NULL
                   GROUP BY sector"""
            )
            conn.commit()

    def get_peer_return(self, sector: str) -> float | None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            row = conn.execute(
                "SELECT median_first_day_return FROM peer_statistics WHERE sector = ?",
                (sector,),
            ).fetchone()
            return row[0] if row and row[0] != 0 else None

    def get_break_even_rate(self, sector: str) -> float | None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            row = conn.execute(
                "SELECT break_even_rate FROM peer_statistics WHERE sector = ?",
                (sector,),
            ).fetchone()
            return row[0] if row else None

    def get_sponsor_performance(self, sponsor_name: str) -> dict[str, Any] | None:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            row = conn.execute(
                """SELECT COUNT(*), AVG(first_day_return_pct)
                   FROM historical_ipos
                   WHERE company_name LIKE ? AND first_day_return_pct IS NOT NULL""",
                (f"%{sponsor_name}%",),
            ).fetchone()
            if row and row[0]:
                return {"count": row[0], "avg_return": round(row[1], 2) if row[1] else 0}
            return None

    def count(self) -> int:
        db_path_str = str(self.db_path)
        with sqlite3.connect(db_path_str) as conn:
            return conn.execute("SELECT COUNT(*) FROM historical_ipos").fetchone()[0]


class HistoricalFetcher:
    """从 HKEX 新上市证券页面抓取历史 IPO 数据。"""

    def __init__(self, client: PoliteHttpClient, db: HistoricalDB):
        self.client = client
        self.db = db

    def fetch_recent(self, days_back: int = 730) -> int:
        """抓取最近 N 天内的新上市证券数据，返回新增条数"""
        try:
            resp = self.client.get(HKEX_NEWLY_LISTED_URL)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            count = 0
            rows = soup.select("table tbody tr") or soup.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                stock_code = cells[0].get_text(strip=True)
                if not re.match(r"^\d{4,5}$", stock_code):
                    continue
                company_name = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                listing_date_str = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                listing_date = self._parse_date(listing_date_str)
                if not listing_date:
                    continue
                cutoff = date.today() - timedelta(days=days_back)
                if listing_date < cutoff:
                    continue
                data = {
                    "stock_code": stock_code.zfill(5),
                    "company_name": company_name,
                    "listing_date": listing_date.isoformat(),
                    "fetched_at": datetime.now().isoformat(),
                    "source_url": HKEX_NEWLY_LISTED_URL,
                }
                if len(cells) > 3:
                    data["offer_price"] = _safe_float(cells[3].get_text(strip=True))
                self.db.insert_ipo(data)
                count += 1
            if count:
                self.db.recompute_peer_stats()
            LOGGER.info("历史 IPO 数据已更新：新增 %s 条，总计 %s 条", count, self.db.count())
            return count
        except Exception:
            LOGGER.warning("历史 IPO 抓取失败", exc_info=True)
            return 0

    @staticmethod
    def _parse_date(text: str) -> date | None:
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"]:
            try:
                return datetime.strptime(text.strip(), fmt).date()
            except ValueError:
                continue
        return None
