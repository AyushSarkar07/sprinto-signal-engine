# Revenue & conversion report

Generated 2026-11-03T15:49:30 · outcomes recorded: 1

> **Measured** = pipeline counts and outcomes you logged. **Estimated** = planning assumptions from `data/revenue_assumptions.json` updated by those outcomes. Estimates are never presented as results.

## What to do next (maximising expected revenue)

1. Contact Plain first: highest expected revenue among ready emails (USD 340 = P(win) 2.8% × ACV 12,000).
2. Angle optimisation is off until 10 contacted outcomes are recorded (currently 1). Log outcomes with --record-outcome.
3. 3 draft(s) are waiting at the review gate — revenue cannot move until they are approved (--review).

## Revenue

| Metric | Value | Type |
|---|---|---|
| Won revenue | USD 12,000 (1 deals) | measured |
| Open opportunity value | USD 0 | measured |
| Expected revenue (qualified, not closed) | USD 640 | estimated |
| Blocked: no decision-maker | USD 0 | estimated |
| Blocked: no grounded email | USD 0 | estimated |
| Open rate (opened / contacted) | 1/1 | measured (log 'opened'; pixel tracking is not used) |
| Average deal size | USD 12,000 | measured |

## Funnel

| Stage | Count | Step conversion | From prospects |
|---|---|---|---|
| Prospects | 5 | — | 100% |
| Scraped | 5 | 100% | 100% |
| Qualified | 3 | 60% | 60% |
| Decision-maker found | 3 | 100% | 60% |
| Email ready | 3 | 100% | 60% |
| Approved at review | 0 | 0% | 0% |
| Contacted | 1 | — | 20% |
| Opened | 1 | 100% | 20% |
| Replied | 1 | 100% | 20% |
| Meeting | 1 | 100% | 20% |
| Opportunity | 1 | 100% | 20% |
| Won | 1 | 100% | 20% |

## Stage conversion model (Beta posterior)

| Transition | Observed | Planned prior | Current estimate |
|---|---|---|---|
| → replied | 1/1 | 5% | 9.5% |
| → meeting | 1/1 | 50% | 66.7% |
| → opportunity | 1/1 | 50% | 66.7% |
| → won | 1/1 | 33% | 50.0% |

Contacted → won: observed 1/1, estimated 2.12%.

## Priority queue (sorted by expected revenue)

| # | Company | Stage | ICP | Timing | ACV | P(win) | Expected | Next action |
|---|---|---|---|---|---|---|---|---|
| 1 | Plain | not contacted | 77 | 42 | 12,000 | 2.84% | 340 | Contact now (email ready) |
| 2 | Attio | not contacted | 56 | 34 | 12,000 | 2.50% | 300 | Contact now (email ready) |

ACV basis per company is in `priority_queue.csv`. P(win) before a reply includes a timing lift (0.5 + timing/50, capped) — a heuristic that should be replaced by segment data once outcomes exist.

## Review gate (email quality)

| Metric | Value |
|---|---|
| Drafts | 3 (3 pending) |
| Approved / rejected | 0 / 0 |
| Average share changed by reviewer | — |
| Heavy edits (>50% rewritten) | — |

## Email angle performance

| Pain-point family | Contacted | Replies | Reply rate |
|---|---|---|---|
| questionnaires | 1 | 1 | 100% |