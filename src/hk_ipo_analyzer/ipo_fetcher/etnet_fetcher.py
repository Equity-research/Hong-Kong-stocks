from __future__ import annotations

import logging
import re
import json
from bs4 import BeautifulSoup

from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

ETNET_IPO_URL = "https://www.etnet.com.hk/www/tc/stocks/ipo-info.php"
SOURCE_NAME = "etnet"


def _clean_code(stock_code: str) -> str:
    return str(int(stock_code))


def _safe_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(text).strip())
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_hkd_amount(text: str) -> float | None:
    m = re.search(r"([\d.,]+)\s*([億亿万萬千]?)", str(text))
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
    return num * mult.get(m.group(2) or "", 1)


class EtnetFetcher:
    """从 etnet 提取完整 IPO 数据：基本资料、基石、保荐人、孖展。"""

    def __init__(self, client: PoliteHttpClient):
        self.client = client

    def enrich(self, record: IPORecord) -> IPORecord:
        try:
            code = _clean_code(record.stock_code)
            url = f"{ETNET_IPO_URL}?code={code}"
            resp = self.client.get(url)
            resp.encoding = "utf-8"
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            self._parse_script_data(html, record, url)
            self._parse_visible_tables(soup, record, url)

            c_url = f"{ETNET_IPO_URL}?code={code}&tab=cornerstone"
            c_resp = self.client.get(c_url)
            c_soup = BeautifulSoup(c_resp.text, "html.parser")
            self._parse_cornerstone_table(c_soup, record, c_url)

            s_url = f"{ETNET_IPO_URL}?code={code}&tab=sponsor"
            s_resp = self.client.get(s_url)
            s_soup = BeautifulSoup(s_resp.text, "html.parser")
            self._parse_sponsor_table(s_soup, record, s_url)

            LOGGER.info("etnet 数据已补充：%s %s", record.stock_code, record.company_name)
        except Exception:
            LOGGER.warning("etnet 抓取失败：%s %s", record.stock_code, record.company_name, exc_info=True)
        return record

    def enrich_all(self, records: list[IPORecord]) -> list[IPORecord]:
        for record in records:
            self.enrich(record)
        return records

    # ---- Script 55 JSON ----

    def _parse_script_data(self, html: str, record: IPORecord, url: str) -> None:
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for s in scripts:
            if "stockcode" not in s or "stocknametc" not in s:
                continue
            objects = re.findall(r"\{[^}]*\"stockcode\"[^}]*\}", s)
            all_data = []
            for o in objects:
                try:
                    all_data.append(json.loads(o))
                except json.JSONDecodeError:
                    pass
            if not all_data:
                continue
            for item in all_data:
                if item.get("stockcode") == record.stock_code:
                    self._apply_script_fields(item, record, url)
                    return

    def _apply_script_fields(self, data: dict, record: IPORecord, url: str) -> None:
        src = SOURCE_NAME
        if data.get("listprice") and data["listprice"] not in ("--", ""):
            p = _safe_float(data["listprice"])
            if p:
                record.set_field("offer_price_low", p, url, src)
                record.set_field("offer_price_high", p, url, src)
                record.set_field("offer_price_range", f"HK${p:g}", url, src)
        if data.get("boardlot"):
            record.set_field("board_lot", int(data["boardlot"]), url, src)
        if data.get("admissionfee") and data["admissionfee"] not in ("--", ""):
            fee = _safe_float(data["admissionfee"].replace("$", "").replace(",", ""))
            if fee:
                record.set_field("entry_fee_hkd", fee, url, src)
        if data.get("applicationstart") and data["applicationstart"] != "--":
            record.set_field("offer_start_date", data["applicationstart"].replace("/", "-"), url, src)
        if data.get("applicationend") and data["applicationend"] != "--":
            record.set_field("offer_end_date", data["applicationend"].replace("/", "-"), url, src)
        if data.get("resultdate") and data["resultdate"] != "--":
            record.set_field("allotment_result_date", data["resultdate"].replace("/", "-"), url, src)
        if data.get("listdate") and data["listdate"] != "--":
            record.set_field("listing_date", data["listdate"].replace("/", "-"), url, src)
        nature = data.get("naturesc") or data.get("naturetc") or data.get("natureeng")
        if nature and not record.value("sector"):
            record.set_field("sector", nature, url, src)
        if data.get("oversubscribtionrate") and data["oversubscribtionrate"] not in ("--", ""):
            over = _safe_float(data["oversubscribtionrate"])
            if over:
                record.set_field("expected_oversubscription", over, url, src)

    # ---- 可见表格 ----

    def _parse_visible_tables(self, soup: BeautifulSoup, record: IPORecord, url: str) -> None:
        text = soup.get_text(" ", strip=True)
        src = SOURCE_NAME
        if not record.value("offer_size_hkd"):
            m = re.search(r"(?:集資(?:額|總額|金额)|募集資金|發售規模)[^\d]{0,80}HK\$?\s*([\d.,]+)\s*([億亿万萬千]?)", text)
            if m:
                amt = float(m.group(1).replace(",", ""))
                mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
                record.set_field("offer_size_hkd", amt * mult.get(m.group(2) or "", 1), url, src)
        if not record.value("public_offer_ratio"):
            m = re.search(r"(?:公開發售|香港發售).{0,40}(\d[\d.]*)\s*%", text)
            if m:
                record.set_field("public_offer_ratio", float(m.group(1)), url, src)
        if not record.value("greenshoe"):
            if re.search(r"(?:綠鞋|绿鞋|Greenshoe|超額配股權|超额配股权)", text, re.I):
                record.set_field("greenshoe", True, url, src)

    # ---- 基石表格 ----

    def _parse_cornerstone_table(self, soup: BeautifulSoup, record: IPORecord, url: str) -> None:
        src = SOURCE_NAME + " 基石"
        table = soup.find("table")
        if not table:
            return
        rows = table.find_all("tr")
        investors = []
        total_ratio = 0.0
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells or len(cells) < 2:
                continue
            name = cells[0]
            if not name or name in ("--", "合計", "合计", "總計", "总计"):
                continue
            if re.match(r"^\d+間$", name):
                continue
            if len(name) < 2:
                continue
            investors.append(name)
            if len(cells) >= 4:
                ratio = _safe_float(cells[3])
                if ratio:
                    total_ratio += ratio
        if investors:
            record.set_field("cornerstone_investors", investors[:20], url, src)
            record.set_field("cornerstone_count", len(investors), url, src)
        if total_ratio > 0 and not record.value("cornerstone_ratio"):
            record.set_field("cornerstone_ratio", round(total_ratio, 1), url, src)
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            for c in cells:
                m = re.search(r"(\d+)\s*(?:個月|个月|month)", c, re.I)
                if m and not record.value("cornerstone_lockup_months"):
                    record.set_field("cornerstone_lockup_months", int(m.group(1)), url, src)
                    break

    # ---- 保荐人表格 ----

    def _parse_sponsor_table(self, soup: BeautifulSoup, record: IPORecord, url: str) -> None:
        src = SOURCE_NAME + " 保荐人"
        table = soup.find("table")
        if not table:
            return
        rows = table.find_all("tr")
        sponsors = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            name = cells[0]
            if not name or name in ("--", "保薦人名稱", "保荐人名称"):
                continue
            # Filter out non-name content
            if re.search(r"[\u4e00-\u9fffA-Z]", name) and len(name) > 2 and len(name) < 60:
                if re.match(r"^\d+間$", name):
                    continue
                sponsors.append(name)
        if sponsors:
            record.set_field("sponsors", sponsors[:10], url, src)

    # ---- 孖展热度（尝试 margin 页面） ----

    def fetch_market_heat(self, record: IPORecord) -> None:
        try:
            code = _clean_code(record.stock_code)
            url = f"{ETNET_IPO_URL}?code={code}"
            resp = self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            src = SOURCE_NAME + " 孖展"
            if not record.value("margin_multiple"):
                m = re.search(r"(?:孖展倍數|孖展倍数|超購倍數|超购倍数|認購倍數|认购倍数|倍率)[^\d]{0,20}([\d.]+)\s*倍", text)
                if m:
                    record.set_field("margin_multiple", float(m.group(1)), url, src)
            if not record.value("news_heat_score"):
                m = re.search(r"(?:關注度|关注度|熱度|热度|heat)[^\d]{0,20}([0-3])", text, re.I)
                if m:
                    record.set_field("news_heat_score", int(m.group(1)), url, src)
        except Exception:
            LOGGER.debug("etnet 孖展获取失败：%s", record.stock_code, exc_info=True)
