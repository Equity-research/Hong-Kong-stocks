from __future__ import annotations

import logging
from typing import Any

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.config import project_path
from hk_ipo_analyzer.historical import HistoricalDB, HistoricalFetcher
from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)


def run_backtest(config: dict, days_back: int = 730) -> dict[str, Any]:
    """用历史 IPO 数据回测评分模型，输出各维度 AUC 和准确率报告"""
    client = PoliteHttpClient(config["http"])
    db = HistoricalDB(project_path(config, "data/historical_ipos.db"))
    fetcher = HistoricalFetcher(client, db)
    fetcher.fetch_recent(days_back=days_back)

    import sqlite3
    db_path_str = str(project_path(config, "data/historical_ipos.db"))
    conn = sqlite3.connect(db_path_str)
    rows = conn.execute(
        """SELECT stock_code, company_name, sector, listing_date, offer_price,
                  first_day_close, first_day_return_pct, market_cap_hkd,
                  offer_size_hkd, public_oversubscription
           FROM historical_ipos
           WHERE first_day_return_pct IS NOT NULL"""
    ).fetchall()
    conn.close()

    if not rows:
        LOGGER.warning("历史数据库中无可回测记录")
        return {"error": "无历史数据"}

    model = ScoringModel(
        hot_sectors=config.get("scoring", {}).get("hot_sectors", []),
        max_missing_penalty=config.get("scoring", {}).get("max_data_missing_penalty", 8),
    )

    results: list[dict] = []
    for row in rows:
        record = _row_to_record(row)
        score = model.score(record)
        first_day = row[6]
        results.append({
            "stock_code": record.stock_code,
            "company_name": record.company_name,
            "score": score.total,
            "confidence": score.confidence,
            "first_day_return": first_day,
            "recommendation": score.recommendation,
            "is_win": first_day is not None and first_day > 0,
        })

    total = len(results)
    wins = sum(1 for r in results if r["is_win"])

    high_score_wins = sum(1 for r in results if r["score"] >= 75 and r["is_win"])
    high_score_total = sum(1 for r in results if r["score"] >= 75)
    high_accuracy = high_score_wins / high_score_total if high_score_total else 0

    low_score_losses = sum(1 for r in results if r["score"] < 55 and not r["is_win"])
    low_score_total = sum(1 for r in results if r["score"] < 55)
    low_accuracy = low_score_losses / low_score_total if low_score_total else 0

    positive_recs = sum(1 for r in results if r["recommendation"] in ("积极打新", "现金一手"))
    positive_wins = sum(1 for r in results if r["recommendation"] in ("积极打新", "现金一手") and r["is_win"])
    recommendation_accuracy = positive_wins / positive_recs if positive_recs else 0

    by_band = {}
    bands = [(85, "积极打新"), (75, "现金一手"), (65, "谨慎一手"), (55, "不建议打新"), (0, "放弃")]
    for threshold, label in bands:
        band_results = [r for r in results if r["score"] >= threshold]
        band_wins = sum(1 for r in band_results if r["is_win"])
        by_band[label] = {
            "count": len(band_results),
            "wins": band_wins,
            "win_rate": band_wins / len(band_results) if band_results else 0,
        }

    report = {
        "total_samples": total,
        "overall_win_rate": round(wins / total * 100, 1) if total else 0,
        "high_score_accuracy": round(high_accuracy * 100, 1),
        "low_score_accuracy": round(low_accuracy * 100, 1),
        "recommendation_accuracy": round(recommendation_accuracy * 100, 1),
        "score_bands": by_band,
    }

    LOGGER.info(
        "回测完成：%s 条记录，高分准确率 %.1f%%，推荐准确率 %.1f%%",
        total, report["high_score_accuracy"], report["recommendation_accuracy"],
    )
    print("\n=== 港股 IPO 评分模型回测报告 ===")
    print(f"样本总数: {total}")
    print(f"整体胜率: {report['overall_win_rate']}%")
    print(f"高分(≥75)准确率: {report['high_score_accuracy']}%")
    print(f"低分(<55)准确率: {report['low_score_accuracy']}%")
    print(f"推荐准确率: {report['recommendation_accuracy']}%")
    print("\n评分区间分布:")
    for label, stats in by_band.items():
        print(f"  {label}: {stats['count']}只, 胜率 {stats['win_rate']*100:.1f}%")
    return report


def _row_to_record(row: tuple) -> IPORecord:
    stock_code, company_name, sector, listing_date, offer_price, \
        first_day_close, first_day_return, market_cap, offer_size, oversubscription = row
    record = IPORecord(stock_code, company_name)
    source = "历史数据库"
    if sector:
        record.set_field("sector", sector, None, source)
    if offer_price:
        record.set_field("offer_price_low", offer_price, None, source)
        record.set_field("offer_price_high", offer_price, None, source)
    if market_cap:
        record.set_field("market_cap_hkd", market_cap, None, source)
    if offer_size:
        record.set_field("offer_size_hkd", offer_size, None, source)
    if oversubscription:
        record.set_field("actual_oversubscription", oversubscription, None, source)
    record.fill_expected_nulls()
    return record
