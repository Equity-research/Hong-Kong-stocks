from datetime import date

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.models import IPORecord
from hk_ipo_analyzer.reporting import render_markdown


def test_report_contains_disclaimer_and_missing_data():
    record = IPORecord("0001", "示例公司")
    score = ScoringModel().score(record)
    report = render_markdown(date(2026, 6, 30), [(record, score)])
    assert "仅供研究，不构成投资建议" in report
    assert "## 数据缺失项" in report
    assert "0001" in report

