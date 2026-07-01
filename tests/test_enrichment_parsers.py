from hk_ipo_analyzer.ipo_parser.cornerstone_parser import CornerstoneParser
from hk_ipo_analyzer.ipo_parser.financial_parser import FinancialParser
from hk_ipo_analyzer.ipo_parser.offer_structure_parser import OfferStructureParser
from hk_ipo_analyzer.models import IPORecord


def test_financial_parser_extracts_latest_series_and_derived_metrics():
    text = (
        "收入分别为人民币7,183 million、9,120 million及10,388 million。"
        "净利润分别为人民币119 million、482 million及466 million。毛利率为22.7%。"
    )
    record = IPORecord("02249", "晶合集成")
    FinancialParser().parse(text, record, "https://example.test/prospectus.pdf")
    assert record.value("revenue") == 10_388_000_000
    assert record.value("net_profit") == 466_000_000
    assert record.value("revenue_growth_pct") == 13.9
    assert record.value("net_margin_pct") == 4.49
    assert record.value("gross_margin_latest") == 22.7
    assert record.value("financial_currency") == "RMB"


def test_offer_structure_parser_distinguishes_greenshoe_and_adjustment_option():
    source = "https://example.test/prospectus.pdf"
    record = IPORecord("01770", "东方科脉")
    OfferStructureParser().parse(
        "香港公開發售佔全球發售約10.0%，視乎超額配股權行使與否。", record, source
    )
    assert record.value("greenshoe") is True
    assert record.value("public_offer_ratio") == 10.0

    gem = IPORecord("08090", "宝盖新材料")
    OfferStructureParser().parse("股份發售數目視乎發售量調整權行使與否。", gem, source)
    assert gem.value("greenshoe") is False


def test_cornerstone_parser_extracts_explicit_count_ratio_and_hkd_amount():
    text = (
        "基石投資者\n本公司已有20名基石投資者。基石投資者將認購港元3,372 million，"
        "約佔全球發售49.92%。禁售期為6個月。"
    )
    record = IPORecord("02249", "晶合集成")
    CornerstoneParser().parse(text, record, "https://example.test/prospectus.pdf")
    assert record.value("cornerstone_count") == 20
    assert record.value("cornerstone_ratio") == 49.92
    assert record.value("cornerstone_amount_hkd") == 3_372_000_000
    assert record.value("cornerstone_lockup_months") == 6
