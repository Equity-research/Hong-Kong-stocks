---
name: ipo-report-ui
description: Improve the information design and visual readability of Hong Kong IPO Markdown or HTML reports without changing underlying facts. Use for report beautification, dashboard-like summaries, mobile readability, comparison tables, risk callouts, and consistent report templates.
---

# IPO Report UI

## Design principles

- Preserve every number, source, confidence value, and missing-data warning.
- Lead with the validated universe rule and count; never beautify an incorrect population into apparent certainty.
- Optimize for a 60-second scan: decision first, evidence second, full detail last.
- Use semantic labels consistently: positive, neutral, caution, high risk, and missing.
- Keep Markdown portable; produce HTML/CSS only when explicitly requested.

## Markdown structure

1. Title, analysis date, data cutoff, and disclaimer.
2. Data-quality banner with coverage, exclusions, stale sources, and confidence.
3. Executive cards represented as compact tables: current IPO count, top score, hottest subscription, and highest risk.
4. Ranked overview table with score, confidence, valuation, heat, allocation odds, grey signal, and recommendation.
5. Per-IPO sections using the same order and collapsible HTML details only when the target renderer supports them.
6. Methodology, source ledger, missing fields, and disclaimer at the end.

## Visual rules

- Use icons sparingly and never as the only signal.
- Keep tables narrow enough for mobile; move long rationale below tables.
- Round presentation values consistently while preserving source precision in evidence records.
- Use horizontal separators and short callouts instead of decorative clutter.
- Do not hide zero confidence, missing dates, conflicting sources, or model assumptions.

## Repository integration

Write generated Markdown to `reports/`. Keep data logic in analyzers and formatting logic in `src/hk_ipo_analyzer/reporting.py`. Validate that redesigned output renders cleanly as plain Markdown before delivery.

