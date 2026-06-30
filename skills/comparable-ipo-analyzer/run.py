# -*- coding: utf-8 -*-
"""comparable-ipo-analyzer Skill: 板块同行对比

Usage: python skills/comparable-ipo-analyzer/run.py --date 2026-06-30
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_data(db_path: Path, analysis_date: str) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """SELECT stock_code, company_name, sector, peer_median_first_day_return_pct,
                  peer_median_pe, issuer_pe, industry_growth_pct
           FROM ipo_daily WHERE report_date = ?""",
        [analysis_date],
    ).fetchall()
    conn.close()
    return [
        {"stock_code": r[0], "company_name": r[1], "sector": r[2],
         "peer_return": r[3], "peer_pe": r[4], "issuer_pe": r[5],
         "industry_growth": r[6]}
        for r in rows
    ]


def load_historical_peers(db_path: Path) -> dict[str, dict]:
    hist_db = PROJECT_ROOT / "data" / "historical_ipos.db"
    if not hist_db.exists():
        return {}
    conn = sqlite3.connect(str(hist_db))
    rows = conn.execute(
        """SELECT sector, ipo_count, median_first_day_return, mean_first_day_return,
                  break_even_rate, avg_oversubscription
           FROM peer_statistics"""
    ).fetchall()
    conn.close()
    return {
        r[0]: {
            "count": r[1], "median_return": r[2], "mean_return": r[3],
            "break_even": r[4], "avg_over": r[5],
        }
        for r in rows
    }


def analyze(ipos: list[dict], peers: dict) -> str:
    lines = [
        f"# 板块同行对比 - {date.today().isoformat()}",
        "",
        "## 板块统计",
        "",
        "| 板块 | 历史 IPO 数 | 中位首日回报 | 平均首日回报 | 破发率 | 平均超购 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sector, stats in sorted(peers.items()):
        med = f"{stats['median_return']:+.1f}%" if stats["median_return"] else "N/A"
        avg = f"{stats['mean_return']:+.1f}%" if stats["mean_return"] else "N/A"
        be = f"{stats['break_even']:.0f}%" if stats.get("break_even") else "N/A"
        over = f"{stats['avg_over']:.1f}x" if stats.get("avg_over") else "N/A"
        lines.append(
            f"| {sector} | {stats['count']} | {med} | {avg} | {be} | {over} |"
        )

    lines.extend(["", "## 当前新股板块归属", ""])
    for item in ipos:
        sector = item["sector"] or "未知"
        peer_info = peers.get(sector, {})
        peer_ret = peer_info.get("median_return")
        peer_str = f"{peer_ret:+.1f}%" if peer_ret else "无历史数据"
        lines.append(
            f"- **{item['company_name']}**（{item['stock_code']}）："
            f"板块 `{sector}`，同行中位首日回报 {peer_str}"
        )

    lines.extend([
        "",
        "## 估值对比",
        "",
        "| 股票代码 | 公司名称 | 发行人 PE | 同行中位 PE | 溢价/折价 |",
        "| --- | --- | ---: | ---: | --- |",
    ])
    for item in ipos:
        issuer_pe = f"{item['issuer_pe']:.1f}" if item["issuer_pe"] else "缺失"
        peer_pe = f"{item['peer_pe']:.1f}" if item["peer_pe"] else "缺失"
        if item["issuer_pe"] and item["peer_pe"]:
            prem = f"{((item['issuer_pe'] / item['peer_pe']) - 1) * 100:+.1f}%"
        else:
            prem = "N/A"
        lines.append(
            f"| {item['stock_code']} | {item['company_name']} | "
            f"{issuer_pe} | {peer_pe} | {prem} |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="板块同行对比")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "hk_ipo.db"
    if not db_path.exists():
        print("数据库不存在，请先运行 `hk-ipo daily`", file=sys.stderr)
        sys.exit(1)

    ipos = load_data(db_path, args.date)
    peers = load_historical_peers(db_path)
    report = analyze(ipos, peers)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
