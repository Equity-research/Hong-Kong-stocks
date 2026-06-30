from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.analysis.sector_classifier import SectorClassifier
from hk_ipo_analyzer.config import project_path
from hk_ipo_analyzer.historical import HistoricalDB, HistoricalFetcher
from hk_ipo_analyzer.ipo_fetcher.broker_heat_fetcher import BrokerHeatFetcher
from hk_ipo_analyzer.ipo_fetcher.calendar_fetcher import CalendarFetcher
from hk_ipo_analyzer.ipo_fetcher.etnet_fetcher import EtnetFetcher
from hk_ipo_analyzer.ipo_fetcher.futu_api_fetcher import FutuAPIFetcher
from hk_ipo_analyzer.ipo_fetcher.hkex_fetcher import HKEXFetcher
from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.ipo_fetcher.prospectus_downloader import ProspectusDownloader
from hk_ipo_analyzer.ipo_parser.cornerstone_parser import CornerstoneParser
from hk_ipo_analyzer.ipo_parser.financial_parser import FinancialParser
from hk_ipo_analyzer.ipo_parser.prospectus_parser import ProspectusParser
from hk_ipo_analyzer.ipo_parser.risk_parser import RiskParser
from hk_ipo_analyzer.ipo_parser.sponsor_parser import SponsorParser
from hk_ipo_analyzer.models import IPORecord
from hk_ipo_analyzer.reporting import update_summary_csv, write_report
from hk_ipo_analyzer.storage import SQLiteStore, save_raw_json

LOGGER = logging.getLogger(__name__)


class DailyPipeline:
    def __init__(self, config: dict):
        self.config = config
        self.client = PoliteHttpClient(config["http"])
        self.hkex = HKEXFetcher(self.client, config["sources"])
        self.etnet = EtnetFetcher(self.client)
        self.futu_api = FutuAPIFetcher()
        self.financial_parser = FinancialParser()
        self.sponsor_parser = SponsorParser()
        self.historical_db = HistoricalDB(project_path(config, "data/historical_ipos.db"))
        self.historical_fetcher = HistoricalFetcher(self.client, self.historical_db)

    def run(self, day: date, input_json: Path | None = None, skip_pdf: bool = False) -> Path:
        records = self._load_input(input_json) if input_json else self.hkex.fetch_current_listings()
        LOGGER.info("获取到 %s 条新股记录", len(records))

        manual_path = project_path(self.config, self.config["paths"]["manual_override_csv"])
        CalendarFetcher(manual_path).apply(records, day)
        BrokerHeatFetcher(manual_path).apply(records, day)

        self._fetch_online_sources(records)  # always enrich from etnet/aastocks
        self.futu_api.enrich_all(records)


        if not skip_pdf:
            self._parse_prospectuses(records)
        self._derive_fields(records)
        records = self._filter_current_offers(records, day)

        classifier = SectorClassifier()
        for record in records:
            if not record.value("sector"):
                sector = classifier.classify(record)
                record.set_field("sector", sector, None, "规则分类器")
            record.fill_expected_nulls()

        self._enrich_with_historical_stats(records)

        model = ScoringModel(
            hot_sectors=self.config.get("scoring", {}).get("hot_sectors", []),
            max_missing_penalty=self.config.get("scoring", {}).get("max_data_missing_penalty", 8),
        )
        items = [(record, model.score(record)) for record in records]
        store = SQLiteStore(project_path(self.config, self.config["app"]["database"]))
        try:
            for record, score in items:
                save_raw_json(project_path(self.config, self.config["paths"]["raw_dir"]), day, record)
                store.save(day, record, score)
        finally:
            store.close()
        update_summary_csv(project_path(self.config, self.config["paths"]["summary_csv"]), day, items)
        report = write_report(project_path(self.config, self.config["paths"]["report_dir"]), day, items)
        LOGGER.info("日报已生成：%s（%s 只新股）", report, len(items))
        return report

    def _fetch_online_sources(self, records: list[IPORecord]) -> None:
        """?? etnet ????????"""
        for record in records:
            try:
                self.etnet.enrich(record)
                self.etnet.fetch_market_heat(record)
            except Exception:
                LOGGER.debug("etnet ?????%s", record.stock_code, exc_info=True)

    def _enrich_with_historical_stats(self, records: list[IPORecord]) -> None:
        """????????????????"""
        try:
            self.historical_fetcher.fetch_recent(days_back=730)
        except Exception:
            LOGGER.debug("????????????????", exc_info=True)
        for record in records:
            sector = record.value("sector")
            if not sector:
                continue
            if not record.value("peer_median_first_day_return_pct"):
                peer_return = self.historical_db.get_peer_return(sector)
                if peer_return is not None:
                    record.set_field("peer_median_first_day_return_pct", peer_return, None, "???????")

    @staticmethod
    def _filter_current_offers(records: list[IPORecord], day: date) -> list[IPORecord]:
        active: list[IPORecord] = []
        for record in records:
            start = DailyPipeline._as_date(record.value("offer_start_date"))
            end = DailyPipeline._as_date(record.value("offer_end_date"))
            if start is None or end is None:
                LOGGER.warning("排除未核实招股日期的记录：%s %s", record.stock_code, record.company_name)
                continue
            if start <= day <= end:
                active.append(record)
            else:
                LOGGER.info(
                    "排除非当日可申购记录：%s %s（%s 至 %s）",
                    record.stock_code, record.company_name, start, end,
                )
        return active

    @staticmethod
    def _as_date(value) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip()[:10].replace("/", "-"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _load_input(path: Path) -> list[IPORecord]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("records", [])
        records: list[IPORecord] = []
        for row in rows:
            if "verified_fields" not in row:
                records.append(IPORecord.from_dict(row))
                continue
            record = IPORecord(str(row["stock_code"]).zfill(4), row["company_name"])
            source_url = row.get("source_url")
            source_name = row.get("source_name", "核验输入")
            fetched_at = row.get("fetched_at")
            for name, value in row["verified_fields"].items():
                record.set_field(name, value, source_url, source_name, fetched_at)
            records.append(record)
        return records

    def _parse_prospectuses(self, records: list[IPORecord]) -> None:
        downloader = ProspectusDownloader(
            self.client, project_path(self.config, self.config["paths"]["prospectus_dir"])
        )
        prospectus_parser = ProspectusParser()
        cornerstone_parser = CornerstoneParser()
        for record in records:
            candidates = [d for d in record.documents if d.get("document_type") == "prospectus"]
            for document in candidates[:1]:
                pdf_documents = self.hkex.resolve_pdf_links(document)
                for pdf in pdf_documents[:1]:
                    path = downloader.download(record.stock_code, pdf["url"])
                    if not path:
                        continue
                    try:
                        text = prospectus_parser.parse(path, record, pdf["url"])
                        self.financial_parser.parse(text, record, pdf["url"])
                        self.financial_parser.parse_from_pdf(path, record, pdf["url"])
                        cornerstone_parser.parse(text, record, pdf["url"])
                        self.sponsor_parser.parse(text, record, pdf["url"])
                        RiskParser().parse(text, record, pdf["url"])
                    except Exception:
                        LOGGER.exception("解析招股书失败：%s", path)

    @staticmethod
    def _derive_fields(records: list[IPORecord]) -> None:
        for record in records:
            high = record.value("offer_price_high")
            lot = record.value("board_lot")
            if high is not None and lot is not None and record.value("entry_fee_hkd") is None:
                fee = round(float(high) * int(lot) * 1.01, 2)
                record.set_field("entry_fee_hkd", fee, None, "规则计算：最高价×一手股数×1.01")
