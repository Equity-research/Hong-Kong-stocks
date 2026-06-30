# -*- coding: utf-8 -*-
"""valuation-analyzer Skill: 估值分析

Usage: python skills/valuation-analyzer/run.py --date 2026-06-30
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def analyze(ipos: list[dict]) -> str:
    lines = [
        f"# 估值分析 - {date.today().isoformat()}",
        "",
        "## 估值概览",
        "",
        "| 股票代码 | 公司名称 | 发行 PE | 同行 PE | 市值(HKD) | 估值结论 |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]

    for item in ipos:
        issuer_pe = item["issuer_pe"]
        peer_pe = item["peer_pe"]
        mkt_cap = item["market_cap"]

        pe_str = f"{issuer_pe:.1f}" if issuer_pe else "缺失"
        peer_str = f"{peer_pe:.1f}" if peer_pe else "缺失"
        cap_str = f"{mkt_cap/1e8:,.0f}亿" if mkt_cap else "缺失"

        if issuer_pe and peer_pe:
            ratio = issuer_pe / peer_pe
            if ratio < 0.7:
                conclusion = "低估"
            elif ratio < 1.0:
                conclusion = "合理偏低"
            elif ratio < 1.3:
                conclusion = "合理"
            elif ratio < 1.8:
                conclusion = "偏高"
            else:
                conclusion = "高估"
        else:
            conclusion = "数据不足"

        lines.append(
            f"| {item['stock_code']} | {item['company_name']} | "
            f"{pe_str} | {peer_str} | {cap_str} | {conclusion} |"
        )

    lines.extend([
        "",
        "## 估值方法说明",
        "",
        "- 主要使用 PE（市盈率）与同行业已上市公司对比。",
        "- 市盈率低于同行中位数 70% 为「低估」；70%-100% 为「合理偏低」；",
        "  100%-130% 为「合理」；130%-180% 为「偏高」；180%+ 为「高估」。",
        "- 没有同行 PE 数据时，不作出估值判断。",
        "- 现金流折现（DCF）等更复杂估值方法需在后续版本中加入。",
        "",
        "## 风险提示",
        "",
        "- 新股定价受市场情绪、行业周期、公司质地等多因素影响。",
        "- PE 估值不适用于尚未盈利或利润极薄的公司。",
        "- 本文结论不构成投资建议。",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="估值分析")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "hk_ipo.db"
    if not db_path.exists():
        print("数据库不存在，请先运行 `hk-ipo daily`", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT stock_code, company_name, offer_price_high, board_lot,
                  market_cap_hkd, peer_median_pe, valuation_score, score
           FROM ipo_daily WHERE report_date = ?""",
        [args.date],
    ).fetchall()
    conn.close()

    ipos = [
        {"stock_code": r[0], "company_name": r[1], "issuer_pe": None,
         "peer_pe": r[4], "market_cap": r[3], "score": r[6]}
        for r in rows
    ]
    report = analyze(ipos)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
