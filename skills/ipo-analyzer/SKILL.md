---
name: ipo-analyzer
description: Read Hong Kong IPO prospectuses and verified offering documents, extract evidence-backed fields, and produce a complete analysis record and report. Use for prospectus review, IPO due diligence, daily IPO reports, or repairing incomplete records in this repository.
---

# IPO Analyzer

## Workflow

1. Resolve the analysis date and universe before reading documents.
2. Treat an IPO as currently subscribable only when verified `offer_start_date <= analysis_date <= offer_end_date`.
3. Keep upcoming, closed, listed, hearing-stage, applicant-only, withdrawn, and duplicate records outside the current-subscription count unless explicitly requested.
4. Prefer HKEX prospectuses and allotment announcements. Record `value`, `source_url`, `source_name`, and `fetched_at` for every extracted field.
5. Extract offering terms, business model, financials, cash flow, margins, concentration, cornerstone allocation, use of proceeds, sponsors, material risks, and timetable.
6. Reconcile conflicting figures by document date and section authority; preserve the conflict in notes.
7. Run the repository scoring and reporting workflow only after universe validation.

## Repository integration

- Read models from `src/hk_ipo_analyzer/models.py` and preserve `IPORecord` field names.
- Use parsers under `src/hk_ipo_analyzer/ipo_parser/`; extend them when a verified field is repeatedly missed.
- Save auditable records under `data/raw/YYYY-MM-DD/` and reports under `reports/`.
- Never turn a missing value into zero. Never infer an offering date from a hearing or listing-candidate page.

## Required output

Report the validated universe count, inclusion rule, exclusions with reasons, source coverage, missing critical fields, company analysis, offering analysis, risks, score confidence, and explicit limitations.

