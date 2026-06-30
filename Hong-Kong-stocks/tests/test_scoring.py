from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.models import IPORecord


def sourced_record() -> IPORecord:
    record = IPORecord("9999", "高质量示例公司")
    values = {
        "revenue_growth_pct": 35, "net_margin_pct": 18, "gross_margin_latest": 55,
        "operating_cash_flow": 500_000_000, "debt_to_assets_pct": 25,
        "customer_concentration_top5": 20, "sector": "AI", "industry_growth_pct": 25,
        "policy_score": 2, "peer_median_first_day_return_pct": 25,
        "offer_size_hkd": 2_000_000_000, "public_offer_ratio": 10,
        "market_cap_hkd": 10_000_000_000, "greenshoe": True,
        "sponsor_quality_score": 2, "valuation_score": 2, "cornerstone_count": 10,
        "cornerstone_ratio": 40, "cornerstone_quality_score": 4,
        "cornerstone_lockup_months": 12, "margin_amount_hkd": 30_000_000_000,
        "margin_multiple": 120, "expected_oversubscription": 150,
        "grey_market_return_pct": 18, "news_heat_score": 3,
    }
    for name, value in values.items():
        record.set_field(name, value, "https://example.test/source", "测试数据")
    return record


def test_high_quality_record_scores_high():
    score = ScoringModel(hot_sectors=["AI"]).score(sourced_record())
    assert score.total >= 85
    assert score.recommendation == "积极打新"
    assert score.confidence >= 0.95


def test_missing_record_is_penalized_and_low_confidence():
    score = ScoringModel(hot_sectors=["AI"]).score(IPORecord("0001", "缺失示例"))
    assert score.total < 55
    assert score.risk_deduction > 0
    assert score.confidence == 0

