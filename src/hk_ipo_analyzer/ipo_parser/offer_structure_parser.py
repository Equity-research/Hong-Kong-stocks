from __future__ import annotations

import re

from hk_ipo_analyzer.models import IPORecord


class OfferStructureParser:
    """从招股书全文提取发行结构，只记录有明确文字证据的字段。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        if re.search(r"Over-?allotment Option|超額配股權|超额配股权", text, re.I):
            record.set_field("greenshoe", True, source_url, "HKEX 招股书")
        elif re.search(r"Offer Size Adjustment Option|發售量調整權|发售量调整权", text, re.I):
            record.set_field("greenshoe", False, source_url, "HKEX 招股书")

        ratio = re.search(
            r"(?:Hong Kong Public Offer(?:ing)?|香港公開發售)[^%]{0,220}?([\d.]+)%",
            text,
            re.I,
        )
        if ratio:
            record.set_field("public_offer_ratio", float(ratio.group(1)), source_url, "HKEX 招股书")

        sponsor = re.search(
            r"(?:Joint Sponsors?|Sole Sponsor|聯席保薦人|独家保荐人|獨家保薦人)[：:]?\s*([^\n]{3,180})",
            text,
            re.I,
        )
        if sponsor:
            value = " ".join(sponsor.group(1).split()).strip("：: ")
            if value and not re.fullmatch(r"(?:and|及|、)+", value, re.I):
                record.set_field("sponsors", value, source_url, "HKEX 招股书")
