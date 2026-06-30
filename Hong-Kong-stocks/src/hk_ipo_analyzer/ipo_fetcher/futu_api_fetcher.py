"""
富途 OpenAPI 数据抓取器

前置条件：
1. 安装富途牛牛 (FutuNiuniu) 桌面端：https://www.futunn.com/
2. 登录富途账号后，FutuOpenD 网关自动在 127.0.0.1:11111 启动
3. pip install futu-api (已完成)

可用 API 及字段：
- get_ipo_list: code/name/list_time/ipo_price_min/ipo_price_max/lot_size/entrance_price/is_subscribe_status
- get_stock_basicinfo: 股票基本资料 (行业/市值/市盈率等)
- get_market_snapshot: 市场快照 (成交量/换手率/振幅等)
- get_financials_statements: 财务报表 (仅已上市公司)
- get_capital_distribution: 资金分布
"""

from __future__ import annotations

import logging
from typing import Optional

from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

try:
    from futu import OpenQuoteContext, RET_OK, Market
    HAS_FUTU = True
except ImportError:
    HAS_FUTU = False


class FutuAPIFetcher:
    """通过 Futu OpenAPI 获取 IPO 及股票数据。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111):
        self.host = host
        self.port = port
        self._ctx: Optional[OpenQuoteContext] = None

    def _connect(self) -> bool:
        """连接 FutuOpenD，先检查端口是否可达"""
        if not HAS_FUTU:
            return False
        if self._ctx is not None:
            return True
        # 快速端口检测，避免 SDK 内置的长时间重试
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            if result != 0:
                LOGGER.debug("FutuOpenD 端口 %s 不可达 (跳过)", self.port)
                return False
        except Exception:
            return False
        try:
            self._ctx = OpenQuoteContext(host=self.host, port=self.port)
            LOGGER.info("FutuOpenD 连接成功 (%s:%s)", self.host, self.port)
            return True
        except Exception as e:
            LOGGER.warning("FutuOpenD 连接失败: %s", e)
            return False
        if self._ctx is not None:
            return True
        try:
            self._ctx = OpenQuoteContext(host=self.host, port=self.port)
            return True
        except Exception as e:
            LOGGER.warning("FutuOpenD 连接失败 (%s:%s): %s", self.host, self.port, e)
            return False

    def _disconnect(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def enrich_all(self, records: list[IPORecord]) -> list[IPORecord]:
        if not self._connect():
            return records
        try:
            self._enrich_ipo_list(records)
            for record in records:
                self._enrich_stock_info(record)
        finally:
            self._disconnect()
        return records

    def _enrich_ipo_list(self, records: list[IPORecord]) -> None:
        """用 get_ipo_list 确认 HK 市场 IPO 列表数据"""
        ret, data = self._ctx.get_ipo_list(market=Market.HK)
        if ret != RET_OK:
            LOGGER.warning("get_ipo_list 失败: %s", data)
            return

        LOGGER.info("Futu IPO 列表获取成功: %s 条", len(data))
        for _, row in data.iterrows():
            code = str(row.get("code", "")).replace("HK.", "").strip()
            record = next((r for r in records if r.stock_code == code), None)
            if record is None:
                continue

            url = f"futu-api://get_ipo_list?code={code}"
            self._set_if_missing(record, "offer_price_low", row.get("ipo_price_min"), url)
            self._set_if_missing(record, "offer_price_high", row.get("ipo_price_max"), url)
            self._set_if_missing(record, "board_lot", row.get("lot_size"), url)
            self._set_if_missing(record, "entry_fee_hkd", row.get("entrance_price"), url)
            self._set_if_missing(record, "listing_date", row.get("list_time"), url)

            # is_subscribe_status: 是否可认购 (这个字段很关键!)
            subscribe_status = row.get("is_subscribe_status")
            if subscribe_status is not None:
                record.set_field("is_subscribable", bool(subscribe_status), url, "Futu OpenAPI")

    def _enrich_stock_info(self, record: IPORecord) -> None:
        """用 get_stock_basicinfo 补充行业/市值/市盈率"""
        try:
            code = f"HK.{record.stock_code}"
            ret, data = self._ctx.get_stock_basicinfo(market=Market.HK, code_list=[code])
            if ret != RET_OK:
                return
            if data.empty:
                return

            row = data.iloc[0]
            url = f"futu-api://get_stock_basicinfo?code={record.stock_code}"

            sector = row.get("industry") or row.get("classification")
            if sector:
                record.set_field("sector", str(sector), url, "Futu OpenAPI")

            market_cap = row.get("market_val")
            if market_cap and market_cap > 0:
                record.set_field("market_cap_hkd", float(market_cap), url, "Futu OpenAPI")

            pe = row.get("pe_ratio") or row.get("pe_ttm")
            if pe and pe > 0:
                record.set_field("pe_ratio", float(pe), url, "Futu OpenAPI")

        except Exception:
            LOGGER.debug("get_stock_basicinfo 失败: %s", record.stock_code, exc_info=True)

    @staticmethod
    def _set_if_missing(record, field: str, value, url: str) -> None:
        if value is None:
            return
        if record.value(field) is not None:
            return  # 不覆盖已有数据
        try:
            if isinstance(value, (int, float)):
                record.set_field(field, float(value), url, "Futu OpenAPI")
            else:
                record.set_field(field, str(value), url, "Futu OpenAPI")
        except (ValueError, TypeError):
            pass
