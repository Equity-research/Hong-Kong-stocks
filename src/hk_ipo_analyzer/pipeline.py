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
from hk_ipo_analyzer.ipo_parser.offer_structure_parser import OfferStructureParser
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

    def run(
        self,
        day: date,
        input_json: Path | None = None,
        skip_pdf: bool = False,
        offline: bool = False,
    ) -> Path:
        records = self._load_input(input_json) if input_json else self.hkex.fetch_current_listings()
        LOGGER.info("获取到 %s 条新股记录", len(records))

        manual_path = project_path(self.config, self.config["paths"]["manual_override_csv"])
        CalendarFetcher(manual_path).apply(records, day)
        BrokerHeatFetcher(manual_path).apply(records, day)

        if not offline:
            self._fetch_online_sources(records)
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
            self._annotate_financial_metadata(record)
            record.fill_expected_nulls()

        self._enrich_with_historical_stats(records, refresh=not offline)

        model = ScoringModel(
            hot_sectors=self.config.get("scoring", {}).get("hot_sectors", []),
            max_missing_penalty=self.config.get("scoring", {}).get("max_data_missing_penalty", 8),
        )
        items = []
        for record in records:
            official_record = record.resolved("official")
            enhanced_record = record.resolved("enhanced")
            self._derive_view_fields(official_record)
            self._derive_view_fields(enhanced_record)
            official_record.fill_expected_nulls()
            enhanced_record.fill_expected_nulls()
            items.append((enhanced_record, model.score(official_record, day), model.score(enhanced_record, day)))
        store = SQLiteStore(project_path(self.config, self.config["app"]["database"]))
        try:
            for record, official_score, enhanced_score in items:
                save_raw_json(project_path(self.config, self.config["paths"]["raw_dir"]), day, record)
                store.save(day, record, official_score, enhanced_score)
        finally:
            store.close()
        update_summary_csv(project_path(self.config, self.config["paths"]["summary_csv"]), day, items)
        report = write_report(project_path(self.config, self.config["paths"]["report_dir"]), day, items)
        LOGGER.info("日报已生成：%s（%s 只新股）", report, len(items))
        return report

    def _fetch_online_sources(self, records: list[IPORecord]) -> None:
        """始终使用 etnet 补充缺失字段；已有值保留为首选，同时记录候选证据。"""
        for record in records:
            try:
                self.etnet.enrich(record)
                self.etnet.fetch_market_heat(record)
            except Exception:
                LOGGER.debug("etnet 补充失败：%s", record.stock_code, exc_info=True)

    def _enrich_with_historical_stats(self, records: list[IPORecord], refresh: bool = True) -> None:
        """用历史 IPO 数据补充同行首日表现。"""
        if refresh:
            try:
                self.historical_fetcher.fetch_recent(days_back=730)
            except Exception:
                LOGGER.debug("历史 IPO 更新失败，继续使用本地缓存", exc_info=True)
        for record in records:
            sector = record.value("sector")
            if not sector:
                continue
            if not record.value("peer_median_first_day_return_pct"):
                peer_return = self.historical_db.get_peer_return(sector)
                if peer_return is not None:
                    record.set_field("peer_median_first_day_return_pct", peer_return, None, "历史 IPO 统计", source_tier="A")

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
            record.risk_tags.extend(row.get("risk_tags", []))
            source_url = row.get("source_url")
            source_name = row.get("source_name", "核验输入")
            fetched_at = row.get("fetched_at")
            for name, value in row["verified_fields"].items():
                if isinstance(value, dict) and "value" in value:
                    record.set_field(
                        name,
                        value["value"],
                        value.get("source_url", source_url),
                        value.get("source_name", source_name),
                        value.get("fetched_at", fetched_at),
                        source_tier=value.get("source_tier"),
                        period=value.get("period"),
                        currency=value.get("currency"),
                        confidence=value.get("confidence"),
                    )
                else:
                    record.set_field(name, value, source_url, source_name, fetched_at)
            prospectus_url = row.get("prospectus_url")
            if prospectus_url:
                record.documents.append({
                    "document_type": "prospectus",
                    "title": "全球发售 / 招股章程",
                    "url": prospectus_url,
                    "source_name": "HKEXnews",
                    "fetched_at": fetched_at,
                })
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
                        OfferStructureParser().parse(text, record, pdf["url"])
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

    @staticmethod
    def _derive_view_fields(record: IPORecord) -> None:
        market_cap = record.value("market_cap_hkd")
        revenue = record.value("revenue")
        profit = record.value("net_profit")
        if market_cap and profit is not None and profit > 0 and record.value("issuer_pe") is None:
            record.set_field("issuer_pe", round(float(market_cap) / float(profit), 2), None, "规则计算：市值÷同期间利润", source_tier="A")
        elif market_cap and revenue and record.value("issuer_ps") is None:
            record.set_field("issuer_ps", round(float(market_cap) / float(revenue), 2), None, "规则计算：市值÷同期间收入", source_tier="A")
        issuer_pe = record.value("issuer_pe")
        peer_pe = record.value("peer_median_pe")
        if issuer_pe and peer_pe and record.value("valuation_score") is None:
            discount = float(issuer_pe) / float(peer_pe)
            score = 2 if discount <= 0.8 else 1 if discount <= 1 else -1 if discount <= 1.3 else -3
            record.set_field("valuation_score", score, None, "规则计算：发行PE相对同行PE", source_tier="A")

    @staticmethod
    def _annotate_financial_metadata(record: IPORecord) -> None:
        period = record.value("financial_period")
        currency = record.value("financial_currency")
        for name in ("revenue", "net_profit", "adjusted_net_profit", "revenue_growth_pct", "net_margin_pct", "gross_margin_latest", "operating_cash_flow", "debt_to_assets_pct"):
            for item in record.evidence_candidates.get(name, []):
                if item.period is None and period:
                    item.period = str(period)
                if item.currency is None and currency:
                    item.currency = str(currency)
