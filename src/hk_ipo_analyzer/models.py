from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


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
    "financial_currency", "financial_period",
    "net_profit", "adjusted_net_profit", "net_margin_pct", "gross_margin_latest",
    "operating_cash_flow", "debt_to_assets_pct", "customer_concentration_top5",
    "supplier_concentration_top5", "rd_expense", "business_highlights", "industry_growth_pct",
    "policy_score", "peer_median_first_day_return_pct", "peer_median_pe", "issuer_pe",
    "sponsor_quality_score", "valuation_score", "issuer_ps", "peer_median_ps",
    "margin_amount_hkd", "margin_multiple",
    "expected_oversubscription", "actual_oversubscription", "grey_market_return_pct",
    "news_heat_score", "risk_tags",
]


@dataclass(slots=True)
class SourcedValue:
    value: Any = None
    source_url: str | None = None
    source_name: str | None = None
    fetched_at: str = field(default_factory=utc_now_iso)
    source_tier: str = "C"
    period: str | None = None
    currency: str | None = None
    confidence: float | None = None

    @property
    def missing(self) -> bool:
        return self.value is None or self.value == ""


@dataclass(slots=True)
class IPORecord:
    stock_code: str
    company_name: str
    fields: dict[str, SourcedValue] = field(default_factory=dict)
    evidence_candidates: dict[str, list[SourcedValue]] = field(default_factory=dict)
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
        source_tier: str | None = None,
        period: str | None = None,
        currency: str | None = None,
        confidence: float | None = None,
    ) -> None:
        candidate = SourcedValue(
            value=value,
            source_url=source_url,
            source_name=source_name,
            fetched_at=fetched_at or utc_now_iso(),
            source_tier=source_tier or infer_source_tier(source_name, source_url),
            period=period,
            currency=currency,
            confidence=confidence,
        )
        bucket = self.evidence_candidates.setdefault(name, [])
        if not any(_same_evidence(candidate, item) for item in bucket):
            bucket.append(candidate)
        current = self.fields.get(name)
        if current and not current.missing and not overwrite:
            return
        self.fields[name] = candidate

    def value(self, name: str, default: Any = None) -> Any:
        item = self.fields.get(name)
        return default if item is None or item.value is None else item.value

    def missing_fields(self, names: list[str]) -> list[str]:
        return [name for name in names if name not in self.fields or self.fields[name].missing]

    def fill_expected_nulls(self) -> None:
        for name in EXPECTED_FIELDS:
            if name not in self.fields:
                self.set_field(name, None, None, "未获取")

    def resolved(self, mode: Literal["official", "enhanced"]) -> "IPORecord":
        """按来源等级和财务期间生成用于评分的不可混期视图。"""
        record = IPORecord(self.stock_code, self.company_name, documents=list(self.documents), risk_tags=list(self.risk_tags))
        allowed = {"A"} if mode == "official" else {"A", "B"}
        operational = {"stock_code", "company_name", "offer_start_date", "offer_end_date", "pricing_date", "allotment_result_date", "listing_date", "sector", "business_description"}
        financial = {"revenue", "net_profit", "adjusted_net_profit", "revenue_growth_pct", "net_margin_pct", "gross_margin_latest", "operating_cash_flow", "debt_to_assets_pct"}
        target_period = self._select_financial_period(mode, allowed)
        for name in EXPECTED_FIELDS:
            candidates = [item for item in self.evidence_candidates.get(name, []) if not item.missing and (item.source_tier in allowed or name in operational)]
            if name in financial and target_period:
                exact = [item for item in candidates if item.period == target_period]
                candidates = exact or [item for item in candidates if item.period is None]
            if candidates:
                selected = sorted(candidates, key=lambda item: (_tier_rank(item.source_tier), item.fetched_at), reverse=True)[0]
                record.fields[name] = selected
                record.evidence_candidates[name] = list(self.evidence_candidates.get(name, []))
        if target_period:
            record.set_field("financial_period", target_period, None, "证据解析器", source_tier="A")
        currency = record.value("financial_currency")
        revenue = record.value("revenue")
        profit = record.value("net_profit")
        revenue_item = record.fields.get("revenue")
        profit_item = record.fields.get("net_profit")
        if revenue not in (None, 0) and profit is not None and revenue_item and profit_item:
            same_period = not revenue_item.period or not profit_item.period or revenue_item.period == profit_item.period
            same_currency = not revenue_item.currency or not profit_item.currency or revenue_item.currency == profit_item.currency
            if same_period and same_currency:
                record.set_field("net_margin_pct", round(float(profit) / float(revenue) * 100, 2), None, "同期间财务推导", source_tier="A", period=target_period, currency=currency)
        return record

    def _select_financial_period(self, mode: str, allowed: set[str]) -> str | None:
        periods = []
        for name in ("revenue", "net_profit", "gross_margin_latest"):
            periods.extend(item.period for item in self.evidence_candidates.get(name, []) if item.period and item.source_tier in allowed)
        if not periods:
            value = self.value("financial_period")
            return str(value) if value else None
        if mode == "official":
            full_year = [period for period in periods if _is_full_year(period)]
            return sorted(full_year or periods)[-1]
        return sorted(periods, key=_period_rank)[-1]

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
        for name, items in payload.get("evidence_candidates", {}).items():
            record.evidence_candidates[name] = [SourcedValue(**item) for item in items]
        if not record.evidence_candidates:
            record.evidence_candidates = {name: [item] for name, item in record.fields.items()}
        return record


def infer_source_tier(source_name: str | None, source_url: str | None) -> str:
    text = f"{source_name or ''} {source_url or ''}".lower()
    if any(token in text for token in ("hkex", "招股书", "招股章程", "公司公告", "发行人公告", "futu openapi", "futu openapi", "手工核验")):
        return "A"
    if any(token in text for token in (
        "etnet", "经济通", "富途", "futu", "aastocks", "新浪", "证券时报", "stcn",
        "财华", "搜狐", "凤凰", "华盛通", "hstong", "经济观察", "eeo.com.cn",
        "证券市场周刊", "seccw", "媒体",
    )):
        return "B"
    return "C"


def _same_evidence(left: SourcedValue, right: SourcedValue) -> bool:
    return left.value == right.value and left.source_url == right.source_url and left.period == right.period


def _tier_rank(tier: str) -> int:
    return {"A": 3, "B": 2, "C": 1}.get(tier, 0)


def _is_full_year(period: str) -> bool:
    upper = period.upper()
    return "FY" in upper and not any(token in upper for token in ("Q", "H", "M"))


def _period_rank(period: str) -> tuple[int, int]:
    import re
    year_match = re.search(r"20\d{2}", period)
    year = int(year_match.group()) if year_match else 0
    upper = period.upper()
    stage = 4 if "FY" in upper and not any(token in upper for token in ("Q", "H", "M")) else 3 if "Q4" in upper or "H2" in upper else 2 if "Q3" in upper else 1
    return year, stage


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
