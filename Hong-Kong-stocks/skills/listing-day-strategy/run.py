# -*- coding: utf-8 -*-
"""listing-day-strategy Skill: 挂牌日操作建议

Usage: python skills/listing-day-strategy/run.py --date 2026-06-30
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def strategy(item: dict) -> str:
    score = item["score"] or 0
    grey = item["grey_return"]
    confidence = item["confidence"] or 0

    lines = []
    if grey is not None and grey > 5:
        lines.append("- 暗盘表现强劲，考虑暗盘获利了结 50% 仓位。")
    elif grey is not None and grey < -5:
        lines.append("- 暗盘表现不佳，挂牌日开盘观望，设止损线 -10%。")

    if score >= 85:
        lines.append("- 高评分 IPO，可持有至首日收盘，目标收益 15-25%。")
        lines.append("- 若首日涨幅超 30%，建议减仓 50% 锁定利润。")
    elif score >= 75:
        lines.append("- 中等偏上评分，首日涨幅 10-15% 建议部分兑现。")
        lines.append("- 若破发，观察 30 分钟，持续走弱则止损。")
    elif score >= 65:
        lines.append("- 评分一般，现金一手参与，首日涨幅 5-10% 即考虑兑现。")
        lines.append("- 不建议融资申购此类 IPO。")
    elif score >= 55:
        lines.append("- 低评分，不建议打新；若已申购，挂牌日开盘即卖出。")
    else:
        lines.append("- 极低评分，坚决不参与。")

    if confidence < 0.5:
        lines.append("- ⚠️ 可信度低，以上建议仅供参考，不构成操作依据。")

    return "\n".join(lines)


def analyze(ipos: list[dict]) -> str:
    lines = [
        f"# 挂牌日操作建议 - {date.today().isoformat()}",
        "",
        "> 基于评分、暗盘和可信度的策略建议。不构成投资建议。",
        "",
        "## 操作建议",
        "",
    ]
    for item in sorted(ipos, key=lambda x: x["score"] or 0, reverse=True):
        lines.append(f"### {item['company_name']}（{item['stock_code']}）")
        lines.append(f"评分: {item['score']:.1f if item['score'] else 'N/A'} | "
                     f"可信度: {item['confidence']:.0% if item['confidence'] else 'N/A'} | "
                     f"暗盘: {item['grey_return']:+.1f}%\" if item['grey_return'] else '暗盘尚未开盘'")
        lines.append(strategy(item))
        lines.append("")

    lines.extend([
        "## 通用策略规则",
        "",
        "1. 不要将所有资金集中于单只 IPO。",
        "2. 融资申购需考虑利息成本（约 3-5% 年化）。",
        "3. 暗盘获利目标：锁定 50% 仓位，剩余观察。",
        "4. 首日破发超过 10%：果断止损。",
        "5. 中签率低但热门 IPO：关注暗盘机会而非等待上市。",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="挂牌日操作建议")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "hk_ipo.db"
    if not db_path.exists():
        print("数据库不存在", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT stock_code, company_name, score, confidence,
                  grey_market_return_pct, recommendation
           FROM ipo_daily WHERE report_date = ?""",
        [args.date],
    ).fetchall()
    conn.close()

    ipos = [
        {"stock_code": r[0], "company_name": r[1], "score": r[2],
         "confidence": r[3], "grey_return": r[4], "recommendation": r[5]}
        for r in rows
    ]
    report = analyze(ipos)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
