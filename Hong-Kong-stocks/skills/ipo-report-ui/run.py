# -*- coding: utf-8 -*-
"""ipo-report-ui Skill: 打开 HTML 仪表盘

Usage: python skills/ipo-report-ui/run.py --date 2026-06-30
"""

import argparse
import sys
import webbrowser
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="打开 IPO 日报 HTML 仪表盘")
    parser.add_argument("--date", default=None, help="日期 (默认今天)")
    parser.add_argument("--latest", action="store_true", help="使用最新的报告")
    args = parser.parse_args()

    reports_dir = PROJECT_ROOT / "reports"

    if args.latest:
        html_files = sorted(reports_dir.glob("*_hk_ipo_report.html"), reverse=True)
        if not html_files:
            print("未找到 HTML 报告。请先运行 `hk-ipo daily`", file=sys.stderr)
            sys.exit(1)
        target = html_files[0]
    elif args.date:
        target = reports_dir / f"{args.date}_hk_ipo_report.html"
    else:
        target = reports_dir / f"{date.today().isoformat()}_hk_ipo_report.html"

    if not target.exists():
        print(f"报告不存在: {target}")
        print("请先运行 `hk-ipo daily` 生成报告。")
        sys.exit(1)

    file_url = target.as_uri()
    print(f"打开报告: {target}")
    try:
        webbrowser.open(file_url)
    except Exception:
        print(f"无法自动打开浏览器。请手动打开:\n  {target}")


if __name__ == "__main__":
    main()
