from __future__ import annotations

import re

from hk_ipo_analyzer.models import IPORecord


class CornerstoneParser:
    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        section = self._section(text)
        if not section:
            return
        names = re.findall(
            r"(?:entered into|與)\s+(?:a\s+)?cornerstone investment agreement[^\n]{0,30}(?:with|訂立)[：:]?\s*([^\n]{2,100})",
            section,
            re.I,
        )
        if names:
            cleaned = [" ".join(name.split()) for name in names[:20]]
            record.set_field("cornerstone_investors", cleaned, source_url, "HKEX 招股书")
            record.set_field("cornerstone_count", len(cleaned), source_url, "HKEX 招股书")
        ratio = re.search(r"cornerstone investors?[^%]{0,600}?([\d.]+)%", section, re.I)
        if ratio:
            record.set_field("cornerstone_ratio", float(ratio.group(1)), source_url, "HKEX 招股书")
        lockup = re.search(r"(?:lock-up period of|禁售期)[^\d]{0,30}(\d+)\s*(?:months|個月|个月)", section, re.I)
        if lockup:
            record.set_field("cornerstone_lockup_months", int(lockup.group(1)), source_url, "HKEX 招股书")

    @staticmethod
    def _section(text: str) -> str:
        match = re.search(r"CORNERSTONE INVESTORS?|基石投資者", text, re.I)
        return text[match.start() : match.start() + 40000] if match else ""

