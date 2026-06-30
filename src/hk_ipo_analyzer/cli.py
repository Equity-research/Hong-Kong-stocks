from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from hk_ipo_analyzer.config import load_config, project_path
from hk_ipo_analyzer.logging_config import setup_logging
from hk_ipo_analyzer.pipeline import DailyPipeline


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def run_once(args, config: dict) -> None:
    report = DailyPipeline(config).run(
        day=args.date or date.today(),
        input_json=Path(args.input_json) if args.input_json else None,
        skip_pdf=args.skip_pdf,
    )
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="港股新股打新每日分析系统")
    parser.add_argument("--config", default="config/config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    daily = subparsers.add_parser("daily", help="运行一次日报")
    daily.add_argument("--date", type=parse_date)
    daily.add_argument("--input-json", help="使用本地 JSON，适合离线测试或人工数据")
    daily.add_argument("--skip-pdf", action="store_true", help="不下载/解析招股书")
    schedule = subparsers.add_parser("schedule", help="前台运行 APScheduler")
    schedule.add_argument("--hour", type=int, default=8)
    schedule.add_argument("--minute", type=int, default=0)
    schedule.add_argument("--skip-pdf", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config["app"].get("log_level", "INFO"), str(project_path(config, "logs/hk_ipo.log")))
    if args.command == "daily":
        run_once(args, config)
        return
    scheduler = BlockingScheduler(timezone=config["app"].get("timezone", "Asia/Shanghai"))
    scheduler.add_job(
        lambda: DailyPipeline(config).run(date.today(), skip_pdf=args.skip_pdf),
        "cron", hour=args.hour, minute=args.minute, id="hk_ipo_daily", replace_existing=True,
    )
    logging.getLogger(__name__).info("定时器已启动：每日 %02d:%02d", args.hour, args.minute)
    scheduler.start()


if __name__ == "__main__":
    main()
