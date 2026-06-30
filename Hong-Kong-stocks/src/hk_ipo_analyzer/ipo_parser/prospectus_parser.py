from __future__ import annotations

import re
from pathlib import Path

from hk_ipo_analyzer.ipo_parser.pdf_text import extract_pdf_text
from hk_ipo_analyzer.models import IPORecord


PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "offer_price_low": [re.compile(r"(?:HK\$|港幣)\s*([\d.]+)\s*(?:to|至|–|-)\s*(?:HK\$|港幣)", re.I)],
    "offer_price_high": [re.compile(r"(?:HK\$|港幣)\s*[\d.]+\s*(?:to|至|–|-)\s*(?:HK\$|港幣)\s*([\d.]+)", re.I)],
    "board_lot": [
        re.compile(r"(?:board lot of|每手)\s*([\d,]+)\s*(?:shares|股)", re.I),
        re.compile(r"([\d,]+)\s*(?:shares|股)\s*(?:per board lot|一手)", re.I),
    ],
    "public_offer_ratio": [re.compile(r"(?:Hong Kong Public Offering|香港公開發售)[^%]{0,120}([\d.]+)%", re.I)],
}


def _number(value: str) -> float | int:
    cleaned = value.replace(",", "")
    parsed = float(cleaned)
    return int(parsed) if parsed.is_integer() else parsed


class ProspectusParser:
    def parse(self, path: Path, record: IPORecord, source_url: str) -> str:
        text = extract_pdf_text(path)
        source_name = "HKEX 招股书"
        for field_name, patterns in PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    record.set_field(field_name, _number(match.group(1)), source_url, source_name)
                    break
        low = record.value("offer_price_low")
        high = record.value("offer_price_high")
        if low is not None and high is not None:
            record.set_field("offer_price_range", f"HK${low:g}-HK${high:g}", source_url, source_name)
        return text

