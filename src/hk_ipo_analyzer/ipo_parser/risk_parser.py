from __future__ import annotations

from hk_ipo_analyzer.models import IPORecord


RISK_KEYWORDS = {
    "持续亏损": ("net loss", "loss-making", "淨虧損", "净亏损"),
    "客户高度集中": ("customer concentration", "依賴主要客戶", "依赖主要客户"),
    "监管风险": ("regulatory risk", "regulatory approval", "監管批准", "监管批准"),
    "诉讼合规": ("litigation", "legal proceedings", "訴訟", "诉讼"),
    "研发失败": ("research and development may", "clinical trial", "研發失敗", "临床试验"),
}


class RiskParser:
    def parse(self, text: str, record: IPORecord, source_url: str) -> None:
        lowered = text.lower()
        tags = [tag for tag, words in RISK_KEYWORDS.items() if any(word.lower() in lowered for word in words)]
        record.risk_tags = sorted(set(record.risk_tags + tags))
        if tags:
            record.set_field("risk_tags", record.risk_tags, source_url, "HKEX 招股书", overwrite=True)

