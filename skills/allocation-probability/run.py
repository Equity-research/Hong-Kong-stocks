# -*- coding: utf-8 -*-
"""allocation-probability Skill: 中签率估算

基于超购倍数历史数据拟合中签率。保守估算，不保证准确性。

Usage: python skills/allocation-probability/run.py --date 2026-06-30 [--stock 02523]
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_data(db_path: Path, analysis_date: str, stock_code: str | None = None) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    query = """
        SELECT stock_code, company_name, expected_oversubscription,
               actual_oversubscription, margin_multiple, public_offer_ratio
        FROM ipo_daily WHERE report_date = ?
    """
    params = [analysis_date]
    if stock_code:
        query += " AND stock_code = ?"
        params.append(stock_code)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {
            "stock_code": r[0], "company_name": r[1],
            "expected_over": r[2], "actual_over": r[3],
            "margin_multiple": r[4], "public_ratio": r[5],
        }
        for r in rows
    ]


def estimate_allocation(oversubscription: float | None, public_ratio: float | None) -> dict:
    """保守中签率估算 - 基于历史港股 IPO 中签率分布"""
    if oversubscription is None or public_ratio is None:
        return {"a_head": None, "a_tail": None, "confidence": "不可估算"}

    over = oversubscription
    ratio = public_ratio or 10

    if over <= 1:
        a_head = 100.0
    elif over <= 5:
        a_head = max(5, 60 / over)
    elif over <= 15:
        a_head = max(2, 100 / over)
    elif over <= 50:
        a_head = max(0.5, 60 / over)
    elif over <= 100:
        a_head = max(0.2, 30 / over)
    else:
        a_head = max(0.05, 15 / over)

    a_tail = min(100, a_head * 2.5) if a_head < 100 else 100

    confidence = "高" if over <= 100 else "中"
    return {"a_head": round(a_head, 2), "a_tail": round(a_tail, 2), "confidence": confidence}


def analyze(ipo_data: list[dict]) -> str:
    lines = [
        f"# 中签率估算 - {date.today().isoformat()}",
        "",
        "> 基于超购倍数历史数据保守估算。实际中签率以港交所公布为准。",
        "",
        "## 中签率估算",
        "",
        "| 股票代码 | 公司名称 | 预估超购 | 公开占比 | A组头 | A组尾 | 可信度 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]

    for item in ipo_data:
        over = item["actual_over"] or item["expected_over"]
        alloc = estimate_allocation(over, item["public_ratio"])
        over_str = f"{over:.0f}x" if over else "缺失"
        ratio_str = f"{item['public_ratio']:.0f}%" if item["public_ratio"] else "缺失"
        a_head = f"{alloc['a_head']:.1f}%" if alloc["a_head"] else "N/A"
        a_tail = f"{alloc['a_tail']:.1f}%" if alloc["a_tail"] else "N/A"

        lines.append(
            f"| {item['stock_code']} | {item['company_name']} | {over_str} | "
            f"{ratio_str} | {a_head} | {a_tail} | {alloc['confidence']} |"
        )

    lines.extend([
        "",
        "## 中签率估算方法",
        "",
        "- 仅在已有超购倍数及公开发售比例时输出区间估算；孖展倍数不冒充超购倍数。",
        "- A 组（小额申购）和 B 组（大额申购）有不同分配机制。",
        "- 回拨机制会影响实际公开认购份额：超购倍数越高，公开发售占比越大。",
        "- A组头 = 申购一手中签概率；A组尾 = 申购最高额度中签概率。",
        "",
        "## 风险提示",
        "",
        "- 此为模型估算，实际中签率受市场情绪、保荐人策略等多因素影响。",
        "- 高倍数认购虽然中签率低，但不等于上市首日一定上涨。",
        "- 回拨后公开发售比例变化会影响中签率。",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="中签率估算")
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
