---
name: valuation-analyzer
description: Assess Hong Kong IPO offer valuation using verified financials, peer multiples, growth, profitability, and scenario ranges. Use for pricing analysis, premium or discount calculations, fair-value ranges, and valuation score inputs.
---

# Valuation Analyzer

## Workflow

1. Verify offer price range, enlarged share count, implied market cap, net cash/debt, and financial period.
2. Choose metrics appropriate to the business: P/E for sustainable earnings, P/S for early-stage revenue, EV/EBITDA when meaningful, and NAV-based measures for asset-heavy issuers.
3. Normalize peer fiscal periods, currencies, exceptional items, and share structures.
4. Calculate low/high offer multiples and peer discount or premium.
5. Build bear/base/bull fair-value ranges with explicit growth, margin, and multiple assumptions.
6. Translate evidence into `issuer_pe`, `peer_median_pe`, and `valuation_score` only when supported.

## Guardrails

Do not use negative P/E as a meaningful multiple. Do not mix trailing and forward estimates silently. Do not present a target price when critical share-count or financial inputs are missing.

## Required output

Show input reconciliation, valuation table, peer range, scenario range, implied upside/downside, sensitivity, confidence, and the largest sources of model risk.

