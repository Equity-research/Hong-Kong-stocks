from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from hk_ipo_analyzer.models import IPORecord, ScoreResult


DISPLAY_FIELDS = [
    "offer_start_date", "offer_end_date", "listing_date", "offer_price_range",
    "board_lot", "entry_fee_hkd", "offer_size_hkd", "sponsors", "business_description",
    "revenue", "revenue_growth_pct", "net_profit", "adjusted_net_profit", "net_margin_pct",
    "gross_margin_latest", "operating_cash_flow", "debt_to_assets_pct",
    "customer_concentration_top5", "cornerstone_investors", "cornerstone_amount_hkd",
    "cornerstone_ratio", "margin_amount_hkd", "margin_multiple",
    "actual_oversubscription", "grey_market_return_pct", "peer_median_first_day_return_pct",
]


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "缺失"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    if isinstance(value, list):
        return "、".join(map(str, value)) if value else "缺失"
    return f"{value}{suffix}"


def _money(value: Any) -> str:
    return "缺失" if value is None else f"HK${float(value):,.0f}"


def _notes(items: list[str]) -> str:
    return "；".join(items) if items else "无可用数据"


def render_markdown(day: date, items: list[tuple[IPORecord, ScoreResult]]) -> str:
    lines = [
        f"# 港股新股打新日报 - {day.isoformat()}", "",
        "> 本报告采用确定性规则评分；缺失数据不获分且可能触发风险扣分。仅供研究，不构成投资建议。", "",
        "## 今日可申购 / 即将申购新股总览", "",
        "| 股票代码 | 公司名称 | 板块 | 招股日期 | 上市日期 | 入场费 | 发行价区间 | 融资倍率 | 基石占比 | 评分 | 建议 |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for record, score in items:
        offer_dates = f"{_fmt(record.value('offer_start_date'))} 至 {_fmt(record.value('offer_end_date'))}"
        lines.append(
            f"| {record.stock_code} | {record.company_name} | {_fmt(record.value('sector'))} | "
            f"{offer_dates} | {_fmt(record.value('listing_date'))} | {_money(record.value('entry_fee_hkd'))} | "
            f"{_fmt(record.value('offer_price_range'))} | {_fmt(record.value('margin_multiple'), 'x')} | "
            f"{_fmt(record.value('cornerstone_ratio'), '%')} | {score.total:.1f} | {score.recommendation} |"
        )

    lines.extend(["", "## 单只新股分析", ""])
    for index, (r, s) in enumerate(items, 1):
        lines.extend([
            f"### {index}. {r.company_name} / {r.stock_code}", "", "#### 基本信息", "",
            f"- 公司名称：{r.company_name}", f"- 股票代码：{r.stock_code}",
            f"- 所属板块：{_fmt(r.value('sector'))}",
            f"- 主营业务：{_fmt(r.value('business_description'))}",
            f"- 招股日期：{_fmt(r.value('offer_start_date'))} 至 {_fmt(r.value('offer_end_date'))}",
            f"- 上市日期：{_fmt(r.value('listing_date'))}",
            f"- 发行价区间：{_fmt(r.value('offer_price_range'))}",
            f"- 一手股数：{_fmt(r.value('board_lot'))}",
            f"- 入场费：{_money(r.value('entry_fee_hkd'))}",
            f"- 募资规模：{_money(r.value('offer_size_hkd'))}",
            f"- 保荐人：{_fmt(r.value('sponsors'))}", "", "#### 公司基本面", "",
            f"- 收入：{_money(r.value('revenue'))}；增长率 {_fmt(r.value('revenue_growth_pct'), '%')}",
            f"- 净利润 / 经调整净利润：{_money(r.value('net_profit'))} / {_money(r.value('adjusted_net_profit'))}",
            f"- 毛利率：{_fmt(r.value('gross_margin_latest'), '%')}",
            f"- 现金流：{_money(r.value('operating_cash_flow'))}",
            f"- 资产负债率：{_fmt(r.value('debt_to_assets_pct'), '%')}",
            f"- 客户集中度：{_fmt(r.value('customer_concentration_top5'), '%')}",
            f"- 业务亮点：{_fmt(r.value('business_highlights'))}",
            f"- 主要风险：{_fmt(r.risk_tags)}", "", "#### 基石投资者", "",
            f"- 基石名单：{_fmt(r.value('cornerstone_investors'))}",
            f"- 认购金额：{_money(r.value('cornerstone_amount_hkd'))}",
            f"- 占发行比例：{_fmt(r.value('cornerstone_ratio'), '%')}",
            f"- 评价：{_notes(s.explanations['cornerstone'])}", "", "#### 市场热度", "",
            f"- 融资认购金额：{_money(r.value('margin_amount_hkd'))}",
            f"- 融资倍率 / 孖展倍数：{_fmt(r.value('margin_multiple'), 'x')}",
            f"- 公开发售超购情况：{_fmt(r.value('actual_oversubscription'), 'x')}",
            f"- 暗盘表现：{_fmt(r.value('grey_market_return_pct'), '%')}",
            f"- 近期同类 IPO 表现：{_fmt(r.value('peer_median_first_day_return_pct'), '%')}",
            "", "#### 评分明细", "",
            "| 维度 | 分数 | 说明 |", "| --- | ---: | --- |",
            f"| 公司基本面 | {s.fundamentals:.1f}/25 | {_notes(s.explanations['fundamentals'])} |",
            f"| 行业与概念 | {s.sector:.1f}/15 | {_notes(s.explanations['sector'])} |",
            f"| 发行结构 | {s.offer_structure:.1f}/15 | {_notes(s.explanations['offer_structure'])} |",
            f"| 基石投资者 | {s.cornerstone:.1f}/15 | {_notes(s.explanations['cornerstone'])} |",
            f"| 市场热度 | {s.market_heat:.1f}/20 | {_notes(s.explanations['market_heat'])} |",
            f"| 风险扣分 | -{s.risk_deduction:.1f} | {_notes(s.explanations['risk'])} |",
            f"| 总分 | {s.total:.1f}/100 | 基础维度按 90 分归一化至 100 后扣风险分；可信度 {s.confidence:.0%} |",
            "", "#### 结论", "", f"- 建议：{s.recommendation}", f"- 适合策略：{s.strategy}",
            "- 不适合策略：在数据缺失或融资成本不明确时使用高杠杆。",
            f"- 核心理由：{_notes(s.explanations['fundamentals'] + s.explanations['market_heat'])}",
            f"- 主要风险：{_notes(s.explanations['risk'])}", "",
        ])

    lines.extend(["## 数据缺失项", ""])
    if not items:
        lines.append("今日未获取到可分析的新股记录。请检查日志、HKEX 页面结构或手工输入。")
    for r, s in items:
        missing = r.missing_fields(DISPLAY_FIELDS)
        impact = "高" if s.confidence < 0.55 else ("中" if s.confidence < 0.8 else "低")
        lines.append(f"- {r.company_name}（{r.stock_code}）：{', '.join(missing) if missing else '无'}；对评分可信度影响：{impact}。")
    lines.extend([
        "", "## 数据来源与追溯", "",
        "每个字段的 `value/source_url/source_name/fetched_at` 已写入当日 JSON 和 SQLite `field_evidence` 表。", "",
        "## 免责声明", "",
        "本报告仅用于个人研究和数据整理，不构成任何投资建议。港股 IPO 存在破发、流动性不足、融资成本、中签率不确定、市场波动等风险，投资者需自行判断并承担风险。", "",
    ])
    return "\n".join(lines)


def write_report(report_dir: Path, day: date, items: list[tuple[IPORecord, ScoreResult]]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / f"{day.isoformat()}_hk_ipo_report.md"
    target.write_text(render_markdown(day, items), encoding="utf-8")
    return target


def update_summary_csv(path: Path, day: date, items: list[tuple[IPORecord, ScoreResult]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record, score in items:
        rows.append({
            "report_date": day.isoformat(), "stock_code": record.stock_code,
            "company_name": record.company_name, "sector": record.value("sector"),
            "offer_start_date": record.value("offer_start_date"),
            "offer_end_date": record.value("offer_end_date"), "listing_date": record.value("listing_date"),
            "offer_price_range": record.value("offer_price_range"), "entry_fee_hkd": record.value("entry_fee_hkd"),
            "margin_multiple": record.value("margin_multiple"), "cornerstone_ratio": record.value("cornerstone_ratio"),
            "score": score.total, "confidence": score.confidence, "recommendation": score.recommendation,
        })
    new = pd.DataFrame(rows)
    if path.exists() and path.stat().st_size:
        old = pd.read_csv(path, dtype={"stock_code": str})
        frame = pd.concat([old, new], ignore_index=True)
        frame = frame.drop_duplicates(["report_date", "stock_code"], keep="last")
    else:
        frame = new
    frame.to_csv(path, index=False, encoding="utf-8-sig")
