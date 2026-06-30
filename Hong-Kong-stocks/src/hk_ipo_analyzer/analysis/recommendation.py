from __future__ import annotations

from hk_ipo_analyzer.models import ScoreResult


def apply_recommendation(result: ScoreResult) -> ScoreResult:
    score = result.total
    if score >= 85:
        result.recommendation = "积极打新"
        result.strategy = "可考虑现金一手或适度融资；先核算融资成本和预期中签率。"
    elif score >= 75:
        result.recommendation = "现金一手"
        result.strategy = "可以参与，优先现金一手，融资需谨慎。"
    elif score >= 65:
        result.recommendation = "谨慎一手"
        result.strategy = "仅适合小额参与，不建议高杠杆。"
    elif score >= 55:
        result.recommendation = "不建议打新"
        result.strategy = "标的偏弱，不建议融资，可等待更多数据。"
    else:
        result.recommendation = "放弃"
        result.strategy = "当前规则和已知数据不支持参与。"
    if result.confidence < 0.55:
        result.strategy += " 数据完整度较低，结论可信度有限。"
    return result

