from __future__ import annotations

import logging
import re

from hk_ipo_analyzer.models import IPORecord

LOGGER = logging.getLogger(__name__)

SPONSOR_SCORE_MAP: dict[str, int] = {
    "中金": 3, "CICC": 3, "摩根士丹利": 3, "Morgan Stanley": 3, "高盛": 3, "Goldman Sachs": 3,
    "摩根大通": 3, "J.P. Morgan": 3, "JPMorgan": 3, "瑞銀": 3, "UBS": 3,
    "中信": 3, "CITIC": 3, "海通": 2, "HTSC": 2, "華泰": 2, "Huatai": 2,
    "國泰": 2, "Guotai": 2, "招銀": 2, "CMB": 2, "建銀": 2, "CCB": 2,
    "農銀": 2, "ABC": 2, "工銀": 2, "ICBC": 2, "中銀": 2, "BOCI": 2,
    "中信建投": 2, "光大": 2, "Everbright": 2, "招商": 2,
    "國信": 2, "國金": 2, "廣發": 2, "興業": 2, "銀河": 2,
}


class SponsorParser:
    """从招股书文本提取保荐人列表并评定质量评分。"""

    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        source = "HKEX 招股书"
        names = self._extract_names(text)
        if names:
            record.set_field("sponsors", names, source_url, source, source_tier="A")
        if not record.value("sponsor_quality_score"):
            score = self._score(names)
            record.set_field("sponsor_quality_score", score, source_url, source + "（启发式评估）", source_tier="C")

    @staticmethod
    def _extract_names(text: str) -> list[str]:
        section_match = re.search(
            r"(?:保薦人|保荐人|Sponsors?|聯席保薦人|联席保荐人|獨家保薦人|独家保荐人|聯席全球協調人|联席全球协调人|JOINT SPONSORS?|SOLE SPONSOR)",
            text, re.I,
        )
        if not section_match:
            return []
        fragment = text[section_match.start():section_match.start() + 3000]
        names: list[str] = []
        patterns = [
            r"([A-Z][A-Za-z&.,'()\- ]{6,80}(?:Limited|Ltd\.?|Inc\.?|Capital|Securities|International|Asia|Hong\s*Kong|China|Financial|Corporate|Partners?|Bank|Trust|Group|Holdings))",
            r"([\u4e00-\u9fff（）()]{2,15}(?:國際|资本|證券|证券|融資|融资|企業|企业|銀行|银行|金融|香港|亞洲|中国|中國|集團|集团|有限|公司))",
        ]
        for pattern in patterns:
            found = re.findall(pattern, fragment)
            for name in found:
                clean = " ".join(name.split()).rstrip(".,;，。； （()")
                if 3 < len(clean) < 120 and clean not in names:
                    names.append(clean)
        return names[:10]

    def _score(self, sponsors: list[str]) -> int:
        """根据已知保荐人列表评定质量分数（0-3）"""
        if not sponsors:
            return 0
        scores = []
        for sponsor in sponsors:
            for key, val in SPONSOR_SCORE_MAP.items():
                if key.lower() in sponsor.lower():
                    scores.append(val)
                    break
            else:
                scores.append(1)
        return min(3, max(scores) if scores else 1)
