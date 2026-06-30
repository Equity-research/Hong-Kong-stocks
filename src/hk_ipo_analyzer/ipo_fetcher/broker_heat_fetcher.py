from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from hk_ipo_analyzer.models import IPORecord


HEAT_FIELDS = {
    "margin_amount_hkd": float,
    "margin_multiple": float,
    "expected_oversubscription": float,
    "actual_oversubscription": float,
    "grey_market_return_pct": float,
    "news_heat_score": float,
}


class BrokerHeatFetcher:
    """首版只读取用户手工数据，不访问登录、付费墙或券商接口。"""

    def __init__(self, manual_csv: Path):
        self.manual_csv = manual_csv

    def apply(self, records: list[IPORecord], as_of: date) -> None:
        if not self.manual_csv.exists() or self.manual_csv.stat().st_size == 0:
            return
        frame = pd.read_csv(self.manual_csv, dtype={"stock_code": str})
        if frame.empty:
            return
        frame["stock_code"] = frame["stock_code"].str.zfill(4)
        frame["as_of_date"] = pd.to_datetime(frame["as_of_date"], errors="coerce").dt.date
        eligible = frame[frame["as_of_date"] <= as_of].sort_values("as_of_date")
        latest = eligible.groupby("stock_code", as_index=False).tail(1)
        rows = {row["stock_code"]: row for _, row in latest.iterrows()}
        for record in records:
            row = rows.get(record.stock_code)
            if row is None:
                continue
            url = None if pd.isna(row.get("source_url")) else str(row.get("source_url"))
            name = (
                "手工覆盖数据"
                if pd.isna(row.get("source_name"))
                else str(row.get("source_name"))
            )
            fetched_at = None if pd.isna(row.get("fetched_at")) else str(row.get("fetched_at"))
            for field_name, caster in HEAT_FIELDS.items():
                raw = row.get(field_name)
                value = None if pd.isna(raw) else caster(raw)
                record.set_field(field_name, value, url, name, fetched_at, overwrite=True)

