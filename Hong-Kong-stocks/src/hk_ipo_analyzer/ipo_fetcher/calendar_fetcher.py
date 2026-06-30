from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from hk_ipo_analyzer.models import IPORecord


CALENDAR_FIELDS = (
    "offer_start_date",
    "offer_end_date",
    "pricing_date",
    "allotment_result_date",
    "listing_date",
)


class CalendarFetcher:
    """用同一手工模板补足关键日期；招股书解析结果优先保留。"""

    def __init__(self, manual_csv: Path):
        self.manual_csv = manual_csv

    def apply(self, records: list[IPORecord], as_of: date) -> None:
        if not self.manual_csv.exists():
            return
        frame = pd.read_csv(self.manual_csv, dtype={"stock_code": str})
        if frame.empty:
            return
        frame["stock_code"] = frame["stock_code"].str.zfill(4)
        frame["as_of_date"] = pd.to_datetime(frame["as_of_date"], errors="coerce").dt.date
        for record in records:
            matches = frame[
                (frame["stock_code"] == record.stock_code) & (frame["as_of_date"] <= as_of)
            ].sort_values("as_of_date")
            if matches.empty:
                continue
            row = matches.iloc[-1]
            source_url = None if pd.isna(row.get("source_url")) else str(row.get("source_url"))
            source_name = "手工日历" if pd.isna(row.get("source_name")) else str(row["source_name"])
            for name in CALENDAR_FIELDS:
                raw = row.get(name)
                value = None if pd.isna(raw) else str(raw)
                record.set_field(name, value, source_url, source_name)
