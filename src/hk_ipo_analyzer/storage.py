from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from hk_ipo_analyzer.models import IPORecord, ScoreResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS ipo_daily (
  report_date TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  company_name TEXT NOT NULL,
  total_score REAL NOT NULL,
  recommendation TEXT NOT NULL,
  confidence REAL NOT NULL,
  record_json TEXT NOT NULL,
  score_json TEXT NOT NULL,
  PRIMARY KEY (report_date, stock_code)
);
CREATE TABLE IF NOT EXISTS field_evidence (
  report_date TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  field_name TEXT NOT NULL,
  value_json TEXT,
  source_url TEXT,
  source_name TEXT,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (report_date, stock_code, field_name)
);
"""


class SQLiteStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript(SCHEMA)

    def save(self, report_date: date, record: IPORecord, score: ScoreResult) -> None:
        from dataclasses import asdict

        day = report_date.isoformat()
        self.connection.execute(
            "INSERT OR REPLACE INTO ipo_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                day, record.stock_code, record.company_name, score.total,
                score.recommendation, score.confidence,
                json.dumps(record.to_dict(), ensure_ascii=False),
                json.dumps(asdict(score), ensure_ascii=False),
            ),
        )
        for name, item in record.fields.items():
            self.connection.execute(
                "INSERT OR REPLACE INTO field_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day, record.stock_code, name, json.dumps(item.value, ensure_ascii=False),
                 item.source_url, item.source_name, item.fetched_at),
            )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def save_raw_json(raw_dir: Path, report_date: date, record: IPORecord) -> Path:
    target_dir = raw_dir / report_date.isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{record.stock_code}.json"
    target.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target

