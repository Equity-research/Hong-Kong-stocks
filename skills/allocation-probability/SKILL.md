---
name: allocation-probability
description: Estimate Hong Kong IPO allocation probability and capital efficiency for different application sizes. Use for one-lot odds, multiple-lot scenarios, clawback analysis, financing decisions, and comparing expected allocation outcomes across IPOs.
---

# Allocation Probability

## Preconditions

Require verified board lot, public offer shares or allocation table, clawback terms, offer price, and a demand scenario. Prefer the official allotment-results table once published.

## Workflow

1. Separate pre-close forecasts from post-allotment actuals.
2. Estimate public shares after clawback under low, base, and high demand cases.
3. Model application counts and allocation rules; do not assume equal allocation when ballot or progressive allocation applies.
4. For each application size, estimate probability of at least one lot, expected lots, capital locked, financing cost, and expected capital efficiency.
5. Back-test assumptions against comparable official allotment tables when available.
6. Label model assumptions, uncertainty range, and the observation time of demand inputs.

## Required output

Provide scenario tables for cash one-lot, several cash tiers, and requested financing tiers. Include probability ranges rather than false precision and state clearly that allocation is not guaranteed.

