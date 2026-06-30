# -*- coding: utf-8 -*-
"""subscription-heat-analyzer Skill: 孖展时间序列追踪与热度分析

Usage: python skills/subscription-heat-analyzer/run.py --date 2026-06-30 [--stock 02523]
"""

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_data(db_path: Path, analysis_date: str, stock_code: str | None = None) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    query = """
        SELECT stock_code, company_name, sector, offer_start_date, offer_end_date,
               margin_amount_hkd, margin_multiple, expected_oversubscription,
               actual_oversubscription, news_heat_score
        FROM ipo_daily
        WHERE report_date = ?
    """
    params = [analysis_date]
    if stock_code:
        query += " AND stock_code = ?"
        params.append(stock_code)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {
            "stock_code": r[0], "company_name": r[1], "sector": r[2],
            "offer_start": r[3], "offer_end": r[4], "margin_amount": r[5],
            "margin_multiple": r[6], "expected_over": r[7], "actual_over": r[8],
            "news_heat": r[9],
        }
        for r in rows
    ]


HEAT_THRESHOLDS = {
    "extreme": 100,
    "hot": 30,
    "warm": 10,
    "neutral": 3,
    "cold": 0,
}


def classify_heat(margin_multiple: float | None) -> str:
    if margin_multiple is None:
        return "unknown"
    for label, threshold in sorted(HEAT_THRESHOLDS.items(), key=lambda x: -x[1]):
        if margin_multiple >= threshold:
            return label
    return "cold"


def analyze(ipo_data: list[dict]) -> str:
    if not ipo_data:
        return "当日无新股孖展数据。请先运行 `hk-ipo daily` 获取数据。"

    lines = [
        f"# 孖展热度分析 - {date.today().isoformat()}",
        "",
        f"分析 {len(ipo_data)} 只新股的认购热度。",
        "",
        "## 热度排名",
        "",
        "| 股票代码 | 公司名称 | 孖展金额(HKD) | 融资倍数 | 热度等级 | 关注度 |",
        "| --- | --- | ---: | ---: | --- | ---: |",
    ]

    sorted_data = sorted(
        ipo_data,
        key=lambda x: x["margin_multiple"] or 0,
        reverse=True,
    )

    for item in sorted_data:
        amount = f"{item['margin_amount']:,.0f}" if item["margin_amount"] else "缺失"
        mult = f"{item['margin_multiple']:.1f}x" if item["margin_multiple"] else "缺失"
        heat = classify_heat(item["margin_multiple"])
        news = item["news_heat"] if item["news_heat"] else "-"
        lines.append(
            f"| {item['stock_code']} | {item['company_name']} | {amount} | "
            f"{mult} | {heat} | {news} |"
        )

    lines.extend([
        "",
        "## 热度分档说明",
        "",
        "| 等级 | 融资倍数 | 含义 |",
        "| --- | --- | --- |",
        "| extreme | ≥100x | 极度火热，中签率极低 |",
        "| hot | 30-99x | 热门认购 |",
        "| warm | 10-29x | 温和认购 |",
        "| neutral | 3-9x | 中性 |",
        "| cold | <3x | 冷清 |",
        "",
        "## 风险提示",
        "",
        "- 融资倍数非最终数据，最终公开发售超购以港交所公布为准。",
        "- 高倍数意味着中签率低但破发风险不一定低，需结合基本面判断。",
        "- 数据来源：`data/manual_override.csv` 或 etnet/AAStocks 实时数据。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="孖展热度分析")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--stock", default=None)
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "hk_ipo.db"
    if not db_path.exists():
        print("数据库不存在，请先运行 `hk-ipo daily`", file=sys.stderr)
        sys.exit(1)

    data = load_data(db_path, args.date, args.stock)
    report = analyze(data)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"报告已保存至：{args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
