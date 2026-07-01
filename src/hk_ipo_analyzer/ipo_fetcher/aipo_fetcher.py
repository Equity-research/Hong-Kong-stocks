"""
AiPO (aipo.myiqdii.com) 数据抓取器

参考: Marvae/hk-ipo-research-assistant 的 AiPO API 接入方案

提供：
- 孖展明细（13+ 券商实时数据）
- 机构评级（辉立、凯基等）
- 基石投资者详情（名单、占比、锁定期）
- 保荐人历史战绩（首日涨跌幅、暗盘表现）
- IPO 基本信息（市值、PE、发行价区间）
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

AIPO_BASE = "https://aipo.myiqdii.com"
AIPO_NEWSTOCK = f"{AIPO_BASE}/aipo/newstock"

# API endpoints
API = {
    "rating_list": "/Home/GetNewStockRatingList",
    "rating_detail": "/Home/GetAgencyRatingInfo",
    "ipo_brief": "/Home/NewStockBrief",
    "cornerstone": "/Home/GetInvestorInfoByCode",
    "placing": "/Home/GetPlacingResult",
    "margin_list": "/Home/GetMarginList",
    "margin_detail": "/Home/GetMarginInfo",
    "sponsor_history": "/Home/SpoHisProjects",
    "grey_list": "/Home/GetGreyList",
    "grey_trades": "/Home/GetGreyTradeInfo",
    "grey_prices": "/Home/GetGreyPriceDistribution",
    "summary": "/Home/GetIpoSummary",
    "performance": "/Home/GetIpoPerformanceByYear",
}


@dataclass
class BrokerMargin:
    """单家券商孖展数据"""
    broker_name: str
    margin_amount: float = 0.0  # 孖展金额（港元）
    interest_rate: float = 0.0  # 孖展利率


@dataclass
class MarginDetail:
    """IPO 孖展明细"""
    stock_code: str
    stock_name: str
    total_margin: float = 0.0       # 孖展总额
    oversubscription: float = 0.0    # 超购倍数
    forecast_oversub: float = 0.0    # 预测超购倍数
    brokers: list[BrokerMargin] = field(default_factory=list)


@dataclass
class AgencyRating:
    """机构评级"""
    agency: str
    rating: str
    score: float = 0.0


@dataclass
class CornerstoneInvestor:
    """基石投资者"""
    name: str
    amount: float = 0.0          # 投资金额
    share_pct: float = 0.0       # 占发行比例 %
    lockup_months: int = 6       # 锁定期（月）
    release_date: str = ""       # 解禁日


@dataclass
class SponsorRecord:
    """保荐人历史记录"""
    stock_code: str
    stock_name: str
    listed_date: str
    first_day_change: float = 0.0   # 首日涨跌幅 %
    grey_change: float = 0.0        # 暗盘涨跌幅 %
    current_price: float = 0.0


class AiPOFetcher:
    """AiPO 数据抓取器"""

    def __init__(self, cache_dir: str = "data/.aipo_cache"):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{AIPO_BASE}/aipo/newstock",
        })
        self._token: Optional[str] = None
        self._token_time: float = 0
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_token(self) -> str:
        """获取/刷新 RequestVerificationToken（30分钟过期）"""
        if self._token and (time.time() - self._token_time) < 1800:
            return self._token

        resp = self.session.get(AIPO_NEWSTOCK, timeout=15)
        m = re.search(
            r'name="__RequestVerificationToken"[^>]+value="([^"]+)"',
            resp.text
        )
        if m:
            self._token = m.group(1)
            self._token_time = time.time()
            self.session.headers["RequestVerificationToken"] = self._token
            return self._token
        raise RuntimeError("Failed to get AiPO verification token")

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """带 token 的 API GET 请求"""
        self._get_token()
        url = f"{AIPO_BASE}{endpoint}"
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") != 1:
            LOGGER.warning("AiPO API error: %s", data.get("msg", "unknown"))
            return {}
        return data

    # ─── 孖展数据 ───────────────────────────────────────

    def fetch_margin_list(self, page_size: int = 50) -> list[dict]:
        """获取当前招股 IPO 的孖展汇总数据"""
        data = self._get(API["margin_list"], {
            "pageIndex": 1, "pageSize": page_size, "sector": ""
        })
        return data.get("data", {}).get("dataList", [])

    def fetch_margin_detail(self, stock_code: str) -> MarginDetail:
        """获取单只 IPO 各券商孖展明细（13+ 券商）"""
        code_e = f"E{int(stock_code):05d}"
        data = self._get(API["margin_detail"], {"stockCode": code_e})
        detail = data.get("data", {})

        margin = MarginDetail(stock_code=stock_code, stock_name="")
        margin.total_margin = float(data.get("totalMarginMoney", 0))
        margin.oversubscription = float(data.get("overSub", 0))
        margin.forecast_oversub = float(data.get("expOverSubscription", 0))

        # 解析各券商明细
        brokers = data.get("marginDetailList", []) or detail.get("marginDetailList", [])
        for b in (brokers or []):
            margin.brokers.append(BrokerMargin(
                broker_name=str(b.get("orgName", "")),
                margin_amount=float(b.get("marginMoney", 0)),
            ))

        return margin

    # ─── 评级数据 ───────────────────────────────────────

    def fetch_rating_list(self, page_size: int = 50) -> list[dict]:
        """获取新股评级列表"""
        data = self._get(API["rating_list"], {
            "pageIndex": 1, "pageSize": page_size, "sector": ""
        })
        return data.get("data", {}).get("dataList", [])

    def fetch_rating_detail(self, stock_code: str) -> list[AgencyRating]:
        """获取单只 IPO 各机构评级"""
        code_e = f"E{int(stock_code):05d}"
        data = self._get(API["rating_detail"], {"code": code_e})
        msg = data.get("msg", "{}")
        try:
            inner = json.loads(msg) if isinstance(msg, str) else msg
        except json.JSONDecodeError:
            return []

        ratings = []
        for r in inner.get("data", []):
            ratings.append(AgencyRating(
                agency=str(r.get("ratingagency", "")),
                rating=str(r.get("rating", "")),
                score=float(r.get("score", 0)),
            ))
        return ratings

    # ─── IPO 基本信息 ────────────────────────────────────

    def fetch_ipo_brief(self, stock_code: str) -> dict:
        """获取 IPO 基本信息（保荐人、市值、PE、发行价）"""
        code_e = f"E{int(stock_code):05d}"
        data = self._get(API["ipo_brief"], {"code": code_e})
        msg = data.get("msg", "{}")
        try:
            inner = json.loads(msg) if isinstance(msg, str) else msg
        except json.JSONDecodeError:
            return {}

        brief = inner.get("data", {})
        issuance = brief.get("issuanceinfo", {})

        return {
            "stock_code": stock_code,
            "sponsors": issuance.get("sponsors", ""),
            "bookrunners": issuance.get("bookrunners", ""),
            "industry": issuance.get("industry", ""),
            "market_cap": issuance.get("marketcap", ""),
            "pe_ratio": issuance.get("pe"),
            "ipo_price_floor": issuance.get("ipoprice", {}).get("floor", ""),
            "ipo_price_ceiling": issuance.get("ipoprice", {}).get("ceiling", ""),
            "lot_size": issuance.get("shares"),
            "entry_fee": issuance.get("minimumcapital"),
            "ipo_start": (issuance.get("ipodate") or {}).get("start", ""),
            "ipo_end": (issuance.get("ipodate") or {}).get("end", ""),
            "listed_date": issuance.get("listeddate", ""),
        }

    # ─── 基石投资者 ──────────────────────────────────────

    def fetch_cornerstone(self, stock_code: str) -> list[CornerstoneInvestor]:
        """获取基石投资者详情"""
        code_e = f"E{int(stock_code):05d}"
        data = self._get(API["cornerstone"], {"code": code_e})
        investors = []
        for item in data.get("data", []):
            inv = CornerstoneInvestor(
                name=str(item.get("investorName", "")),
                amount=float(item.get("marketValue", 0)),
                share_pct=float(item.get("shareholding_percentage", 0)),
                release_date=str(item.get("releaseDate", "")),
            )
            investors.append(inv)
        return investors

    # ─── 保荐人历史战绩 ──────────────────────────────────

    def fetch_sponsor_history(self, sponsor_name: str, limit: int = 30) -> list[SponsorRecord]:
        """获取保荐人历史 IPO 表现（首日涨跌幅、暗盘涨跌幅）"""
        data = self._get(API["sponsor_history"], {
            "market": "mkt_hk",
            "sponsor": sponsor_name,
            "type": 0,  # 0=保荐人
            "pageIndex": 1,
            "pageSize": limit,
        })
        records = []
        for item in data.get("data", {}).get("dataList", []):
            records.append(SponsorRecord(
                stock_code=str(item.get("symbol", "")).replace("E", ""),
                stock_name=str(item.get("shortName", "")),
                listed_date=str(item.get("listedDate", "")),
                first_day_change=float(item.get("firstDayChg", 0)),
                grey_change=float(item.get("grayPriceChg", 0)),
                current_price=float(item.get("nowprice", 0)),
            ))
        return records

    # ─── 批量抓取 ────────────────────────────────────────

    def fetch_all_for_ipos(
        self, stock_codes: list[str], max_workers: int = 6
    ) -> dict[str, dict]:
        """并发抓取多只 IPO 的全部数据"""
        results = {}

        def fetch_one(code: str) -> tuple[str, dict]:
            result = {"stock_code": code}
            try:
                # IPO 基本信息
                brief = self.fetch_ipo_brief(code)
                result["brief"] = brief

                # 基石投资者
                cornerstone = self.fetch_cornerstone(code)
                if cornerstone:
                    total_pct = sum(c.share_pct for c in cornerstone)
                    result["cornerstone"] = {
                        "investors": [
                            {"name": c.name, "amount": c.amount,
                             "share_pct": c.share_pct, "release_date": c.release_date}
                            for c in cornerstone
                        ],
                        "total_pct": total_pct,
                        "count": len(cornerstone),
                    }

                # 评级
                ratings = self.fetch_rating_detail(code)
                if ratings:
                    avg = sum(r.score for r in ratings) / len(ratings)
                    result["ratings"] = {
                        "agencies": [
                            {"agency": r.agency, "rating": r.rating, "score": r.score}
                            for r in ratings
                        ],
                        "avg_score": round(avg, 1),
                        "count": len(ratings),
                    }

                return code, result
            except Exception as e:
                LOGGER.warning("AiPO fetch failed for %s: %s", code, e)
                result["error"] = str(e)
                return code, result

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, c): c for c in stock_codes}
            for future in as_completed(futures):
                code, data = future.result()
                results[code] = data

        return results

    def enrich_record(self, record: dict, aipo_data: dict) -> int:
        """将 AiPO 数据合并到 IPORecord 的 verified_fields"""
        code = record.get("stock_code", "")
        ncode = str(int(code))
        ad = aipo_data.get(ncode, {})
        if not ad or ad.get("error"):
            return 0

        vf = record.get("verified_fields", {})
        count = 0

        # Brief data
        brief = ad.get("brief", {})
        for src, dst in [
            ("sponsors", "sponsors"),
            ("pe_ratio", "pe_ratio"),
            ("market_cap", "market_cap"),
            ("entry_fee", "entry_fee_hkd"),
            ("lot_size", "lot_size"),
            ("industry", "industry"),
        ]:
            val = brief.get(src)
            if val is not None and val != "":
                vf[dst] = val
                count += 1

        # Cornerstone
        cs = ad.get("cornerstone", {})
        if cs.get("count", 0) > 0:
            vf["cornerstone_ratio"] = cs["total_pct"]
            vf["cornerstone_count"] = cs["count"]
            vf["cornerstone_investors"] = cs["investors"]
            count += 3

        # Ratings
        rt = ad.get("ratings", {})
        if rt.get("count", 0) > 0:
            vf["agency_rating_avg"] = rt["avg_score"]
            vf["agency_rating_count"] = rt["count"]
            count += 2

        # Margin (from brief if available)
        # The full margin detail requires separate call per stock

        record["verified_fields"] = vf
        return count
