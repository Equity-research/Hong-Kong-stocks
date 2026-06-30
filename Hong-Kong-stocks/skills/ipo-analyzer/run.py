# -*- coding: utf-8 -*-
"""ipo-analyzer Skill: 端到端 IPO 分析入口

整合所有分析 Skill，对单只或全部新股执行完整分析。

Usage:
    python skills/ipo-analyzer/run.py --stock 02523      # 单只分析
    python skills/ipo-analyzer/run.py --date 2026-06-30   # 全部分析
"""

import argparse
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"

ANALYSIS_STEPS = [
    ("subscription-heat-analyzer", "孖展热度分析"),
    ("grey-market-analyzer", "暗盘分析"),
    ("allocation-probability", "中签率估算"),
    ("comparable-ipo-analyzer", "同行对比"),
    ("valuation-analyzer", "估值分析"),
    ("ipo-scoring", "场景评分"),
    ("listing-day-strategy", "挂牌策略"),
]


def run_skill(name: str, args_str: str) -> str | None:
    script = SKILLS_DIR / name / "run.py"
    if not script.exists():
        return f"  ⚠️  Skill `{name}` 未实现，跳过"
    try:
        result = subprocess.run(
            [sys.executable, str(script)] + args_str.split(),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return f"  ❌ Skill `{name}` 执行失败: {result.stderr}"
    except Exception as e:
        return f"  ❌ Skill `{name}` 异常: {e}"


def main():
    parser = argparse.ArgumentParser(description="端到端 IPO 分析")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--stock", default=None)
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    date_arg = f"--date {args.date}"
    stock_arg = f"--stock {args.stock}" if args.stock else ""

    all_reports = []

    print(f"=== IPO 端到端分析 ===")
    print(f"日期: {args.date}")
    if args.stock:
        print(f"股票: {args.stock}")
    print()

    for skill_name, label in ANALYSIS_STEPS:
        print(f"[{label}] ", end="", flush=True)
        result = run_skill(skill_name, f"{date_arg} {stock_arg}")
        if result:
            header = f"\n## {label} ({skill_name})\n"
            all_reports.append(header + result)
            lines = result.strip().split("\n")
            status = lines[0] if lines else "(空)"
            print(status[:80])
        else:
            print("(跳过)")

    combined = f"# 港股 IPO 综合分析 - {args.date}\n" + "\n---\n".join(all_reports)

    if args.output:
        Path(args.output).write_text(combined, encoding="utf-8")
        print(f"\n综合报告已保存至: {args.output}")
    else:
        out_path = SKILLS_DIR / "ipo-analyzer" / f"combined_{args.date}_analysis.md"
        out_path.write_text(combined, encoding="utf-8")
        print(f"\n综合报告已保存至: {out_path}")


if __name__ == "__main__":
    main()
