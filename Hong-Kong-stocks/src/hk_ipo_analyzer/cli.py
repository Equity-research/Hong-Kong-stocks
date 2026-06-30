from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from hk_ipo_analyzer.config import load_config, project_path
from hk_ipo_analyzer.logging_config import setup_logging
from hk_ipo_analyzer.models import EXPECTED_FIELDS
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


def cmd_verify(args, config: dict) -> None:
    """交互式逐字段填写 IPO 数据并输出 verified_current_ipos JSON"""
    stock_code = args.code or input("股票代码（5位，如 02523）: ").strip()
    company_name = args.name or input("公司名称: ").strip()
    source_url = args.source_url or input("数据来源 URL（如 etnet 页面）: ").strip() or "手工核验"
    source_name = args.source_name or "手工核验"
    fields: dict[str, dict] = {}
    if args.from_csv:
        import csv
        with open(args.from_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = str(row.get("stock_code", "")).strip()
                name = str(row.get("company_name", "")).strip()
                if not code or not name:
                    continue
                record_fields: dict[str, dict] = {}
                for field in EXPECTED_FIELDS:
                    val = row.get(field, "").strip()
                    if val:
                        record_fields[field] = {
                            "value": _parse_value(val),
                            "source_url": row.get(f"{field}_source_url", source_url),
                            "source_name": row.get(f"{field}_source_name", source_name),
                            "fetched_at": datetime.now().isoformat(),
                        }
                fields[f"{code.zfill(5)}|{name}"] = record_fields
    else:
        print(f"\n开始交互填写 {company_name}（{stock_code}）的字段。留空跳过。\n")
        print("可用字段:", ", ".join(EXPECTED_FIELDS[:20]), "...\n")
        record_fields: dict[str, dict] = {}
        for field in EXPECTED_FIELDS:
            val = input(f"  {field}: ").strip()
            if val:
                record_fields[field] = {
                    "value": _parse_value(val),
                    "source_url": input(f"    source_url [{source_url}]: ").strip() or source_url,
                    "source_name": input(f"    source_name [{source_name}]: ").strip() or source_name,
                    "fetched_at": datetime.now().isoformat(),
                }
        key = f"{stock_code.zfill(5)}|{company_name}"
        fields[key] = record_fields

    output = []
    for key, field_dict in fields.items():
        code, name = key.split("|", 1)
        verified_fields = {}
        for fname, finfo in field_dict.items():
            verified_fields[fname] = finfo["value"]
        output.append({
            "stock_code": code,
            "company_name": name,
            "source_url": source_url,
            "source_name": source_name,
            "fetched_at": datetime.now().isoformat(),
            "verified_fields": verified_fields,
        })

    out_path = Path(args.output or f"data/verified_current_ipos_{date.today().isoformat()}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"analysis_date": date.today().isoformat(), "universe_rule": "手工核验", "records": output}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存 {len(output)} 条记录到 {out_path}")


def _parse_value(val: str):
    if val.lower() in ("true", "yes", "是"):
        return True
    if val.lower() in ("false", "no", "否"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    if "," in val and not val.startswith("HK"):
        return [v.strip() for v in val.split(",")]
    return val


def main() -> None:
    parser = argparse.ArgumentParser(description="港股新股打新每日分析系统")
    parser.add_argument("--config", default="config/config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="运行一次日报")
    daily.add_argument("--date", type=parse_date)
    daily.add_argument("--input-json", help="使用本地 JSON，适合离线测试或人工数据")
    daily.add_argument("--skip-pdf", action="store_true", help="不下载/解析招股书")

    verify = subparsers.add_parser("verify", help="交互式手工核验 IPO 数据")
    verify.add_argument("--code", help="股票代码")
    verify.add_argument("--name", help="公司名称")
    verify.add_argument("--source-url", help="数据来源 URL")
    verify.add_argument("--source-name", help="数据来源名称")
    verify.add_argument("--from-csv", help="从 CSV 模板批量导入")
    verify.add_argument("-o", "--output", help="输出 JSON 文件路径")

    backtest = subparsers.add_parser("backtest", help="回测评分模型")
    backtest.add_argument("--days-back", type=int, default=730, help="回测历史天数（默认 730）")

    schedule = subparsers.add_parser("schedule", help="前台运行 APScheduler")
    schedule.add_argument("--hour", type=int, default=8)
    schedule.add_argument("--minute", type=int, default=0)
    schedule.add_argument("--skip-pdf", action="store_true")

    args = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config["app"].get("log_level", "INFO"), str(project_path(config, "logs/hk_ipo.log")))

    if args.command == "daily":
        run_once(args, config)
    elif args.command == "verify":
        cmd_verify(args, config)
    elif args.command == "backtest":
        from hk_ipo_analyzer.analysis.backtest import run_backtest
        run_backtest(config, args.days_back)
    elif args.command == "schedule":
        scheduler = BlockingScheduler(timezone=config["app"].get("timezone", "Asia/Shanghai"))
        scheduler.add_job(
            lambda: DailyPipeline(config).run(date.today(), skip_pdf=args.skip_pdf),
            "cron", hour=args.hour, minute=args.minute, id="hk_ipo_daily", replace_existing=True,
        )
        logging.getLogger(__name__).info("定时器已启动：每日 %02d:%02d", args.hour, args.minute)
        scheduler.start()


if __name__ == "__main__":
    main()
