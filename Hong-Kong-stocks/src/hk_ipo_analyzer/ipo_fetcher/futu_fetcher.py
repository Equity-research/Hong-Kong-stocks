from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

FUTU_IPO_URL = "https://www.futunn.com/stock/{code}-HK/ipo"
SOURCE_NAME = "富途"


def _clean_code(stock_code: str) -> str:
    return str(int(stock_code))


def _parse_hkd(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
    return num * mult.get(m.group(2) or "", 1)


class FutuFetcher:
    """从富途获取 IPO 详情：基石名单/占比/金额、保荐人、财务、孖展、暗盘。"""

    def __init__(self, client: PoliteHttpClient):
        self.client = client
        self.client.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.futunn.com/",
        })

    def enrich(self, record: IPORecord) -> IPORecord:
        try:
            code = _clean_code(record.stock_code)
            url = FUTU_IPO_URL.format(code=code)
            resp = self.client.get(url)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) < 200:
                LOGGER.debug("富途页面内容过短，可能需登录或反爬：%s", record.stock_code)
                return record
            self._parse_cornerstone(text, record, url)
            self._parse_sponsors(text, record, url)
            self._parse_financial(text, record, url)
            self._parse_margin(text, record, url)
            self._parse_grey(text, record, url)
            self._parse_offer_details(text, record, url)
            LOGGER.info("富途数据已补充：%s %s", record.stock_code, record.company_name)
        except Exception:
            LOGGER.warning("富途抓取失败：%s %s", record.stock_code, record.company_name, exc_info=True)
        return record

    def enrich_all(self, records: list[IPORecord]) -> list[IPORecord]:
        for record in records:
            self.enrich(record)
        return records

    # ---- 基石 ----
    def _parse_cornerstone(self, text: str, record: IPORecord, url: str) -> None:
        section = self._find_section(text, ["基石投资者", "基石投資者", "Cornerstone"])
        if not section:
            return
        if not record.value("cornerstone_count"):
            names = re.findall(
                r"(?:[A-Z][A-Za-z&.,'()\- ]{8,80}(?:Limited|Ltd\.?|Inc\.?|Corp\.?|Capital|Holdings|Group|Investment|Fund|Asset|Management|Partners?|Securities|International|Asia|China|Financial|Bank|Trust|Venture|Private|Equity))",
                section,
            )
            if not names:
                names = re.findall(
                    r"([\u4e00-\u9fff（）()]{3,18}(?:集團|控股|有限|投资|科技|基金|资产|资本|证券|医疗|医药|生物|电子|半导体|机器人|能源|材料|化工|消费|零售|地产|金融|保险|银行|国际|香港|中国|企業|公司))",
                    section,
                )
            if names:
                clean = list({n.strip() for n in names[:20]})
                record.set_field("cornerstone_investors", clean, url, SOURCE_NAME)
                record.set_field("cornerstone_count", len(clean), url, SOURCE_NAME)
        if not record.value("cornerstone_ratio"):
            ratio = re.search(r"([\d.]+)\s*%[^%]{0,40}(?:基石|cornerstone)", section, re.I)
            if not ratio:
                ratio = re.search(r"(?:佔|占|約|相当于)[^\d]{0,60}([\d.]+)\s*%", section)
            if ratio:
                record.set_field("cornerstone_ratio", float(ratio.group(1)), url, SOURCE_NAME)
        if not record.value("cornerstone_amount_hkd"):
            amt = _parse_hkd(section, r"(?:總額|總認購|認購總額|投资总额)[^\d]{0,40}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if amt:
                record.set_field("cornerstone_amount_hkd", amt, url, SOURCE_NAME)

    # ---- 保荐人 ----
    def _parse_sponsors(self, text: str, record: IPORecord, url: str) -> None:
        if record.value("sponsors"):
            return
        match = re.search(r"(?:保薦人|保荐人|獨家保薦人|独家保荐人|聯席保薦人|联席保荐人)", text)
        if not match:
            return
        frag = text[match.end():match.end() + 2000]
        names = re.findall(r"([\u4e00-\u9fff（）()·]{2,20}(?:國際|资本|證券|证券|融資|融资|企業|企业|銀行|银行|金融|香港|亞洲|中国|中國|集團|集团|有限|公司))", frag)
        if not names:
            names = re.findall(r"([A-Z][A-Za-z&., ]{5,60}(?:Limited|Ltd\.?|Capital|Securities|International|Asia|Hong Kong|China|Financial|Corporate))", frag)
        if names:
            clean = list({n.strip() for n in names[:10]})
            record.set_field("sponsors", clean, url, SOURCE_NAME)

    # ---- 财务 ----
    def _parse_financial(self, text: str, record: IPORecord, url: str) -> None:
        section = self._find_section(text, ["财务数据", "財務數據", "業績", "业绩", "财务摘要"])
        if not section:
            return
        if not record.value("revenue"):
            rev = _parse_hkd(section, r"(?:營業收入|营业收入|收益|Revenue)[^\d]{0,60}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if rev:
                record.set_field("revenue", rev, url, SOURCE_NAME)
        if not record.value("net_profit"):
            prof = _parse_hkd(section, r"(?:淨利潤|净利润|純利|纯利|Net Profit)[^\d]{0,60}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if prof:
                record.set_field("net_profit", prof, url, SOURCE_NAME)
        if not record.value("gross_margin_latest"):
            gm = re.search(r"(?:毛利[率]?|Gross Margin)[^%\d]{0,60}([\d.]+)\s*%", section, re.I)
            if gm:
                record.set_field("gross_margin_latest", float(gm.group(1)), url, SOURCE_NAME)
        if not record.value("net_margin_pct"):
            nm = re.search(r"(?:淨利[率]?|净利[率]?|純利[率]?|Net Margin)[^%\d]{0,60}([\d.]+)\s*%", section, re.I)
            if nm:
                record.set_field("net_margin_pct", float(nm.group(1)), url, SOURCE_NAME)
        if not record.value("revenue_growth_pct"):
            growth = re.search(r"(?:收入增長|收入增长|營收增長|複合增長|复合增长|CAGR|同比增長|同比增长)[^%\d]{0,60}([\d.]+)\s*%", section)
            if growth:
                record.set_field("revenue_growth_pct", float(growth.group(1)), url, SOURCE_NAME)

    # ---- 孖展 ----
    def _parse_margin(self, text: str, record: IPORecord, url: str) -> None:
        if not record.value("margin_multiple"):
            mult = re.search(r"(?:孖展倍數|孖展倍数|融资倍数|超購倍數|超购倍数|認購倍數|认购倍数|Margin Multiple)[^\d]{0,20}([\d.]+)\s*倍", text)
            if mult:
                record.set_field("margin_multiple", float(mult.group(1)), url, SOURCE_NAME)
        if not record.value("margin_amount_hkd"):
            amt = _parse_hkd(text, r"(?:孖展金額|孖展金额|融资额|融資額|Margin Amount)[^\d]{0,60}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if amt:
                record.set_field("margin_amount_hkd", amt, url, SOURCE_NAME)
        if not record.value("expected_oversubscription"):
            over = re.search(r"(?:預計超購|预计超购|預期超購|预期超购)[^\d]{0,20}([\d.]+)\s*倍", text)
            if over:
                record.set_field("expected_oversubscription", float(over.group(1)), url, SOURCE_NAME)

    # ---- 暗盘 ----
    def _parse_grey(self, text: str, record: IPORecord, url: str) -> None:
        if record.value("grey_market_return_pct"):
            return
        grey = re.search(r"(?:暗盤|暗盘|Grey Market)[^\d%]{0,120}([+-]?[\d.]+)\s*%", text, re.I)
        if grey:
            record.set_field("grey_market_return_pct", float(grey.group(1)), url, SOURCE_NAME)

    # ---- 发行详情 ----
    def _parse_offer_details(self, text: str, record: IPORecord, url: str) -> None:
        if not record.value("market_cap_hkd"):
            cap = _parse_hkd(text, r"(?:發行市值|发行市值|市值|Market Cap)[^\d]{0,40}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)")
            if cap:
                record.set_field("market_cap_hkd", cap, url, SOURCE_NAME)
        if not record.value("public_offer_ratio"):
            ratio = re.search(r"(?:公開發售|公开发售|香港發售|香港发售)[^\d]{0,40}(\d[\d.]*)\s*%", text)
            if ratio:
                record.set_field("public_offer_ratio", float(ratio.group(1)), url, SOURCE_NAME)
        if not record.value("greenshoe"):
            if re.search(r"(?:綠鞋|绿鞋|Greenshoe|超額配股權|超额配股权)", text, re.I):
                record.set_field("greenshoe", True, url, SOURCE_NAME)

    @staticmethod
    def _find_section(text: str, keywords: list[str]) -> str:
        for kw in keywords:
            match = re.search(re.escape(kw), text, re.I)
            if match:
                start = max(0, match.start() - 200)
                end = min(len(text), match.end() + 5000)
                return text[start:end]
        return ""
