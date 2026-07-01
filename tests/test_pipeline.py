from datetime import date
import json

from hk_ipo_analyzer.models import IPORecord
from hk_ipo_analyzer.pipeline import DailyPipeline


def _record(code: str, start=None, end=None) -> IPORecord:
    record = IPORecord(code, f"公司{code}")
    if start is not None:
        record.set_field("offer_start_date", start, "https://example.test", "测试")
    if end is not None:
        record.set_field("offer_end_date", end, "https://example.test", "测试")
    return record


def test_filter_current_offers_requires_verified_active_window():
    records = [
        _record("0001", "2026-06-29", "2026-07-03"),
        _record("0002", "2026-06-20", "2026-06-25"),
        _record("0003"),
    ]

    result = DailyPipeline._filter_current_offers(records, date(2026, 6, 30))

    assert [record.stock_code for record in result] == ["0001"]


def test_load_compact_verified_input(tmp_path):
    path = tmp_path / "verified.json"
    path.write_text(json.dumps({"records": [{
        "stock_code": "1",
        "company_name": "核验公司",
        "risk_tags": ["持续亏损"],
        "source_url": "https://example.test/source",
        "source_name": "核验来源",
        "verified_fields": {"offer_start_date": "2026-06-30", "board_lot": 100},
    }]}), encoding="utf-8")

    record = DailyPipeline._load_input(path)[0]

    assert record.stock_code == "0001"
    assert record.value("board_lot") == 100
    assert record.fields["board_lot"].source_name == "核验来源"
    assert record.risk_tags == ["持续亏损"]


def test_load_compact_input_attaches_official_prospectus(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"records": [{
        "stock_code": "02249",
        "company_name": "晶合集成",
        "prospectus_url": "https://www.hkexnews.hk/prospectus.htm",
        "verified_fields": {"offer_start_date": "2026-06-30"},
    }]}), encoding="utf-8")

    record = DailyPipeline._load_input(path)[0]

    assert record.documents[0]["document_type"] == "prospectus"
    assert record.documents[0]["url"] == "https://www.hkexnews.hk/prospectus.htm"


def test_load_compact_input_accepts_field_level_evidence(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"records": [{
        "stock_code": "02249",
        "company_name": "晶合集成",
        "source_url": "https://example.test/common",
        "verified_fields": {
            "cornerstone_ratio": {
                "value": 49.92,
                "source_url": "https://example.test/cornerstone",
                "source_name": "字段核验来源",
            },
        },
    }]}), encoding="utf-8")

    record = DailyPipeline._load_input(path)[0]

    assert record.value("cornerstone_ratio") == 49.92
    assert record.fields["cornerstone_ratio"].source_url.endswith("/cornerstone")
    assert record.fields["cornerstone_ratio"].source_name == "字段核验来源"
