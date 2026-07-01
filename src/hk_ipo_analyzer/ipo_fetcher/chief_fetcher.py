"""
ChiefGroup (致富证券) HK IPO 数据抓取器

从 chiefgroup.com.hk 抓取：
- 认购倍数 (subscription_multiple / margin_multiple)
- 市盈率 (pe_ratio)
- 一手中籤率 (allotment_rate)
- 申请人数 (applicant_count)
- 入场费 / 每手股数 / 市值
- 保荐人

参考: discountifu/hk-ipo-skill 的并发抓取模式
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient

LOGGER = logging.getLogger(__name__)

CHIEF_LIST_URL = "https://www.chiefgroup.com.hk/cn/securities/hk-ipo/dp"
CHIEF_DETAIL_URL = "https://www.chiefgroup.com.hk/cn/securities/hk-ipo-detail/dp?symbol={}"

# 字段映射: ChiefGroup 表格标签 -> 标准化字段名 + 类型转换
FIELD_MAP = {
    "招股价": ("offer_price_range", str),
    "上市价": ("listing_price", str),
    "每手股数": ("lot_size", lambda x: int(x.replace(",", "")) if x else None),
    "全球发售股数": ("total_shares", str),
    "公开发售股数": ("public_shares", str),
    "国际发售股数": ("international_shares", str),
    "招股日期": ("subscription_period", str),
    "上市日期": ("listing_date", str),
    "入场费": ("entry_fee_hkd", lambda x: float(x.replace("港元", "").replace(",", "").strip()) if x else None),
    "认购倍数": ("subscription_multiple", lambda x: float(x.replace(",", "")) if x else None),
    "市价": ("market_cap_range", str),
    "市盈率": ("pe_ratio", lambda x: float(x.replace(",", "")) if x else None),
    "一手中籤率": ("allotment_rate_pct", lambda x: float(x.replace("%", "").replace(",", "")) if x and x != "-" else None),
    "申请人数": ("applicant_count", lambda x: int(x.replace(",", "")) if x and x != "-" else None),
}


class ChiefGroupFetcher:
    """致富证券 IPO 数据抓取器（并发 + 缓存）"""

    def __init__(self, client: Optional[PoliteHttpClient] = None, cache_dir: str = "data/.chief_cache"):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_html(self, url: str, cache_key: str) -> str:
        """带缓存的 HTTP 抓取"""
        cache_path = self.cache_dir / f"{cache_key}.html"
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < 1800:  # 30分钟缓存
                return cache_path.read_text(encoding="utf-8")

        if self.client:
            resp = self.client.get(url)
            html = resp.text
        else:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")

        cache_path.write_text(html, encoding="utf-8")
        return html

    def fetch_symbols(self) -> list[str]:
        """从列表页获取所有正在招股的股票代码（纯数字）"""
        html = self._fetch_html(CHIEF_LIST_URL, "chief_list")
        soup = BeautifulSoup(html, "html.parser")
        # 从详情链接提取 symbol 参数
        symbols = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "hk-ipo-detail" in href and "symbol=" in href:
                m = re.search(r"symbol=(\d+)", href)
                if m:
                    symbols.append(m.group(1))
        return list(set(symbols))  # 去重

    def fetch_detail(self, symbol: str) -> dict:
        """抓取单只 IPO 详情"""
        url = CHIEF_DETAIL_URL.format(symbol)
        try:
            html = self._fetch_html(url, f"chief_detail_{symbol}")
            return self._parse_detail(html, symbol)
        except Exception as e:
            LOGGER.warning("ChiefGroup fetch failed for %s: %s", symbol, e)
            return {"symbol": symbol, "error": str(e)}

    def _parse_detail(self, html: str, symbol: str) -> dict:
        """解析详情页 HTML，提取结构化数据"""
        soup = BeautifulSoup(html, "html.parser")
        result = {"symbol": symbol, "_fetched_at": time.time()}

        # 从所有表格提取键值对
        tables = soup.find_all("table")
        for table in tables:
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                key = cols[0].get_text(strip=True)
                # 从 span 或直接取文本
                val_el = cols[1].find("span") or cols[1]
                val = val_el.get_text(strip=True).replace("\n", "").strip()

                if key in FIELD_MAP:
                    field_name, converter = FIELD_MAP[key]
                    try:
                        result[field_name] = converter(val)
                    except (ValueError, TypeError):
                        result[field_name] = None

        # 从 Table 0 提取保荐人等
        if tables:
            for row in tables[0].find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2:
                    key = cols[0].get_text(strip=True)
                    val = cols[1].get_text(strip=True)
                    if key == "保荐人" and val and val != "-":
                        result["sponsors"] = val
                    elif key == "包销商" and val and val != "-":
                        result["underwriters"] = val
                    elif key == "股票名称" and val:
                        result["company_name"] = val
                    elif key == "股票编号" and val:
                        result["stock_code_full"] = val

        # 标准化字段：认购倍数也填到 margin_multiple（评分模型用）
        if result.get("subscription_multiple"):
            result["margin_multiple"] = result["subscription_multiple"]
            result["actual_oversubscription"] = result["subscription_multiple"]

        return result

    def fetch_all(self, max_workers: int = 6) -> dict[str, dict]:
        """并发抓取所有 IPO 详情（参考 discountifu 的 ThreadPoolExecutor 模式）"""
        symbols = self.fetch_symbols()
        if not symbols:
            LOGGER.warning("No symbols found on ChiefGroup listing page")
            return {}

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch_detail, s): s for s in symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    data = future.result()
                    results[symbol] = data
                    sub = data.get("subscription_multiple")
                    sub_str = f"{sub}x" if sub else "N/A"
                    LOGGER.info("Chief: %s -> 认购=%s", symbol, sub_str)
                except Exception as e:
                    LOGGER.error("Chief: %s failed: %s", symbol, e)
                    results[symbol] = {"symbol": symbol, "error": str(e)}

        return results

    def save_json(self, data: dict, path: str = "data/chief_all_details.json") -> Path:
        """保存抓取结果到 JSON"""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    def enrich_record(self, record: dict, chief_data: dict) -> int:
        """将 ChiefGroup 数据合并到 IPORecord 的 verified_fields 中"""
        code = record.get("stock_code", "")
        ncode = str(int(code))  # "02523" -> "2523"

        if ncode not in chief_data:
            return 0

        cd = chief_data[ncode]
        if cd.get("error"):
            return 0

        vf = record.get("verified_fields", {})
        count = 0

        # 映射字段
        for chief_field, vf_field in [
            ("subscription_multiple", "subscription_multiple"),
            ("margin_multiple", "margin_multiple"),
            ("actual_oversubscription", "actual_oversubscription"),
            ("pe_ratio", "pe_ratio"),
            ("allotment_rate_pct", "allotment_rate_pct"),
            ("applicant_count", "applicant_count"),
            ("entry_fee_hkd", "entry_fee_hkd"),
            ("lot_size", "lot_size"),
            ("market_cap_range", "market_cap"),
            ("sponsors", "sponsors"),
            ("offer_price_range", "offer_price_range"),
        ]:
            val = cd.get(chief_field)
            if val is not None and val != "-":
                vf[vf_field] = val
                count += 1

        record["verified_fields"] = vf
        return count
