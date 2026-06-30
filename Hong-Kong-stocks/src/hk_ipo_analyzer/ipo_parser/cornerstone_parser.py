from __future__ import annotations

import logging
import re

from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)


class CornerstoneParser:
    """增强的基石投资者解析：名称、金额、占比、锁定期 + 质量评分启发。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        section = self._section(text)
        if not section:
            return
        self._parse_names(section, record, source_url)
        self._parse_amount(section, record, source_url)
        self._parse_ratio(section, record, source_url)
        self._parse_lockup(section, record, source_url)
        self._score_quality(section, record, source_url)

    @staticmethod
    def _section(text: str) -> str:
        match = re.search(r"CORNERSTONE INVESTORS?|基石投資者|基石投资者", text, re.I)
        return text[match.start() : match.start() + 40000] if match else ""

    def _parse_names(self, section: str, record: IPORecord, source_url: str) -> None:
        source = "HKEX 招股书"
        names: list[str] = []
        patterns = [
            r"(?:entered into|與|与)\s+(?:a\s+)?cornerstone investment agreement[^\n]{0,80}(?:with|和|與|与)[：:]?\s*([^\n]{4,120}?)(?:，|。|,|\n|HK\$|港幣|港元|，a)",
            r"([A-Z][A-Za-z&.,'()\- ]{6,80}(?:Limited|Ltd\.?|Inc\.?|Corp\.?|Corporation|Group|Holdings|Capital|Investment|Asset|Fund|Management|Technology|International|Partners?|Enterprise|Company|Financial|Securities|Bank|Trust|Development|Industrial|Pharmaceutical|Biotech|Venture|Private|Equity|Advisors?|Associates?|LLC|LLP|PLC|S\.A\.|B\.V\.|GmbH|Co\.))\s+(?:已|已經|已同意|同意|已訂立|已订立)",
            r"([\u4e00-\u9fff（）()]{3,20}(?:集團|控股|有限|投资|科技|基金|资产|资本|证券|实业|医疗|医药|生物|电子|半导体|机器人|能源|材料|化工|消费|零售|地产|金融|保险|银行|国际|香港|中国|企業|公司))\s+(?:已|已經|已同意|同意|已訂立|已订立)",
        ]
        for pattern in patterns:
            found = re.findall(pattern, section, re.I)
            for name in found:
                clean = " ".join(name.split()).rstrip(".,;，。； （()")
                if 3 < len(clean) < 120 and clean not in names:
                    names.append(clean)
        if names:
            record.set_field("cornerstone_investors", names[:20], source_url, source)
            record.set_field("cornerstone_count", len(names[:20]), source_url, source)

    def _parse_amount(self, section: str, record: IPORecord, source_url: str) -> None:
        if record.value("cornerstone_amount_hkd"):
            return
        patterns = [
            r"(?:總額|總認購金額|認購總額|投資總額|合共|共計|合計|合約)[^\d]{0,80}(?:HK\$|港幣|港元)?\s*([\d.,]+)\s*([億亿万萬千]?)",
            r"(?:HK\$|港幣|港元)\s*([\d.,]+)\s*([億亿万萬千]?)\s*(?:港元)?[^%]{0,40}(?:基石|cornerstone)",
        ]
        for pattern in patterns:
            match = re.search(pattern, section, re.I)
            if match:
                num = float(match.group(1).replace(",", ""))
                mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
                record.set_field("cornerstone_amount_hkd", num * mult.get(match.group(2) or "", 1), source_url, "HKEX 招股书")
                return

    def _parse_ratio(self, section: str, record: IPORecord, source_url: str) -> None:
        if record.value("cornerstone_ratio"):
            return
        patterns = [
            r"cornerstone investors?[^%\d]{0,600}?([\d.]+)\s*%",
            r"([\d.]+)\s*%[^%]{0,40}(?:cornerstone|基石)",
            r"(?:佔|占|約|相当于|相當於)[^\d.]{0,80}([\d.]+)\s*%[^%]{0,30}(?:發售股份|发售股份|發行股份|发行股份|全球發售|全球发售)",
        ]
        for pattern in patterns:
            match = re.search(pattern, section, re.I)
            if match:
                record.set_field("cornerstone_ratio", float(match.group(1)), source_url, "HKEX 招股书")
                return

    def _parse_lockup(self, section: str, record: IPORecord, source_url: str) -> None:
        if record.value("cornerstone_lockup_months"):
            return
        lockup = re.search(r"(?:lock-up period of|禁售期|鎖定期)[^\d]{0,30}(\d+)\s*(?:months|個月|个月)", section, re.I)
        if lockup:
            record.set_field("cornerstone_lockup_months", int(lockup.group(1)), source_url, "HKEX 招股书")

    def _score_quality(self, section: str, record: IPORecord, source_url: str) -> None:
        """启发式评估基石投资者质量（0-4）"""
        if record.value("cornerstone_quality_score") is not None:
            return
        score = 0
        high_quality = [
            "Temasek", "GIC", "BlackRock", "Fidelity", "Capital Group", "J.P. Morgan",
            "Morgan Stanley", "Goldman Sachs", "UBS", "CPP", "Norges", "Ontario",
            "Hillhouse", "Boyu", "Sequoia", "SoftBank", "腾讯", "阿里巴巴", "國壽", "人寿",
            "中國人壽", "中國平安", "太保", "太平", "社保基金", "主權基金", "Sovereign",
        ]
        for name in high_quality:
            if name.lower() in section.lower():
                score += 2
                break
        medium_quality = [
            "Asset Management", "Capital", "Investment", "Fund", "Venture", "Private Equity",
            "資產管理", "投資", "基金", "资本", "資產", "投資管理",
        ]
        for name in medium_quality:
            if name.lower() in section.lower():
                score += 1
                break
        count = record.value("cornerstone_count") or 0
        if isinstance(count, (int, float)) and count >= 8:
            score += 1
        ratio = record.value("cornerstone_ratio") or 0
        if isinstance(ratio, (int, float)) and 30 <= ratio <= 60:
            score += 1
        record.set_field("cornerstone_quality_score", min(4, score), source_url, "HKEX 招股书（启发式评估）")
