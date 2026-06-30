from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


EXPECTED_FIELDS = [
    "stock_code", "company_name", "sector", "business_description", "offer_start_date",
    "offer_end_date", "pricing_date", "allotment_result_date", "listing_date",
    "offer_price_low", "offer_price_high", "offer_price_range", "board_lot", "entry_fee_hkd",
    "offer_size_hkd", "public_offer_ratio", "international_offer_ratio", "clawback_mechanism",
    "market_cap_hkd", "greenshoe", "sponsors", "cornerstone_investors", "cornerstone_count",
    "cornerstone_amount_hkd", "cornerstone_ratio", "cornerstone_quality_score",
    "cornerstone_lockup_months", "use_of_proceeds", "revenue", "revenue_growth_pct",
    "net_profit", "adjusted_net_profit", "net_margin_pct", "gross_margin_latest",
    "operating_cash_flow", "debt_to_assets_pct", "customer_concentration_top5",
    "supplier_concentration_top5", "rd_expense", "business_highlights", "industry_growth_pct",
    "policy_score", "peer_median_first_day_return_pct", "peer_median_pe", "issuer_pe",
    "sponsor_quality_score", "valuation_score", "margin_amount_hkd", "margin_multiple",
    "expected_oversubscription", "actual_oversubscription", "grey_market_return_pct",
    "news_heat_score", "risk_tags",
]


@dataclass(slots=True)
class SourcedValue:
    value: Any = None
    source_url: str | None = None
    source_name: str | None = None
    fetched_at: str = field(default_factory=utc_now_iso)

    @property
    def missing(self) -> bool:
        return self.value is None or self.value == ""


@dataclass(slots=True)
class IPORecord:
    stock_code: str
    company_name: str
    fields: dict[str, SourcedValue] = field(default_factory=dict)
    documents: list[dict[str, Any]] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)

    def set_field(
        self,
        name: str,
        value: Any,
        source_url: str | None,
        source_name: str,
        fetched_at: str | None = None,
        overwrite: bool = False,
    ) -> None:
        current = self.fields.get(name)
        if current and not current.missing and not overwrite:
            return
        self.fields[name] = SourcedValue(
            value=value,
            source_url=source_url,
            source_name=source_name,
            fetched_at=fetched_at or utc_now_iso(),
        )

    def value(self, name: str, default: Any = None) -> Any:
        item = self.fields.get(name)
        return default if item is None or item.value is None else item.value

    def missing_fields(self, names: list[str]) -> list[str]:
        return [name for name in names if name not in self.fields or self.fields[name].missing]

    def fill_expected_nulls(self) -> None:
        for name in EXPECTED_FIELDS:
            if name not in self.fields:
                self.set_field(name, None, None, "未获取")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IPORecord":
        record = cls(
            stock_code=str(payload["stock_code"]).zfill(4),
            company_name=payload["company_name"],
            documents=payload.get("documents", []),
            risk_tags=payload.get("risk_tags", []),
        )
        for name, item in payload.get("fields", {}).items():
            record.fields[name] = SourcedValue(**item)
        return record


@dataclass(slots=True)
class ScoreResult:
    fundamentals: float
    sector: float
    offer_structure: float
    cornerstone: float
    market_heat: float
    risk_deduction: float
    total: float
    confidence: float
    explanations: dict[str, list[str]]
    recommendation: str = ""
    strategy: str = ""
