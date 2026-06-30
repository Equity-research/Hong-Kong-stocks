from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

AASTOCKS_IPO_URL = "https://www.aastocks.com/tc/stocks/analysis/ipo.aspx?symbol={code}"
SOURCE_NAME = "AAStocks"


def _clean_code(stock_code: str) -> str:
    return str(int(stock_code))


def _parse_hkd_amount(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    num = float(match.group(1).replace(",", ""))
    unit = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
    multipliers = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
    return num * multipliers.get(unit, 1)


class AAStocksFetcher:
    """从 AAStocks 获取孖展实时数据、暗盘价、行业对比。"""

    def __init__(self, client: PoliteHttpClient):
        self.client = client
        self.client.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.aastocks.com/",
        })

    def enrich(self, record: IPORecord) -> IPORecord:
        try:
            code = _clean_code(record.stock_code)
            url = AASTOCKS_IPO_URL.format(code=code)
            resp = self.client.get(url)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            if len(text) < 100:
                LOGGER.debug("AAStocks 页面内容过短，可能需反爬：%s", record.stock_code)
                return record
            self._parse_margin_heat(text, record, url)
            self._parse_grey_market(text, record, url)
            self._parse_peer_comparison(text, record, url)
            self._parse_market_cap(text, record, url)
            LOGGER.info("AAStocks 数据已补充：%s %s", record.stock_code, record.company_name)
        except Exception:
            LOGGER.warning("AAStocks 抓取失败：%s %s", record.stock_code, record.company_name, exc_info=True)
        return record

    def enrich_all(self, records: list[IPORecord]) -> list[IPORecord]:
        for record in records:
            self.enrich(record)
        return records

    def _parse_margin_heat(self, text: str, record: IPORecord, url: str) -> None:
        if not record.value("margin_amount_hkd"):
            amt = _parse_hkd_amount(text, r"(?:孖展金額|孖展金额|融資額|融资额|Margin\s*Amount)[^\d]{0,60}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if not amt:
                amt = _parse_hkd_amount(text, r"(?:孖展總額|孖展总额)[^\d]{0,60}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if amt:
                record.set_field("margin_amount_hkd", amt, url, SOURCE_NAME)
        if not record.value("margin_multiple"):
            mult = re.search(r"(?:超額倍數|超额倍数|認購倍數|认购倍数|超購倍數|超购倍数)[^\d]{0,20}([\d.]+)\s*倍", text)
            if not mult:
                mult = re.search(r"(?:孖展倍數|孖展倍数|Margin\s*Multiple)[^\d]{0,20}([\d.]+)\s*倍", text, re.I)
            if mult:
                record.set_field("margin_multiple", float(mult.group(1)), url, SOURCE_NAME)
        if not record.value("expected_oversubscription"):
            over = re.search(r"(?:預計超購|预计超购|預期超購|预期超购)[^\d]{0,20}([\d.]+)\s*倍", text)
            if over:
                record.set_field("expected_oversubscription", float(over.group(1)), url, SOURCE_NAME)
        if not record.value("news_heat_score"):
            heat = re.search(r"(?:市場關注度|市场关注度|熱度)[^\d]{0,20}([0-3])", text)
            if heat:
                record.set_field("news_heat_score", int(heat.group(1)), url, SOURCE_NAME)

    def _parse_grey_market(self, text: str, record: IPORecord, url: str) -> None:
        if record.value("grey_market_return_pct"):
            return
        grey = re.search(r"(?:暗盤|暗盘|Grey\s*Market)[^\d%]{0,120}([+-]?[\d.]+)\s*%", text, re.I)
        if grey:
            record.set_field("grey_market_return_pct", float(grey.group(1)), url, SOURCE_NAME)

    def _parse_peer_comparison(self, text: str, record: IPORecord, url: str) -> None:
        if record.value("peer_median_first_day_return_pct"):
            return
        peer = re.search(r"(?:同類IPO|同类IPO|同業首日|同业首日|Peer\s*First\s*Day)[^\d]{0,120}([+-]?[\d.]+)\s*%", text, re.I)
        if peer:
            record.set_field("peer_median_first_day_return_pct", float(peer.group(1)), url, SOURCE_NAME)
        if not record.value("peer_median_pe"):
            pe = re.search(r"(?:同業PE|同业PE|同行市盈率)[^\d]{0,40}([\d.]+)", text)
            if pe:
                record.set_field("peer_median_pe", float(pe.group(1)), url, SOURCE_NAME)

    def _parse_market_cap(self, text: str, record: IPORecord, url: str) -> None:
        if record.value("market_cap_hkd"):
            return
        cap = _parse_hkd_amount(text, r"(?:市值|Market\s*Cap)[^\d]{0,40}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
        if cap:
            record.set_field("market_cap_hkd", cap, url, SOURCE_NAME)
