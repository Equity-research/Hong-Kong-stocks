import csv
from datetime import date

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.models import IPORecord
from hk_ipo_analyzer.reporting import render_markdown, update_summary_csv


def test_report_contains_disclaimer_and_missing_data():
    record = IPORecord("0001", "示例公司")
    score = ScoringModel().score(record)
    report = render_markdown(date(2026, 6, 30), [(record, score, score)])
    assert "仅供研究，不构成投资建议" in report
    assert "## 数据缺失项" in report
    assert "当日真实可申购：1 只" in report
    assert "0001" in report


def test_summary_replaces_the_whole_report_date(tmp_path):
    path = tmp_path / "summary.csv"
    first = IPORecord("0001", "旧记录")
    first.set_field("offer_start_date", "2026-06-30", "https://example.test", "测试")
    first_score = ScoringModel().score(first)
    update_summary_csv(path, date(2026, 6, 30), [(first, first_score, first_score)])

    second = IPORecord("0002", "新记录")
    second.set_field("offer_start_date", "2026-06-30", "https://example.test", "测试")
    second_score = ScoringModel().score(second)
    update_summary_csv(path, date(2026, 7, 1), [(second, second_score, second_score)])

    text = path.read_text(encoding="utf-8-sig")
    assert "0001" not in text
    assert "0002" in text
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert {row["report_date"] for row in rows} == {"2026-07-01"}
