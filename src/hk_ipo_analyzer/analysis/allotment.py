"""
港股新股中签率预测模型

参考: Marvae/hk-ipo-research-assistant 的 allotment.py

核心原理：
1. 基于分配机制 (A/B) 和超购倍数计算基础一手中签率
2. 应用价格调整因子
3. 手数需求乘数（甲组一手优先，乙组按比例）
4. 几何分布计算多手中签概率
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# 机制系数 K
K_MECHANISM_A = 0.02   # 机制 A (有回拨)
K_MECHANISM_B = 1.65   # 机制 B (无回拨)

# 价格调整
PRICE_BASE = 15.0  # 基准价格（港元）
PRICE_ADJ_MIN = 0.85
PRICE_ADJ_MAX = 1.15

# 甲乙组分界线
GROUP_A_MAX = 5_000_000  # 500万港元

# 概率边界
MAX_BASE_P1 = 0.99


@dataclass
class AllotmentPrediction:
    """中签预测结果"""
    base_p1: float          # 基础一手中签率
    oversub: float          # 超购倍数
    mechanism: str           # 机制 A/B
    group: str              # 甲组/乙组
    lots: int               # 申购手数
    amount: float           # 申购金额
    probability: float      # 至少中一手概率
    expected_lots: float    # 预期中签手数


def predict_base_p1(oversub: float, mechanism: str = "A", price: float = 15.0) -> float:
    """
    预测基础一手中签率

    公式: base_p1 = min(K / oversub * price_adj, MAX_BASE_P1)

    参数:
        oversub: 超购倍数 (> 0)
        mechanism: 分配机制 "A" 或 "B"
        price: 发行价（港元）
    """
    if oversub <= 0:
        return MAX_BASE_P1

    k = K_MECHANISM_A if mechanism == "A" else K_MECHANISM_B
    base = k / oversub

    # 价格调整：低价股中签率略高
    price_adj = PRICE_BASE / max(price, 1.0)
    price_adj = max(PRICE_ADJ_MIN, min(PRICE_ADJ_MAX, price_adj))

    return min(base * price_adj, MAX_BASE_P1)


def lot_demand_multiplier(lots: int, group: str = "A") -> float:
    """
    手数需求乘数

    甲组：一手优先（红鞋制度），多手中签率递减
    乙组：大额按比例分配
    """
    if group == "B":
        return lots  # 乙组按比例

    # 甲组递减
    if lots <= 1:
        return 1.0
    elif lots <= 5:
        return lots * 0.85
    elif lots <= 20:
        return lots * 0.65
    elif lots <= 100:
        return lots * 0.40
    else:
        return lots * 0.25


def calculate_probability(
    oversub: float,
    price: float,
    lot_size: int = 100,
    lots: int = 1,
    mechanism: str = "A"
) -> AllotmentPrediction:
    """
    计算中签概率

    使用几何分布: P(至少中1手) = 1 - (1 - base_p1)^(有效手数)
    """
    base_p1 = predict_base_p1(oversub, mechanism, price)
    amount = lots * lot_size * price

    group = "B" if amount >= GROUP_A_MAX else "A"
    effective_lots = lot_demand_multiplier(lots, group)

    # 几何分布：至少中 1 手的概率
    probability = 1.0 - (1.0 - base_p1) ** effective_lots
    probability = min(probability, 0.9999)

    # 预期中签手数
    expected = base_p1 * effective_lots

    return AllotmentPrediction(
        base_p1=base_p1,
        oversub=oversub,
        mechanism=mechanism,
        group=group,
        lots=lots,
        amount=amount,
        probability=probability,
        expected_lots=expected,
    )


def allotment_table(
    oversub: float,
    price: float,
    lot_size: int = 100,
    mechanism: str = "A",
    max_lots: int = 10
) -> list[dict]:
    """生成中签率表格（各手数档位）"""
    table = []
    lots_list = [1, 2, 3, 5, 10, 20, 50, 100, 200, 500]
    lots_list = [l for l in lots_list if l <= max_lots * 10]

    for lots in lots_list:
        pred = calculate_probability(oversub, price, lot_size, lots, mechanism)
        table.append({
            "lots": lots,
            "amount": round(pred.amount, 0),
            "probability_pct": round(pred.probability * 100, 2),
            "expected_lots": round(pred.expected_lots, 2),
            "group": pred.group,
        })

    return table


def format_allotment_table(
    oversub: float,
    price: float,
    lot_size: int = 100,
    mechanism: str = "A"
) -> str:
    """格式化中签率表格（Markdown）"""
    table = allotment_table(oversub, price, lot_size, mechanism)

    lines = [
        f"## 中签率预测（超购 {oversub:.1f}x, 发行价 HK${price:.2f}）",
        "",
        "| 手数 | 金额(HK$) | 中签率 | 预期中签 | 分组 |",
        "| ---: | ---: | ---: | ---: | --- |",
    ]

    for row in table[:15]:
        lines.append(
            f"| {row['lots']} | {row['amount']:,.0f} | "
            f"{row['probability_pct']:.2f}% | {row['expected_lots']:.2f}手 | "
            f"{row['group']}组 |"
        )

    return "\n".join(lines)
