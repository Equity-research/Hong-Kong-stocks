from __future__ import annotations

import logging
import re

import pdfplumber

from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

FINANCIAL_PATTERNS = {
    "gross_margin_latest": [
        re.compile(r"gross profit margin[^%\d]{0,100}?([\d.]+)\s*%", re.I),
        re.compile(r"毛利率[^%\d]{0,100}?([\d.]+)\s*%"),
    ],
    "customer_concentration_top5": [
        re.compile(r"five largest customers[^%\d]{0,200}?([\d.]+)\s*%", re.I),
        re.compile(r"五大客戶[^%\d]{0,200}?([\d.]+)\s*%"),
    ],
    "supplier_concentration_top5": [
        re.compile(r"five largest suppliers[^%\d]{0,200}?([\d.]+)\s*%", re.I),
        re.compile(r"五大供應商[^%\d]{0,200}?([\d.]+)\s*%"),
    ],
}

REVENUE_LABELS = ["收入", "收益", "營收", "营业", "Revenue", "營業收入", "營業額"]
PROFIT_LABELS = ["淨利", "净利", "純利", "纯利", "淨利潤", "净利润", "Net Profit", "純利潤", "纯利润"]
GROSS_LABELS = ["毛利", "Gross Profit", "銷售成本", "销售成本", "營業成本", "营业成本"]
CASHFLOW_LABELS = ["經營現金", "经营现金", "Operating Cash", "經營活動現金", "经营活动现金"]
DEBT_LABELS = ["資產負債", "资产负债", "總負債", "总负债", "總資產", "总资产", "負債率", "负债率"]


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
    match = re.search(r"([\d.,]+)\s*([億亿万萬千]?)", str(text))
    if not match:
        return None
    num = float(match.group(1).replace(",", ""))
    unit_mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
    return num * unit_mult.get(match.group(2) or "", 1)


class FinancialParser:
    """保守正则 + pdfplumber 表格双重提取；复杂表格不猜测，留待人工校验。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        for name, patterns in FINANCIAL_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    record.set_field(name, float(match.group(1)), source_url, "HKEX 招股书")
                    break

    def parse_from_pdf(self, pdf_path, record: IPORecord, source_url: str) -> None:
        """使用 pdfplumber 从 PDF 表格中提取财务数据。"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                all_tables = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            all_tables.append(table)
                if not all_tables:
                    return
                merged_text = self._tables_to_text(all_tables)
                self._extract_financial_rows(all_tables, record, source_url)
                self._text_fallback(merged_text, record, source_url)
        except Exception:
            LOGGER.warning("pdfplumber 表格提取失败：%s", pdf_path, exc_info=True)

    @staticmethod
    def _tables_to_text(tables: list) -> str:
        lines = []
        for table in tables:
            for row in table:
                if row:
                    cells = [str(c or "").strip() for c in row if c]
                    lines.append(" | ".join(cells))
        return "\n".join(lines)

    def _extract_financial_rows(self, tables: list, record: IPORecord, source_url: str) -> None:
        source = "HKEX 招股书（表格提取）"
        for table in tables:
            for row in table:
                if not row or len(row) < 2:
                    continue
                header = str(row[0] or "").strip()
                values = [v for v in row[1:] if v and str(v).strip()]

                if any(kw in header for kw in REVENUE_LABELS) and not record.value("revenue"):
                    for v in values:
                        amt = _parse_hkd_amount(str(v))
                        if amt and amt > 0:
                            record.set_field("revenue", amt, source_url, source)
                            break

                if any(kw in header for kw in PROFIT_LABELS) and not record.value("net_profit"):
                    for v in values:
                        amt = _parse_hkd_amount(str(v))
                        if amt is not None:
                            record.set_field("net_profit", amt, source_url, source)
                            break

                if any(kw in header for kw in CASHFLOW_LABELS) and not record.value("operating_cash_flow"):
                    for v in values:
                        amt = _parse_hkd_amount(str(v))
                        if amt is not None:
                            record.set_field("operating_cash_flow", amt, source_url, source)
                            break

                if any(kw in header for kw in GROSS_LABELS) and not record.value("gross_margin_latest"):
                    for v in values:
                        pct = _safe_float(str(v))
                        if pct is not None and 0 < pct < 100:
                            record.set_field("gross_margin_latest", pct, source_url, source)
                            break

                if any(kw in header for kw in DEBT_LABELS) and not record.value("debt_to_assets_pct"):
                    for v in values:
                        pct = _safe_float(str(v))
                        if pct is not None and 0 < pct <= 200:
                            record.set_field("debt_to_assets_pct", pct, source_url, source)
                            break

    def _text_fallback(self, text: str, record: IPORecord, source_url: str) -> None:
        source = "HKEX 招股书"
        if not record.value("revenue"):
            rev = re.search(r"(?:收入|收益|營收|Revenue)[^\d\n]{0,60}[\$HK]*\s*([\d.,]+)\s*([億亿万萬千]?)", text, re.I)
            if rev:
                num = float(rev.group(1).replace(",", ""))
                unit = rev.group(2)
                mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
                record.set_field("revenue", num * mult.get(unit, 1), source_url, source)
        if not record.value("debt_to_assets_pct"):
            debt = re.search(r"(?:資產負債率|资产负债率|負債比率|负债比率|Debt[ /]Asset)[^\d\n]{0,60}([\d.]+)\s*%", text, re.I)
            if debt:
                record.set_field("debt_to_assets_pct", float(debt.group(1)), source_url, source)
        if not record.value("revenue_growth_pct"):
            growth = re.search(r"(?:收入增長|收入增长|營收增長|營收增长|Revenue Growth|複合年增長|复合年增长|CAGR)[^\d\n]{0,80}([\d.]+)\s*%", text, re.I)
            if growth:
                record.set_field("revenue_growth_pct", float(growth.group(1)), source_url, source)
