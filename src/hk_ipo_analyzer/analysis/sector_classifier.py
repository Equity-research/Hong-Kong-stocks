from __future__ import annotations

from hk_ipo_analyzer.models import IPORecord


SECTOR_KEYWORDS = {
    "创新药": ("biotech", "biopharma", "drug discovery", "生物科技", "創新藥", "创新药"),
    "医药": ("pharmaceutical", "medical", "healthcare", "醫療", "医药"),
    "AI": ("artificial intelligence", "large language model", "人工智能", "大模型"),
    "半导体": ("semiconductor", "integrated circuit", "芯片", "半導體", "半导体"),
    "机器人": ("robot", "automation", "機器人", "机器人"),
    "新能源": ("solar", "battery", "新能源", "光伏", "儲能", "储能"),
    "SaaS": ("saas", "software as a service", "雲軟件", "云软件"),
    "消费": ("consumer", "retail", "food", "消費", "零售", "食品"),
    "物业": ("property management", "物業管理", "物业管理"),
    "金融": ("financial services", "insurance", "銀行", "金融", "保險", "保险"),
    "教育": ("education", "training", "教育", "培訓", "培训"),
    "制造业": ("manufacturing", "manufacturer", "製造", "制造"),
}


class SectorClassifier:
    def classify(self, record: IPORecord, text: str = "") -> str | None:
        haystack = f"{record.company_name} {record.value('business_description', '')} {text[:30000]}".lower()
        scored = {
            sector: sum(haystack.count(keyword.lower()) for keyword in keywords)
            for sector, keywords in SECTOR_KEYWORDS.items()
        }
        sector, count = max(scored.items(), key=lambda item: item[1])
        return sector if count else None

