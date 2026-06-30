# -*- coding: utf-8 -*-
"""ipo-scoring Skill: 场景评分分析

支持 what-if 场景：如果某某字段改变，评分会如何变化？

Usage: python skills/ipo-scoring/run.py --stock 02523 --scenario '{"cornerstone_ratio":50,"margin_multiple":30}'
"""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_record(db_path: Path, stock_code: str) -> dict | None:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        """SELECT record_json FROM ipo_daily
           WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1""",
        [stock_code],
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None


def analyze_scenario(record_json: dict, scenario: dict) -> str:
    from hk_ipo_analyzer.models import IPORecord
    from hk_ipo_analyzer.analysis.scoring_model import ScoringModel

    record = IPORecord.from_dict(record_json)

    model = ScoringModel()
    baseline = model.score(record)

    for field, value in scenario.items():
        record.set_field(field, value, "scenario", "场景分析", overwrite=True)

    scenario_score = model.score(record)

    dims = [
        ("fundamentals", "基本面"),
        ("sector", "行业"),
        ("offer_structure", "发行结构"),
        ("cornerstone", "基石"),
        ("market_heat", "市场热度"),
    ]

    lines = [
        f"# 场景评分分析 - {record.company_name}（{record.stock_code}）",
        "",
        "## 变更参数",
    ]
    for field, value in scenario.items():
        lines.append(f"- `{field}`: {value}")

    lines.extend([
        "",
        "## 评分对比",
        "",
        "| 维度 | 基准 | 场景 | 变化 |",
        "| --- | ---: | ---: | ---: |",
    ])

    for attr, label in dims:
        base_val = getattr(baseline, attr)
        sc_val = getattr(scenario_score, attr)
        chg = sc_val - base_val
        lines.append(
            f"| {label} | {base_val:.1f} | {sc_val:.1f} | {chg:+.1f} |"
        )

    lines.extend([
        f"| 风险扣分 | {baseline.risk_deduction:.1f} | {scenario_score.risk_deduction:.1f} | {scenario_score.risk_deduction - baseline.risk_deduction:+.1f} |",
        f"| **总分** | **{baseline.total:.1f}** | **{scenario_score.total:.1f}** | **{scenario_score.total - baseline.total:+.1f}** |",
        f"| 可信度 | {baseline.confidence:.0%} | {scenario_score.confidence:.0%} | |",
        "",
        f"### 基准建议: {baseline.recommendation}",
        f"### 场景建议: {scenario_score.recommendation}",
        "",
        "> 场景分析仅供参考，不构成投资建议。",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="场景评分分析")
    parser.add_argument("--stock", required=True, help="股票代码")
    parser.add_argument("--scenario", required=True, help='JSON 场景参数，如 {"cornerstone_ratio":50}')
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    db_path = PROJECT_ROOT / "data" / "hk_ipo.db"
    if not db_path.exists():
        print("数据库不存在", file=sys.stderr)
        sys.exit(1)

    record = load_record(db_path, args.stock.zfill(5))
    if not record:
        print(f"未找到股票 {args.stock} 的数据")
        sys.exit(1)

    scenario = json.loads(args.scenario)
    report = analyze_scenario(record, scenario)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
