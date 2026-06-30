from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from hk_ipo_analyzer.analysis.scoring_model import ScoringModel
from hk_ipo_analyzer.analysis.sector_classifier import SectorClassifier
from hk_ipo_analyzer.config import project_path
from hk_ipo_analyzer.ipo_fetcher.broker_heat_fetcher import BrokerHeatFetcher
from hk_ipo_analyzer.ipo_fetcher.calendar_fetcher import CalendarFetcher
from hk_ipo_analyzer.ipo_fetcher.hkex_fetcher import HKEXFetcher
from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.ipo_fetcher.prospectus_downloader import ProspectusDownloader
from hk_ipo_analyzer.ipo_parser.cornerstone_parser import CornerstoneParser
from hk_ipo_analyzer.ipo_parser.financial_parser import FinancialParser
from hk_ipo_analyzer.ipo_parser.prospectus_parser import ProspectusParser
from hk_ipo_analyzer.ipo_parser.risk_parser import RiskParser
from hk_ipo_analyzer.models import IPORecord
from hk_ipo_analyzer.reporting import update_summary_csv, write_report
from hk_ipo_analyzer.storage import SQLiteStore, save_raw_json

LOGGER = logging.getLogger(__name__)


class DailyPipeline:
    def __init__(self, config: dict):
        self.config = config
        self.client = PoliteHttpClient(config["http"])
        self.hkex = HKEXFetcher(self.client, config["sources"])

    def run(self, day: date, input_json: Path | None = None, skip_pdf: bool = False) -> Path:
        records = self._load_input(input_json) if input_json else self.hkex.fetch_current_listings()
        manual_path = project_path(self.config, self.config["paths"]["manual_override_csv"])
        CalendarFetcher(manual_path).apply(records, day)
        BrokerHeatFetcher(manual_path).apply(records, day)
        if not skip_pdf:
            self._parse_prospectuses(records)
        self._derive_fields(records)
        classifier = SectorClassifier()
        for record in records:
            if not record.value("sector"):
                sector = classifier.classify(record)
                record.set_field("sector", sector, None, "规则分类器")
            record.fill_expected_nulls()

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

    @staticmethod
    def _load_input(path: Path) -> list[IPORecord]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("records", [])
        return [IPORecord.from_dict(row) for row in rows]

    def _parse_prospectuses(self, records: list[IPORecord]) -> None:
        downloader = ProspectusDownloader(
            self.client, project_path(self.config, self.config["paths"]["prospectus_dir"])
        )
        prospectus_parser = ProspectusParser()
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
                        FinancialParser().parse(text, record, pdf["url"])
                        CornerstoneParser().parse(text, record, pdf["url"])
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
