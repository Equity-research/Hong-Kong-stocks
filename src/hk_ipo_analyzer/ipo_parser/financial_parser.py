from __future__ import annotations

import re

from hk_ipo_analyzer.models import IPORecord


FINANCIAL_PATTERNS = {
    "gross_margin_latest": [
        re.compile(r"gross profit margin[^%]{0,100}?([\d.]+)%", re.I),
        re.compile(r"毛利率[^%]{0,100}?([\d.]+)%"),
    ],
    "customer_concentration_top5": [
        re.compile(r"five largest customers[^%]{0,150}?([\d.]+)%", re.I),
        re.compile(r"五大客戶[^%]{0,150}?([\d.]+)%"),
    ],
    "supplier_concentration_top5": [
        re.compile(r"five largest suppliers[^%]{0,150}?([\d.]+)%", re.I),
        re.compile(r"五大供應商[^%]{0,150}?([\d.]+)%"),
    ],
}


class FinancialParser:
    """保守正则提取；复杂表格不猜测，留待人工校验或后续表格解析。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        for name, patterns in FINANCIAL_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    record.set_field(name, float(match.group(1)), source_url, "HKEX 招股书")
                    break

