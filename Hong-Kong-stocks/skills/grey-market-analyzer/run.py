# -*- coding: utf-8 -*-
"""grey-market-analyzer Skill: 暗盘价格追踪与上市首日情景分析

Usage: python skills/grey-market-analyzer/run.py --date 2026-06-30 [--stock 02523]
"""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_data(db_path: Path, analysis_date: str, stock_code: str | None = None) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    query = """
        SELECT stock_code, company_name, sector, listing_date,
               offer_price_high, board_lot, entry_fee_hkd,
               grey_market_return_pct, margin_multiple, score
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
            "listing_date": r[3], "offer_price_high": r[4],
            "board_lot": r[5], "entry_fee": r[6],
            "grey_return": r[7], "margin_multiple": r[8], "score": r[9],
        }
        for r in rows
    ]


def scenario_analysis(item: dict) -> str:
    grey = item["grey_return"]
    if grey is None:
        return "暗盘数据尚未公布，请在暗盘交易开始后重新运行。"

    price = item["offer_price_high"] or 0
    lot = item["board_lot"] or 0
    entry = item["entry_fee"] or 0
    gross_profit = price * lot * (grey / 100) if grey else 0
    net_profit = gross_profit - entry * 0.0127  # 估算交易成本 1.27%

    lines = [
        "",
        f"- **暗盘回报**: {grey:+.1f}%",
        f"- **每手毛利**: HK${gross_profit:,.0f}",
        f"- **估算净利** (含交易费): HK${net_profit:,.0f}",
        "",
        "**情景分析**:",
    ]

    scenarios = [
        ("bull", grey * 1.5, "乐观：暗盘涨幅延续"),
        ("base", grey, "中性：维持暗盘水平"),
        ("bear", grey * 0.3, "悲观：涨幅收窄"),
    ]

    for label, ret, desc in scenarios:
        lot_profit = price * lot * (ret / 100) - entry * 0.0127
        lines.append(f"- {label.upper()}: {ret:+.1f}% | 每手净利 HK${lot_profit:,.0f} | {desc}")

    return "\n".join(lines)


def analyze(ipo_data: list[dict]) -> str:
    lines = [
        f"# 暗盘分析 - {date.today().isoformat()}",
        "",
        "> 暗盘数据来自 AAStocks/券商公开报价。仅供研究，不构成交易建议。",
        "",
        "## 暗盘概览",
        "",
        "| 股票代码 | 公司名称 | 暗盘涨跌 | 融资倍数 | 上市首日情景 |",
        "| --- | --- | ---: | ---: | --- |",
    ]

    for item in sorted(ipo_data, key=lambda x: x["grey_return"] or 0, reverse=True):
        grey_str = f"{item['grey_return']:+.1f}%" if item["grey_return"] is not None else "未开盘"
        mult = f"{item['margin_multiple']:.0f}x" if item["margin_multiple"] else "-"
        status = "已开盘" if item["grey_return"] is not None else "待开盘"
        lines.append(
            f"| {item['stock_code']} | {item['company_name']} | "
            f"{grey_str} | {mult} | {status} |"
        )

    lines.extend(["", "## 逐只分析", ""])
    for item in ipo_data:
        lines.append(f"### {item['company_name']}（{item['stock_code']}）")
        lines.append(scenario_analysis(item))
        lines.append("")

    lines.extend([
        "## 风险提示",
        "",
        "- 暗盘价格不代表上市首日开盘价。",
        "- 不同券商暗盘价格可能存在差异。",
        "- 暗盘成交量低时价格信号可靠性下降。",
        "- 如果暗盘数据缺失，说明该 IPO 尚未开始暗盘交易。",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="暗盘分析")
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
