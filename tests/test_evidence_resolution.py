from datetime import date

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.models import IPORecord


def test_official_uses_full_year_and_enhanced_uses_latest_period():
    record = IPORecord("03752", "珞石机器人")
    record.set_field("revenue", 522_000_000, "https://hkex.test/p.pdf", "HKEX 招股书", source_tier="A", period="FY2025", currency="RMB")
    record.set_field("net_profit", -179_000_000, "https://hkex.test/p.pdf", "HKEX 招股书", source_tier="A", period="FY2025", currency="RMB")
    record.set_field("revenue", 200_000_000, "https://futu.test", "Futu Financials", source_tier="B", period="Q1-2026", currency="RMB")
    record.set_field("net_profit", -50_000_000, "https://futu.test", "Futu Financials", source_tier="B", period="Q1-2026", currency="RMB")

    official = record.resolved("official")
    enhanced = record.resolved("enhanced")

    assert official.value("revenue") == 522_000_000
    assert official.value("net_profit") == -179_000_000
    assert enhanced.value("revenue") == 200_000_000
    assert enhanced.value("net_profit") == -50_000_000
    assert enhanced.value("net_margin_pct") == -25.0


def test_media_is_excluded_from_official_but_allowed_in_enhanced():
    record = IPORecord("00001", "示例")
    record.set_field("gross_margin_latest", 40.0, "https://media.test", "新浪财经（引述招股书）", source_tier="B", period="FY2025", currency="RMB")
    assert record.resolved("official").value("gross_margin_latest") is None
    assert record.resolved("enhanced").value("gross_margin_latest") == 40.0


def test_pre_listing_grey_market_is_not_missing_penalty():
    record = IPORecord("00001", "示例")
    for field in ScoringModel._applicable_core_fields(record, date(2026, 7, 1)):
        record.set_field(field, 1, "https://hkex.test", "HKEX 招股书", source_tier="A")
    record.set_field("listing_date", "2026-07-10", "https://hkex.test", "HKEX 招股书", source_tier="A")
    model = ScoringModel()
    before = model.score(record, date(2026, 7, 1))
    after = model.score(record, date(2026, 7, 11))
    assert before.confidence > after.confidence


def test_explicit_zero_and_false_are_not_missing():
    record = IPORecord("00001", "无基石示例")
    record.set_field("cornerstone_count", 0, "https://hkex.test", "HKEX 招股书", source_tier="A")
    record.set_field("cornerstone_ratio", 0, "https://hkex.test", "HKEX 招股书", source_tier="A")
    record.set_field("greenshoe", False, "https://hkex.test", "HKEX 招股书", source_tier="A")
    assert record.missing_fields(["cornerstone_count", "cornerstone_ratio", "greenshoe"]) == []
