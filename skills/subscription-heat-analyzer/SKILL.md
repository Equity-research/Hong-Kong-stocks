---
name: subscription-heat-analyzer
description: Track and analyze Hong Kong IPO margin financing, subscription multiples, broker snapshots, public-offer demand, and market attention over time. Use for live subscription heat checks, momentum changes, funding-cost analysis, and daily IPO heat comparisons.
---

# Subscription Heat Analyzer

## Data rules

- Accept only timestamped observations with source URLs or named manual evidence.
- Distinguish margin amount, margin multiple, expected oversubscription, and official final oversubscription.
- Never mix currencies, observation times, or forecast and actual values.
- Do not treat social attention as verified subscription demand.

## Workflow

1. Confirm the IPO is inside its offer window.
2. Build a time series by IPO and source from `data/manual_override.csv` and verified public sources.
3. Deduplicate same-source snapshots and retain the latest observation at each cutoff.
4. Calculate absolute heat, change rate, acceleration, source dispersion, and funding-cost break-even where inputs exist.
5. Classify heat as cold, neutral, warm, hot, or extreme using explicit thresholds; show the observation age.
6. Flag stale, conflicting, forecast-only, or source-incomplete data.

## Required output

Show latest margin amount/multiple, official or expected oversubscription, change since prior snapshot, source count, observation time, heat classification, confidence, and implications for allocation and financing risk.

