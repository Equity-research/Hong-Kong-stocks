from __future__ import annotations

import re

from hk_ipo_analyzer.models import IPORecord


class CornerstoneParser:
    """解析基石名称、数量、金额、全球发售占比和锁定期。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        section = self._section(text)
        if not section:
            return
        names = self._names(section)
        if names:
            record.set_field("cornerstone_investors", names, source_url, "HKEX 招股书", source_tier="A")
            record.set_field("cornerstone_count", len(names), source_url, "HKEX 招股书", source_tier="A")
        count = re.search(r"(?:with|引入|已有|已與|已与)\s*(\d{1,2})\s*(?:cornerstone investors?|名?基石投資者|名?基石投资者)", section, re.I)
        if count:
            record.set_field("cornerstone_count", int(count.group(1)), source_url, "HKEX 招股书", source_tier="A", overwrite=True)
        amount = self._amount(section)
        if amount is not None:
            record.set_field("cornerstone_amount_hkd", amount, source_url, "HKEX 招股书", source_tier="A", currency="HKD")
        ratio = self._global_offer_ratio(section)
        if ratio is not None:
            record.set_field("cornerstone_ratio", ratio, source_url, "HKEX 招股书", source_tier="A")
        lockup = re.search(r"(?:lock-up period of|禁售期|鎖定期|锁定期)[^\d]{0,40}(\d+)\s*(?:months|個月|个月)", section, re.I)
        if lockup:
            record.set_field("cornerstone_lockup_months", int(lockup.group(1)), source_url, "HKEX 招股书", source_tier="A")
        quality = self._quality_score(section, names, ratio)
        record.set_field("cornerstone_quality_score", quality, source_url, "基石质量启发式", source_tier="C")

    @staticmethod
    def _section(text: str) -> str:
        match = re.search(r"CORNERSTONE INVESTORS?|基石投資者|基石投资者", text, re.I)
        return text[match.start():match.start() + 50000] if match else ""

    @staticmethod
    def _names(section: str) -> list[str]:
        patterns = [
            r"([A-Z][A-Za-z&.,'()\- ]{6,80}(?:Limited|Ltd\.?|Inc\.?|Corporation|Group|Holdings|Capital|Investment|Asset|Fund|Management|International|Partners?|Securities|Bank|Trust|Advisors?))",
            r"([\u4e00-\u9fff（）()]{3,24}(?:集團|集团|控股|有限|投資|投资|基金|資產|资产|資本|资本|證券|证券|銀行|银行|保險|保险|國際|国际|公司))",
        ]
        names: list[str] = []
        for pattern in patterns:
            for name in re.findall(pattern, section[:25000], re.I):
                clean = " ".join(name.split()).rstrip(".,;，。； （()")
                if 3 < len(clean) < 120 and "基石" not in clean and clean not in names:
                    names.append(clean)
        return names[:20]

    @staticmethod
    def _amount(section: str) -> float | None:
        patterns = [
            r"(?:總認購金額|总认购金额|認購總額|认购总额|投資總額|投资总额|合共|合計|合计)[^\n]{0,120}?(?:HK\$|港幣|港币|港元)\s*(\(?-?[\d,.]+\)?)\s*(billion|million|十億|十亿|億|亿|百萬|百万|萬|万)?",
            r"(?:基石投資者|基石投资者|cornerstone investors?)[^。\n]{0,120}?(?:認購|认购|subscribe)[^。\n]{0,80}?(?:HK\$|港幣|港币|港元)\s*(\(?-?[\d,.]+\)?)\s*(billion|million|十億|十亿|億|亿|百萬|百万|萬|万)?",
            r"(?:HK\$|港幣|港币|港元)\s*(\(?-?[\d,.]+\)?)\s*(billion|million|十億|十亿|億|亿|百萬|百万|萬|万)?[^\n]{0,100}(?:基石|cornerstone)",
        ]
        scales = {"billion": 1e9, "十億": 1e9, "十亿": 1e9, "億": 1e8, "亿": 1e8, "million": 1e6, "百萬": 1e6, "百万": 1e6, "萬": 1e4, "万": 1e4}
        for pattern in patterns:
            match = re.search(pattern, section, re.I)
            if match:
                raw = match.group(1)
                negative = raw.startswith("(") and raw.endswith(")")
                value = float(raw.strip("()").replace(",", ""))
                return (-abs(value) if negative else value) * scales.get((match.group(2) or "").lower(), 1)
        return None

    @staticmethod
    def _global_offer_ratio(section: str) -> float | None:
        patterns = [
            r"(?:基石投資者|基石投资者|cornerstone investors?)[^。\n%]{0,500}?(?:佔|占|representing)[^。\n%]{0,80}?(?:全球發售|全球发售|Global Offering|發售股份|发售股份)[^\d%]{0,40}([\d.]+)\s*%",
            r"(?:基石投資者|基石投资者|cornerstone investors?)[^。\n%]{0,500}?(?:佔|占|representing|approximately)[^。\n%]{0,120}?([\d.]+)\s*%[^。\n]{0,100}(?:全球發售|全球发售|Global Offering|發售股份|发售股份)",
            r"([\d.]+)\s*%[^。\n]{0,100}(?:全球發售|全球发售|Global Offering|發售股份|发售股份)[^。\n]{0,120}(?:基石|cornerstone)",
        ]
        for pattern in patterns:
            match = re.search(pattern, section, re.I)
            if match:
                value = float(match.group(1))
                if 0 <= value <= 100:
                    return value
        return None

    @staticmethod
    def _quality_score(section: str, names: list[str], ratio: float | None) -> int:
        score = 0
        if any(name.lower() in section.lower() for name in ("Temasek", "GIC", "BlackRock", "Fidelity", "Hillhouse", "腾讯", "阿里巴巴", "主權基金", "主权基金")):
            score += 2
        if len(names) >= 8:
            score += 1
        if ratio is not None and 30 <= ratio <= 60:
            score += 1
        return min(4, score)
