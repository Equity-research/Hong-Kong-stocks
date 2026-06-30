---
name: grey-market-analyzer
description: Analyze verified Hong Kong IPO grey-market prices, returns, liquidity, spread, and intraday sentiment. Use after grey-market trading opens for short-term strategy, broker-price comparison, momentum checks, and listing-day expectation updates.
---

# Grey Market Analyzer

## Data rules

- Do not populate grey-market fields before the grey session opens.
- Record broker/venue, quote time, currency, price basis, volume if available, and source.
- Separate executable trades from indicative quotes and separate different broker venues.

## Workflow

1. Verify final offer price and board lot.
2. Compute return, lot-level profit before and after fees, range, spread, liquidity, and momentum by timestamp.
3. Compare venues without averaging away meaningful disagreement.
4. Contrast grey performance with subscription heat, allocation concentration, and comparable IPOs.
5. Produce bull/base/bear listing-day implications, not a single-point forecast.
6. Flag thin liquidity, stale prices, one-sided quotes, and abnormal volatility.

## Required output

Show timestamped price observations, return and net lot profit, liquidity quality, cross-venue dispersion, confidence, key risks, and how the evidence changes—not determines—the listing-day plan.

