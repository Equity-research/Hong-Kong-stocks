from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from hk_ipo_analyzer.models import IPORecord, ScoreResult

AnalysisItem = tuple[IPORecord, ScoreResult, ScoreResult]


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


def _money(value: Any, currency: str = "HKD") -> str:
    if value is None:
        return "缺失"
    prefix = {"HKD": "HK$", "RMB": "RMB ", "SGD": "S$", "USD": "US$"}.get(currency, f"{currency} ")
    return f"{prefix}{float(value):,.0f}"


def _yes_no(value: Any) -> str:
    if value is None:
        return "缺失"
    return "是" if value is True else "否"


def _notes(items: list[str]) -> str:
    return "；".join(items) if items else "无可用数据"


def _score_class(total: float) -> str:
    if total >= 85:
        return "positive"
    if total >= 65:
        return "neutral"
    if total >= 55:
        return "caution"
    return "high-risk"


def _score_color(total: float) -> str:
    if total >= 85:
        return "#22c55e"
    if total >= 75:
        return "#84cc16"
    if total >= 65:
        return "#eab308"
    if total >= 55:
        return "#f97316"
    return "#ef4444"


def render_markdown(day: date, items: list[AnalysisItem]) -> str:
    covered = sum(1 for record, _, _ in items if record.value("offer_start_date") and record.value("offer_end_date"))
    prospectus_covered = sum(1 for record, _, _ in items if any(doc.get("document_type") == "prospectus" for doc in record.documents))
    revenue_covered = sum(1 for record, _, _ in items if record.value("revenue") is not None)
    structure_covered = sum(1 for record, _, _ in items if record.value("greenshoe") is not None)
    cornerstone_covered = sum(1 for record, _, _ in items if record.value("cornerstone_count") is not None)
    official_high_confidence = sum(1 for _, score, _ in items if score.confidence >= 0.8)
    enhanced_high_confidence = sum(1 for _, _, score in items if score.confidence >= 0.8)
    lines = [
        f"# 港股新股打新日报 - {day.isoformat()}", "",
        "> 本报告采用确定性规则评分；缺失数据不获分且可能触发风险扣分。仅供研究，不构成投资建议。", "",
        "## 数据质量与口径", "",
        f"- **当日真实可申购：{len(items)} 只**",
        f"- 名单规则：仅保留 `招股开始日 ≤ {day.isoformat()} ≤ 招股截止日` 且日期来源可追溯的记录。",
        f"- 招股日期覆盖：{covered}/{len(items)}；官方/增强高置信度：{official_high_confidence}/{len(items)}、{enhanced_high_confidence}/{len(items)}。",
        f"- 港交所招股书入口：{prospectus_covered}/{len(items)}；收入数据：{revenue_covered}/{len(items)}；绿鞋：{structure_covered}/{len(items)}；基石数量：{cornerstone_covered}/{len(items)}。",
        "- 官方分只采用 A 级一手来源和完整财年；增强分允许 A/B 级来源和最新可比期间。C 级数据仅展示。",
        "- 未到配发或暗盘阶段的字段标记为尚未公布，不计入对应阶段的缺失惩罚。", "",
        "## 今日可申购新股总览", "",
        "| 股票代码 | 公司名称 | 板块 | 招股日期 | 入场费 | 基石占比 | 官方分/置信度 | 增强分/置信度 | 增强建议 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for record, official, enhanced in items:
        offer_dates = f"{_fmt(record.value('offer_start_date'))} 至 {_fmt(record.value('offer_end_date'))}"
        lines.append(
            f"| {record.stock_code} | {record.company_name} | {_fmt(record.value('sector'))} | "
            f"{offer_dates} | {_money(record.value('entry_fee_hkd'))} | {_fmt(record.value('cornerstone_ratio'), '%')} | "
            f"{official.total:.1f}/{official.confidence:.0%} | {enhanced.total:.1f}/{enhanced.confidence:.0%} | {enhanced.recommendation} |"
        )

    lines.extend(["", "## 单只新股分析", ""])
    for index, (r, s, enhanced) in enumerate(items, 1):
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
            f"- 保荐人：{_fmt(r.value('sponsors'))}",
            f"- 绿鞋机制：{_yes_no(r.value('greenshoe'))}", "", "#### 公司基本面", "",
            f"- 财务口径：{_fmt(r.value('financial_period'))}；币种 {_fmt(r.value('financial_currency'))}",
            f"- 收入：{_money(r.value('revenue'), r.value('financial_currency', 'HKD'))}；增长率 {_fmt(r.value('revenue_growth_pct'), '%')}",
            f"- 净利润 / 经调整净利润：{_money(r.value('net_profit'), r.value('financial_currency', 'HKD'))} / {_money(r.value('adjusted_net_profit'), r.value('financial_currency', 'HKD'))}",
            f"- 毛利率：{_fmt(r.value('gross_margin_latest'), '%')}",
            f"- 现金流：{_money(r.value('operating_cash_flow'), r.value('financial_currency', 'HKD'))}",
            f"- 资产负债率：{_fmt(r.value('debt_to_assets_pct'), '%')}",
            f"- 客户集中度：{_fmt(r.value('customer_concentration_top5'), '%')}",
            f"- 业务亮点：{_fmt(r.value('business_highlights'))}",
            f"- 主要风险：{_fmt(r.risk_tags)}", "", "#### 基石投资者", "",
            f"- 基石名单：{_fmt(r.value('cornerstone_investors'))}",
            f"- 基石数量：{_fmt(r.value('cornerstone_count'))}",
            f"- 认购金额：{_money(r.value('cornerstone_amount_hkd'))}",
            f"- 占发行比例：{_fmt(r.value('cornerstone_ratio'), '%')}",
            f"- 评价：{_notes(s.explanations['cornerstone'])}", "", "#### 市场热度", "",
            f"- 融资认购金额：{_money(r.value('margin_amount_hkd'))}",
            f"- 融资倍率 / 孖展倍数：{_fmt(r.value('margin_multiple'), 'x')}",
            f"- 公开发售超购情况：{_fmt(r.value('actual_oversubscription'), 'x')}",
            f"- 暗盘表现：{_fmt(r.value('grey_market_return_pct'), '%')}",
            f"- 近期同类 IPO 表现：{_fmt(r.value('peer_median_first_day_return_pct'), '%')}",
            "", "#### 关键字段证据", "",
            "| 字段 | 值/状态 | 来源等级 | 来源 | 期间 | 币种 |",
            "| --- | --- | --- | --- | --- | --- |",
            *_evidence_rows(r, day),
            "", "#### 双轨评分", "",
            "| 评分轨 | 总分 | 可信度 | 建议 |", "| --- | ---: | ---: | --- |",
            f"| 官方分（A 级 + 完整财年） | {s.total:.1f} | {s.confidence:.0%} | {s.recommendation} |",
            f"| 增强分（A/B 级 + 最新可比期间） | {enhanced.total:.1f} | {enhanced.confidence:.0%} | {enhanced.recommendation} |",
            "", "#### 结论", "", f"- 官方建议：{s.recommendation}", f"- 增强建议：{enhanced.recommendation}", f"- 适合策略：{enhanced.strategy}",
            "- 不适合策略：在数据缺失或融资成本不明确时使用高杠杆。",
            f"- 核心理由：{_notes(enhanced.explanations['fundamentals'] + enhanced.explanations['market_heat'])}",
            f"- 主要风险：{_notes(enhanced.explanations['risk'])}", "",
        ])

    lines.extend(["## 数据缺失项", ""])
    if not items:
        lines.append("今日未获取到可分析的新股记录。请检查日志、HKEX 页面结构或手工输入。")
    for r, s, enhanced in items:
        missing = r.missing_fields(DISPLAY_FIELDS)
        impact = "高" if enhanced.confidence < 0.55 else ("中" if enhanced.confidence < 0.8 else "低")
        reasons = [f"{name}（{_missing_reason(r, name, day)}）" for name in missing]
        lines.append(f"- {r.company_name}（{r.stock_code}）：{', '.join(reasons) if reasons else '无'}；对评分可信度影响：{impact}。")
    lines.extend([
        "", "## 数据来源与追溯", "",
        "每个字段的候选证据及 `source_tier/period/currency` 已写入当日 JSON 和 SQLite `field_evidence_candidates` 表。", "",
        "## 免责声明", "",
        "本报告仅用于个人研究和数据整理，不构成任何投资建议。港股 IPO 存在破发、流动性不足、融资成本、中签率不确定、市场波动等风险，投资者需自行判断并承担风险。", "",
    ])
    return "\n".join(lines)


EVIDENCE_FIELDS = (
    "revenue", "net_profit", "gross_margin_latest", "operating_cash_flow",
    "debt_to_assets_pct", "customer_concentration_top5", "cornerstone_ratio",
    "greenshoe", "sponsors", "margin_multiple", "actual_oversubscription",
    "grey_market_return_pct",
)


def _evidence_rows(record: IPORecord, day: date) -> list[str]:
    rows = []
    for name in EVIDENCE_FIELDS:
        item = record.fields.get(name)
        if item is None or item.missing:
            rows.append(f"| `{name}` | {_missing_reason(record, name, day)} | — | — | — | — |")
            continue
        rows.append(
            f"| `{name}` | {_fmt(item.value)} | {item.source_tier} | "
            f"{item.source_name or '—'} | {item.period or '—'} | {item.currency or '—'} |"
        )
    return rows


def _missing_reason(record: IPORecord, name: str, day: date) -> str:
    if name == "actual_oversubscription":
        publication = _date_value(record.value("allotment_result_date"))
        if publication is None or day < publication:
            return "未到配发结果公布时间"
    if name == "grey_market_return_pct":
        listing = _date_value(record.value("listing_date"))
        if listing is None or day < listing:
            return "未到暗盘/上市阶段"
    if name in {"margin_amount_hkd", "margin_multiple"}:
        return "未取得带抓取时间的可靠孖展来源"
    return "未取得符合当前评分轨的可靠证据"


def _date_value(value) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            pass
    return None


def render_html(day: date, items: list[AnalysisItem]) -> str:
    total = len(items)
    high_score = sum(1 for _, _, s in items if s.total >= 75)
    hot = max(items, key=lambda x: x[0].value("margin_multiple") or 0) if items else items[0] if items else None
    high_conf = sum(1 for _, _, s in items if s.confidence >= 0.8)

    rows_html = ""
    for r, official, s in items:
        score_color = _score_color(s.total)
        rows_html += f"""
            <tr>
                <td>{r.stock_code}</td>
                <td class="name-col">{r.company_name}</td>
                <td>{_fmt(r.value('sector'))}</td>
                <td>{official.total:.0f}<small> / {official.confidence:.0%}</small></td>
                <td><span class="score-badge" style="background:{score_color}">{s.total:.0f}</span><small> / {s.confidence:.0%}</small></td>
                <td>{_money(r.value('entry_fee_hkd'))}</td>
                <td>{_fmt(r.value('margin_multiple'), 'x')}</td>
                <td>{_fmt(r.value('cornerstone_ratio'), '%')}</td>
                <td class="rec-{_score_class(s.total)}">{s.recommendation}</td>
            </tr>"""

    detail_html = ""
    for idx, (r, official, s) in enumerate(items, 1):
        sc = _score_color(s.total)
        detail_html += f"""
        <details>
            <summary>{idx}. {r.company_name}（{r.stock_code}）
                <span class="score-badge" style="background:{sc}">{s.total:.0f}</span>
                <small>{s.recommendation}</small>
            </summary>
            <div class="detail-grid">
                <div>
                    <h4>基本信息</h4>
                    <table class="detail-table">
                        <tr><td>板块</td><td>{_fmt(r.value('sector'))}</td></tr>
                        <tr><td>招股日期</td><td>{_fmt(r.value('offer_start_date'))} 至 {_fmt(r.value('offer_end_date'))}</td></tr>
                        <tr><td>上市日期</td><td>{_fmt(r.value('listing_date'))}</td></tr>
                        <tr><td>发行价</td><td>{_fmt(r.value('offer_price_range'))}</td></tr>
                        <tr><td>入场费</td><td>{_money(r.value('entry_fee_hkd'))}</td></tr>
                        <tr><td>募资规模</td><td>{_money(r.value('offer_size_hkd'))}</td></tr>
                        <tr><td>保荐人</td><td>{_fmt(r.value('sponsors'))}</td></tr>
                    </table>
                </div>
                <div>
                    <h4>评分明细</h4>
                    <table class="detail-table">
                        <tr><td>官方分</td><td class="num">{official.total:.1f} / {official.confidence:.0%}</td></tr>
                        <tr><td>增强分</td><td class="num">{s.total:.1f} / {s.confidence:.0%}</td></tr>
                        <tr><td>基本面（增强）</td><td class="num">{s.fundamentals:.1f}/25</td></tr>
                        <tr><td>发行结构（增强）</td><td class="num">{s.offer_structure:.1f}/15</td></tr>
                        <tr><td>基石（增强）</td><td class="num">{s.cornerstone:.1f}/15</td></tr>
                    </table>
                </div>
                <div>
                    <h4>市场热度</h4>
                    <table class="detail-table">
                        <tr><td>融资认购</td><td>{_money(r.value('margin_amount_hkd'))}</td></tr>
                        <tr><td>融资倍数</td><td>{_fmt(r.value('margin_multiple'), 'x')}</td></tr>
                        <tr><td>超购</td><td>{_fmt(r.value('actual_oversubscription'), 'x')}</td></tr>
                        <tr><td>暗盘</td><td>{_fmt(r.value('grey_market_return_pct'), '%')}</td></tr>
                        <tr><td>基石占比</td><td>{_fmt(r.value('cornerstone_ratio'), '%')}</td></tr>
                    </table>
                </div>
                <div>
                    <h4>结论</h4>
                    <p><strong>建议：{s.recommendation}</strong></p>
                    <p>策略：{s.strategy}</p>
                    <p>可信度：{s.confidence:.0%}</p>
                    <p>风险：{_notes(s.explanations['risk'])}</p>
                </div>
            </div>
        </details>"""

    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>港股新股打新日报 - {day.isoformat()}</title>
<style>
:root {{ --bg: #f8fafc; --card: #fff; --text: #1e293b; --muted: #64748b; --border: #e2e8f0; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans HK', sans-serif; background:var(--bg); color:var(--text); line-height:1.6;padding:16px;max-width:960px;margin:0 auto; }}
h1 {{ font-size:1.5rem; margin-bottom:4px; }}
.disclaimer {{ color:var(--muted); font-size:.8rem; margin-bottom:16px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:20px; }}
.card {{ background:var(--card); border-radius:8px; padding:12px; box-shadow:0 1px 3px rgba(0,0,0,.08); text-align:center; }}
.card .num {{ font-size:1.8rem; font-weight:700; }}
.card .label {{ font-size:.75rem; color:var(--muted); margin-top:2px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); margin-bottom:16px; }}
th,td {{ padding:8px 10px; text-align:left; font-size:.85rem; border-bottom:1px solid var(--border); }}
th {{ background:#f1f5f9; font-weight:600; white-space:nowrap; }}
.name-col {{ max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.score-badge {{ display:inline-block; padding:2px 8px; border-radius:12px; color:#fff; font-weight:700; font-size:.8rem; min-width:36px; text-align:center; }}
.rec-positive {{ color:#16a34a; font-weight:700; }}
.rec-neutral {{ color:#ca8a04; font-weight:700; }}
.rec-caution {{ color:#ea580c; font-weight:700; }}
.rec-high-risk {{ color:#dc2626; font-weight:700; }}
details {{ background:var(--card); border-radius:8px; padding:10px 14px; margin-bottom:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
summary {{ cursor:pointer; font-weight:600; font-size:.95rem; display:flex; align-items:center; gap:8px; }}
.detail-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:10px; }}
@media(max-width:600px){{ .detail-grid{{grid-template-columns:1fr;}} table{{font-size:.75rem;}} .cards{{grid-template-columns:1fr 1fr;}} }}
.detail-table td {{ padding:4px 8px; font-size:.8rem; }}
.detail-table td.num {{ text-align:right; font-weight:600; }}
h4 {{ font-size:.85rem; margin-bottom:4px; color:var(--muted); }}
p {{ margin:4px 0; font-size:.85rem; }}
footer {{ margin-top:24px; padding-top:12px; border-top:1px solid var(--border); font-size:.75rem; color:var(--muted); text-align:center; }}
</style>
</head>
<body>
<h1>港股新股打新日报 - {day.isoformat()}</h1>
<p class="disclaimer">确定性规则评分 · 缺失数据不获分 · 仅供研究，不构成投资建议</p>

<div class="cards">
    <div class="card"><div class="num">{total}</div><div class="label">可申购新股</div></div>
    <div class="card"><div class="num">{high_score}</div><div class="label">高评分(≥75)</div></div>
    <div class="card"><div class="num">{hot[0].value('margin_multiple') or 0 if hot else 0}x</div><div class="label">最热认购</div></div>
    <div class="card"><div class="num">{high_conf}/{total}</div><div class="label">高置信度</div></div>
</div>

<table>
    <thead><tr>
        <th>代码</th><th>公司名称</th><th>板块</th><th>官方分/置信度</th><th>增强分/置信度</th>
        <th>入场费</th><th>融资倍数</th><th>基石占比</th><th>建议</th>
    </tr></thead>
    <tbody>{rows_html}
    </tbody>
</table>

<h2>单只新股详情</h2>
{detail_html}

<footer>
    每个字段的 value/source_url/source_name/fetched_at 已存入 SQLite field_evidence 表 · 本报告仅供研究，不构成投资建议
</footer>
</body>
</html>"""


def write_report(report_dir: Path, day: date, items: list[AnalysisItem]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / f"{day.isoformat()}_hk_ipo_report.md"
    target.write_text(render_markdown(day, items), encoding="utf-8")
    html_target = report_dir / f"{day.isoformat()}_hk_ipo_report.html"
    html_target.write_text(render_html(day, items), encoding="utf-8")
    return target


def update_summary_csv(path: Path, day: date, items: list[AnalysisItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record, official_score, enhanced_score in items:
        rows.append({
            "report_date": day.isoformat(), "stock_code": record.stock_code,
            "company_name": record.company_name, "sector": record.value("sector"),
            "offer_start_date": record.value("offer_start_date"),
            "offer_end_date": record.value("offer_end_date"), "listing_date": record.value("listing_date"),
            "offer_price_range": record.value("offer_price_range"), "entry_fee_hkd": record.value("entry_fee_hkd"),
            "margin_multiple": record.value("margin_multiple"), "cornerstone_ratio": record.value("cornerstone_ratio"),
            "score": official_score.total, "confidence": official_score.confidence, "recommendation": official_score.recommendation,
            "enhanced_score": enhanced_score.total, "enhanced_confidence": enhanced_score.confidence,
            "enhanced_recommendation": enhanced_score.recommendation,
        })
    # 汇总文件是“当日快照”，每次运行整体替换，避免历史日期混入今日名单。
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
