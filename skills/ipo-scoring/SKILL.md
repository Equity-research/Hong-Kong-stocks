---
name: ipo-scoring
description: Score and rank verified Hong Kong IPO records with deterministic, confidence-aware rules. Use for cross-IPO comparison, daily rankings, score calibration, recommendation generation, or explaining why an IPO received a score.
---

# IPO Scoring

## Preconditions

- Score only records whose identity and offering status are verified.
- For a current-subscription ranking, require the analysis date to fall inside the verified offer window.
- Keep data completeness separate from investment quality. Missing evidence earns no points and lowers confidence; it is not a negative business fact.

## Workflow

1. Load the field contract from `src/hk_ipo_analyzer/models.py`.
2. Use the deterministic dimensions in `analysis/scoring_model.py`: fundamentals, sector, offer structure, cornerstone, market heat, and risk deductions.
3. Normalize units and as-of times before comparing records.
4. Explain each subscore with cited inputs, thresholds, and missing fields.
5. Rank by score only after showing confidence and coverage. Do not let a low-confidence score outrank a well-supported score without a warning.
6. Run sensitivity cases when valuation, subscription heat, or peer data is estimated.

## Required output

Produce a comparison table containing score, confidence, five dimension scores, risk deduction, recommendation, critical missing inputs, and top positive/negative drivers. Mark estimates and stale observations visibly.

