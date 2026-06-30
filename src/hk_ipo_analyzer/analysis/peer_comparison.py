from __future__ import annotations

from hk_ipo_analyzer.models import IPORecord


class PeerComparison:
    """首版消费已验证的手工同行数据，不自动猜测可比公司。"""

    def summary(self, record: IPORecord) -> dict:
        return {
            "peer_median_first_day_return_pct": record.value("peer_median_first_day_return_pct"),
            "peer_median_pe": record.value("peer_median_pe"),
            "issuer_pe": record.value("issuer_pe"),
        }

