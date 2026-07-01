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
CREATE TABLE IF NOT EXISTS field_evidence_candidates (
  report_date TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  field_name TEXT NOT NULL,
  candidate_index INTEGER NOT NULL,
  value_json TEXT,
  source_url TEXT,
  source_name TEXT,
  fetched_at TEXT NOT NULL,
  source_tier TEXT NOT NULL,
  period TEXT,
  currency TEXT,
  confidence REAL,
  PRIMARY KEY (report_date, stock_code, field_name, candidate_index)
);
"""


class SQLiteStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript(SCHEMA)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        existing = {row[1] for row in self.connection.execute("PRAGMA table_info(ipo_daily)")}
        additions = {
            "enhanced_score": "REAL",
            "enhanced_recommendation": "TEXT",
            "enhanced_confidence": "REAL",
        }
        for name, column_type in additions.items():
            if name not in existing:
                self.connection.execute(f"ALTER TABLE ipo_daily ADD COLUMN {name} {column_type}")
        self.connection.commit()

    def save(self, report_date: date, record: IPORecord, official_score: ScoreResult, enhanced_score: ScoreResult) -> None:
        from dataclasses import asdict

        day = report_date.isoformat()
        self.connection.execute(
            """INSERT OR REPLACE INTO ipo_daily
               (report_date, stock_code, company_name, total_score, recommendation, confidence,
                record_json, score_json, enhanced_score, enhanced_recommendation, enhanced_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                day, record.stock_code, record.company_name, official_score.total,
                official_score.recommendation, official_score.confidence,
                json.dumps(record.to_dict(), ensure_ascii=False),
                json.dumps({"official": asdict(official_score), "enhanced": asdict(enhanced_score)}, ensure_ascii=False),
                enhanced_score.total, enhanced_score.recommendation, enhanced_score.confidence,
            ),
        )
        for name, item in record.fields.items():
            self.connection.execute(
                "INSERT OR REPLACE INTO field_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day, record.stock_code, name, json.dumps(item.value, ensure_ascii=False),
                 item.source_url, item.source_name, item.fetched_at),
            )
        self.connection.execute(
            "DELETE FROM field_evidence_candidates WHERE report_date = ? AND stock_code = ?",
            (day, record.stock_code),
        )
        for name, candidates in record.evidence_candidates.items():
            for index, item in enumerate(candidates):
                self.connection.execute(
                    "INSERT INTO field_evidence_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (day, record.stock_code, name, index, json.dumps(item.value, ensure_ascii=False),
                     item.source_url, item.source_name, item.fetched_at, item.source_tier,
                     item.period, item.currency, item.confidence),
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
