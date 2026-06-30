from __future__ import annotations

from hk_ipo_analyzer.analysis.recommendation import apply_recommendation
from hk_ipo_analyzer.models import IPORecord, ScoreResult


CORE_FIELDS = [
    "revenue_growth_pct",
    "net_margin_pct",
    "gross_margin_latest",
    "operating_cash_flow",
    "debt_to_assets_pct",
    "customer_concentration_top5",
    "sector",
    "peer_median_first_day_return_pct",
    "offer_size_hkd",
    "public_offer_ratio",
    "market_cap_hkd",
    "greenshoe",
    "sponsor_quality_score",
    "valuation_score",
    "cornerstone_count",
    "cornerstone_ratio",
    "cornerstone_quality_score",
    "cornerstone_lockup_months",
    "margin_amount_hkd",
    "margin_multiple",
    "expected_oversubscription",
    "grey_market_return_pct",
    "news_heat_score",
]


def _band(value, bands: list[tuple[float, float]], default: float = 0.0) -> float:
    if value is None:
        return default
    for threshold, score in bands:
        if float(value) >= threshold:
            return score
    return default


class ScoringModel:
    """确定性评分。缺失字段不获分，并通过缺失风险进一步扣分。"""

    def __init__(self, hot_sectors: list[str] | None = None, max_missing_penalty: int = 8):
        self.hot_sectors = set(hot_sectors or [])
        self.max_missing_penalty = max_missing_penalty

    def score(self, r: IPORecord) -> ScoreResult:
        explanations: dict[str, list[str]] = {key: [] for key in ("fundamentals", "sector", "offer_structure", "cornerstone", "market_heat", "risk")}
        fundamentals = self._fundamentals(r, explanations["fundamentals"])
        sector = self._sector(r, explanations["sector"])
        offer = self._offer(r, explanations["offer_structure"])
        cornerstone = self._cornerstone(r, explanations["cornerstone"])
        heat = self._heat(r, explanations["market_heat"])
        missing_ratio = len(r.missing_fields(CORE_FIELDS)) / len(CORE_FIELDS)
        risk = self._risk(r, missing_ratio, explanations["risk"])
        base_90 = fundamentals + sector + offer + cornerstone + heat
        total = max(0.0, min(100.0, base_90 / 90.0 * 100.0 - risk))
        result = ScoreResult(
            fundamentals=round(fundamentals, 1), sector=round(sector, 1),
            offer_structure=round(offer, 1), cornerstone=round(cornerstone, 1),
            market_heat=round(heat, 1), risk_deduction=round(risk, 1),
            total=round(total, 1), confidence=round(1.0 - missing_ratio, 2),
            explanations=explanations,
        )
        return apply_recommendation(result)

    def _fundamentals(self, r: IPORecord, notes: list[str]) -> float:
        growth = _band(r.value("revenue_growth_pct"), [(30, 6), (15, 4.5), (5, 3), (0, 1.5)])
        margin = _band(r.value("net_margin_pct"), [(15, 6), (8, 4.5), (0, 3), (-10, 1)])
        gross = _band(r.value("gross_margin_latest"), [(50, 4), (30, 3), (15, 2), (0, 1)])
        ocf = r.value("operating_cash_flow")
        cash = 4 if ocf is not None and ocf > 0 else (1 if ocf is not None else 0)
        debt = r.value("debt_to_assets_pct")
        stability = _band(None if debt is None else 100 - debt, [(70, 3), (50, 2), (30, 1)])
        concentration = r.value("customer_concentration_top5")
        quality = 2 if concentration is not None and concentration < 30 else (1 if concentration is not None and concentration < 50 else 0)
        notes.append(f"增长{growth:g}、盈利{margin:g}、毛利{gross:g}、现金流{cash:g}、稳健性{stability:g}、集中度{quality:g}")
        return growth + margin + gross + cash + stability + quality

    def _sector(self, r: IPORecord, notes: list[str]) -> float:
        sector_name = r.value("sector")
        hot = 5 if sector_name in self.hot_sectors else (2 if sector_name else 0)
        growth = _band(r.value("industry_growth_pct"), [(20, 4), (10, 3), (3, 2), (0, 1)])
        policy = max(-3, min(3, float(r.value("policy_score", 0) or 0)))
        peers = _band(r.value("peer_median_first_day_return_pct"), [(20, 3), (5, 2), (0, 1)])
        notes.append(f"赛道{hot:g}、行业空间{growth:g}、政策{policy:g}、近期同行{peers:g}")
        return max(0, min(15, hot + growth + policy + peers))

    def _offer(self, r: IPORecord, notes: list[str]) -> float:
        size = r.value("offer_size_hkd")
        scale = 3 if size is not None and 5e8 <= size <= 5e9 else (1.5 if size is not None else 0)
        public = r.value("public_offer_ratio")
        public_score = 3 if public is not None and 10 <= public <= 30 else (1 if public is not None else 0)
        market_cap = r.value("market_cap_hkd")
        float_score = 3 if market_cap is not None and market_cap >= 2e9 else (1 if market_cap is not None else 0)
        greenshoe = 2 if r.value("greenshoe") is True else 0
        sponsor = max(0, min(2, float(r.value("sponsor_quality_score", 0) or 0)))
        valuation = max(-3, min(2, float(r.value("valuation_score", 0) or 0)))
        notes.append(f"规模{scale:g}、公开发售{public_score:g}、流通结构{float_score:g}、绿鞋{greenshoe:g}、保荐人{sponsor:g}、定价{valuation:g}")
        return max(0, min(15, scale + public_score + float_score + greenshoe + sponsor + valuation))

    def _cornerstone(self, r: IPORecord, notes: list[str]) -> float:
        count = _band(r.value("cornerstone_count"), [(8, 5), (4, 4), (1, 2)])
        ratio_value = r.value("cornerstone_ratio")
        ratio = 4 if ratio_value is not None and 25 <= ratio_value <= 55 else (2 if ratio_value is not None else 0)
        quality = max(0, min(4, float(r.value("cornerstone_quality_score", 0) or 0)))
        lockup = _band(r.value("cornerstone_lockup_months"), [(12, 2), (6, 1.5), (3, 0.5)])
        notes.append(f"数量{count:g}、占比{ratio:g}、质量{quality:g}、锁定期{lockup:g}")
        return min(15, count + ratio + quality + lockup)

    def _heat(self, r: IPORecord, notes: list[str]) -> float:
        amount = _band(r.value("margin_amount_hkd"), [(20e9, 5), (5e9, 4), (1e9, 2.5), (1e8, 1)])
        multiple = _band(r.value("margin_multiple"), [(100, 5), (30, 4), (10, 3), (3, 1.5)])
        over = r.value("actual_oversubscription", r.value("expected_oversubscription"))
        subscription = _band(over, [(100, 4), (30, 3), (10, 2), (1, 1)])
        grey_value = r.value("grey_market_return_pct")
        grey = _band(grey_value, [(15, 3), (5, 2), (0, 1)])
        news_raw = r.value("news_heat_score")
        news = max(0, min(3, float(news_raw))) if news_raw is not None else 0
        notes.append(f"融资额{amount:g}、融资倍数{multiple:g}、超购{subscription:g}、暗盘{grey:g}、关注度{news:g}")
        return min(20, amount + multiple + subscription + grey + news)

    def _risk(self, r: IPORecord, missing_ratio: float, notes: list[str]) -> float:
        deductions = 0.0
        mapping: dict[str, float] = {
            "持续亏损": 5, "收入大幅波动": 3, "客户高度集中": 3,
            "估值明显偏贵": 5, "监管风险": 5, "诉讼合规": 5,
            "研发失败": 3, "冷门小票": 4,
        }
        for tag in r.risk_tags:
            if tag in mapping:
                deductions += mapping[tag]
                notes.append(f"{tag} -{mapping[tag]:g}")
        missing = round(min(self.max_missing_penalty, missing_ratio * self.max_missing_penalty), 1)
        if missing:
            deductions += missing
            notes.append(f"核心数据缺失率 {missing_ratio:.0%}，-{missing:g}")
        return min(20, deductions)
