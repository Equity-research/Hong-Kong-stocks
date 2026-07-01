from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

FINANCIAL_PATTERNS = {
    "gross_margin_latest": [
        re.compile(r"gross profit margin[^%\d]{0,100}?(-?[\d.]+)\s*%", re.I),
        re.compile(r"毛利率[^%\d]{0,100}?(-?[\d.]+)\s*%"),
    ],
    "customer_concentration_top5": [
        re.compile(r"five largest customers[^%\d]{0,200}?([\d.]+)\s*%", re.I),
        re.compile(r"五大客戶[^%\d]{0,200}?([\d.]+)\s*%"),
    ],
    "supplier_concentration_top5": [
        re.compile(r"five largest suppliers[^%\d]{0,200}?([\d.]+)\s*%", re.I),
        re.compile(r"五大供應商[^%\d]{0,200}?([\d.]+)\s*%"),
    ],
    "debt_to_assets_pct": [
        re.compile(r"(?:debt[- /]to[- /]asset|debt ratio)[^%\d]{0,80}?([\d.]+)\s*%", re.I),
        re.compile(r"(?:資產負債率|资产负债率|負債比率|负债比率)[^%\d]{0,80}?([\d.]+)\s*%"),
    ],
}

REVENUE_LABELS = ("收入", "收益", "營收", "营业收入", "Revenue")
PROFIT_LABELS = ("淨利潤", "净利润", "年內利潤", "年度利潤", "Net Profit", "Profit for the year")
CASHFLOW_LABELS = ("經營活動現金", "经营活动现金", "Operating Cash", "Net cash generated from operating")
NUMBER_RE = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")
UNIT_SCALE = {"": 1.0, "千": 1e3, "万": 1e4, "萬": 1e4, "百万": 1e6, "百萬": 1e6, "million": 1e6, "亿": 1e8, "億": 1e8, "billion": 1e9}


def _safe_float(text: str | None) -> float | None:
    if not text:
        return None
    raw = str(text).strip()
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^\d.\-]", "", raw)
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        value = float(cleaned)
        return -abs(value) if negative else value
    except ValueError:
        return None


def _parse_hkd_amount(text: str) -> float | None:
    match = re.search(r"(\(?-?[\d.,]+\)?)\s*(billion|million|百萬|百万|億|亿|萬|万|千)?", str(text), re.I)
    if not match:
        return None
    value = _safe_float(match.group(1))
    if value is None:
        return None
    return value * UNIT_SCALE.get((match.group(2) or "").lower(), 1)


class FinancialParser:
    """从招股书文本和表格提取财务字段，并保留期间、币种和负号。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        period = self._latest_period(text)
        currency = self._currency(text)
        if period:
            record.set_field("financial_period", period, source_url, "HKEX 招股书", source_tier="A")
        if currency:
            record.set_field("financial_currency", currency, source_url, "HKEX 招股书", source_tier="A")
        for name, patterns in FINANCIAL_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    record.set_field(name, float(match.group(1)), source_url, "HKEX 招股书", source_tier="A", period=period, currency=currency)
                    break
        self._parse_text_series(text, record, source_url, period, currency)
        revenue = record.value("revenue")
        profit = record.value("net_profit")
        if revenue not in (None, 0) and profit is not None:
            record.set_field("net_margin_pct", round(float(profit) / float(revenue) * 100, 2), source_url, "HKEX 招股书（同期间推导）", source_tier="A", period=period, currency=currency)

    def parse_from_pdf(self, pdf_path: Path, record: IPORecord, source_url: str) -> None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                tables = [table for page in pdf.pages for table in page.extract_tables() if table]
            if tables:
                self._extract_tables(tables, record, source_url)
        except Exception:
            LOGGER.warning("pdfplumber 表格提取失败：%s", pdf_path, exc_info=True)

    def _extract_tables(self, tables: list, record: IPORecord, source_url: str) -> None:
        source = "HKEX 招股书（表格提取）"
        for table in tables:
            table_text = "\n".join(" | ".join(str(cell or "") for cell in row) for row in table if row)
            period = self._latest_period(table_text)
            currency = self._currency(table_text)
            for row in table:
                if not row or len(row) < 2:
                    continue
                label = str(row[0] or "").strip()
                values = [_parse_hkd_amount(str(value)) for value in row[1:] if str(value or "").strip()]
                values = [value for value in values if value is not None]
                if not values:
                    continue
                latest = values[-1]
                if any(token.lower() in label.lower() for token in REVENUE_LABELS):
                    record.set_field("revenue", latest, source_url, source, source_tier="A", period=period, currency=currency)
                    if len(values) >= 2 and values[-2] != 0:
                        growth = (latest / values[-2] - 1) * 100
                        record.set_field("revenue_growth_pct", round(growth, 2), source_url, source, source_tier="A", period=period, currency=currency)
                elif any(token.lower() in label.lower() for token in PROFIT_LABELS):
                    record.set_field("net_profit", latest, source_url, source, source_tier="A", period=period, currency=currency)
                elif any(token.lower() in label.lower() for token in CASHFLOW_LABELS):
                    record.set_field("operating_cash_flow", latest, source_url, source, source_tier="A", period=period, currency=currency)

    def _parse_text_series(self, text: str, record: IPORecord, source_url: str, period: str | None, currency: str | None) -> None:
        source = "HKEX 招股书"
        for field_name, labels in (("revenue", REVENUE_LABELS), ("net_profit", PROFIT_LABELS), ("operating_cash_flow", CASHFLOW_LABELS)):
            if record.value(field_name) is not None:
                continue
            for label in labels:
                match = re.search(rf"{re.escape(label)}[^。\n]{{0,220}}", text, re.I)
                if not match:
                    continue
                values = self._amounts(match.group(0))
                if values:
                    record.set_field(field_name, values[-1], source_url, source, source_tier="A", period=period, currency=currency)
                    if field_name == "revenue" and len(values) >= 2 and values[-2] != 0:
                        record.set_field("revenue_growth_pct", round((values[-1] / values[-2] - 1) * 100, 2), source_url, source, source_tier="A", period=period, currency=currency)
                    break

    @staticmethod
    def _amounts(segment: str) -> list[float]:
        values = []
        for match in re.finditer(r"(\(?-?[\d,]+(?:\.\d+)?\)?)\s*(billion|million|百萬|百万|億|亿|萬|万)?", segment, re.I):
            raw, unit = match.groups()
            value = _safe_float(raw)
            if value is None:
                continue
            if not unit and "," not in raw:
                continue
            values.append(value * UNIT_SCALE.get((unit or "").lower(), 1))
        return values[-4:]

    @staticmethod
    def _latest_period(text: str) -> str | None:
        years = [int(year) for year in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text[:200000])]
        return f"FY{max(years)}" if years else None

    @staticmethod
    def _currency(text: str) -> str | None:
        head = text[:120000]
        patterns = (("RMB", r"(?:RMB|人民幣|人民币)"), ("SGD", r"(?:S\$|Singapore dollars?|新加坡元)"), ("HKD", r"(?:HK\$|Hong Kong dollars?|港元)"))
        for code, pattern in patterns:
            if re.search(pattern, head, re.I):
                return code
        return None
