# Sweetgreen — Sprinto Signal Engine research report

*Domain:* `sweetgreen.com` · *Generated:* 2026-11-19 11:08 · *Extraction:* deterministic fallback — rule-based, not AI-verified

## Decision

**NOT_QUALIFIED** → recommended action: **disqualify**

| Dimension | Value |
|---|---|
| ICP fit | 0/100 |
| Buying timing | 0/100 |
| Evidence confidence | 0.58 |
| Secondary research | 2 round(s) |

- Evidence Map → DROP: Short-circuit on 'Is it a SaaS business?': Not SaaS — outside Sprinto's ICP whatever else is true.
- Scores: ICP 0/100, timing 0/100, evidence confidence 0.58.
- Biggest ICP drivers: SaaS business model (0/25) — Evidence indicates a non-SaaS business.; Relevant growth stage (Series A–C) (0/15) — Growth stage unknown (missing, not negative).
- Biggest timing drivers: Explicit SOC 2 / ISO 27001 / audit requirement (0/30) — No explicit audit or certification requirement observed.; Enterprise security review / procurement pressure (0/25) — No security-review pressure observed.
- Extraction ran in deterministic fallback mode (Claude not used); confidence capped at 0.75. Results are rule-based, not AI-verified.

### Evidence Map → **DROP**

| Question (core in bold) | Answer | Basis | Pages read / budget | If unanswered | Evidence |
|---|---|---|---|---|---|
| Is there still something to certify? | UNKNOWN | No security or trust page read yet. | 0/2 | Treat as pass | — |
| Is it free of a competing compliance platform? | UNKNOWN | No security or trust page read yet. | 0/2 | Treat as pass | — |
| **Is it a SaaS business?** | NO | Evidence describes a non-software business. | 4/3 | Flag at review gate | "Our restaurants" — https://careers.sweetgreen.com/<br>"Check out our regional bakery partners" — https://sweetgreen.com/ |
| **Is it Series A–C / 50–200 employees?** | UNKNOWN | Neither funding stage nor headcount stated on the pages read. | 1/3 | Flag at review gate | — |
| **Is it preparing for an audit (SOC 2 / ISO 27001)?** | NO | No certification under way and no security/compliance hire on the 1 security, trust or careers page(s) read. | 1/4 | Nurture (right company, wrong time) | — |
| Does it have >50 clients / larger customers? | UNKNOWN | No customer references found. | 1/2 | Neutral | — |
| Does it serve a regulated industry? | UNKNOWN | Customer industries not identified as regulated. | 1/2 | Neutral | — |
| Is it on AWS / GCP / Azure? | UNKNOWN | Cloud provider not stated. | 1/2 | Neutral | — |

## 1. Website intelligence

Scraping status: **partial** · pages read: 6 of 13 attempted

| Type | Status | URL | Fetched via |
|---|---|---|---|
| homepage | ok | https://sweetgreen.com/ | requests |
| about | not_found | https://sweetgreen.com/about | requests |
| security | not_found | https://sweetgreen.com/security | requests |
| trust | not_found | https://sweetgreen.com/trust | requests |
| customers | not_found | https://sweetgreen.com/customers | requests |
| pricing | ok | https://sweetgreen.com/pricing | requests |
| product | ok | https://order.sweetgreen.com/order-product/rosemary-focaccia | requests |
| about | not_found | https://sweetgreen.com/company | requests |
| news | ok | https://sweetgreen.com/press | requests |
| product | ok | https://order.sweetgreen.com/order-product/pesto-chicken-parmesan | requests |
| careers | ok | https://careers.sweetgreen.com/ | requests |
| customers | not_found | https://sweetgreen.com/case-studies | requests |
| enterprise | not_found | https://sweetgreen.com/enterprise | requests |

Errors: https://sweetgreen.com/about: not_found; https://sweetgreen.com/security: not_found; https://sweetgreen.com/trust: not_found; https://sweetgreen.com/customers: not_found

## 2. Extracted company profile

| Field | Value |
|---|---|
| Business | healthy salads, hearty wraps, grain bowls, and warm plates made in-house from scratch, using whole produce delivered that morning. |
| SaaS? | False (Not SaaS (rule-based assessment)) |
| Funding stage | not stated |
| Headcount | not stated |
| Industries | not identified |
| Tech stack (explicit only) | none stated |
| Trust centre | False |

### Buying moments

None observed. (No buying moment was invented.)

**Missing information:** Funding stage or headcount; Evidence of enterprise customers or an enterprise motion; Any SOC 2 / ISO 27001 / GDPR status; Security, compliance or engineering hiring activity; A security or trust page describing controls

## 3. Qualification scoring

### ICP fit

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| SaaS business model | 0/25 | Evidence indicates a non-SaaS business. |  |
| Relevant growth stage (Series A–C) | 0/15 | Growth stage unknown (missing, not negative). |  |
| Enterprise customer orientation | 0/20 | No enterprise orientation observed. |  |
| Relevant customer industry | 0/10 | Customer industries not identified. |  |
| Company scaling signals | 0/10 | No scaling signals observed. |  |
| Security / compliance complexity | 0/20 | No security/compliance content observed. |  |

### Buying timing

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| Explicit SOC 2 / ISO 27001 / audit requirement | 0/30 | No explicit audit or certification requirement observed. |  |
| Enterprise security review / procurement pressure | 0/25 | No security-review pressure observed. |  |
| Security or compliance hiring | 0/20 | No security roles found. |  |
| Trust centre or compliance activity | 0/10 | No trust centre found. |  |
| Recent enterprise expansion / scaling | 0/15 | No recent expansion signal. |  |

### Research agent log

**Round 1** — open questions: Is this a subscription software business?; What stage / size is the company?; Does it sell to enterprises?; What is its SOC 2 / ISO 27001 / GDPR status?; Is it hiring for security, compliance or engineering?; Does it publish security controls or a trust centre?; Is there any evidence compliance matters right now?

- Targeted: https://sweetgreen.com/pricing [pricing] — Is this a subscription software business?, Does it sell to enterprises?
- Targeted: https://order.sweetgreen.com/order-product/rosemary-focaccia [product] — Is this a subscription software business?
- Targeted: https://sweetgreen.com/company [about] — Is this a subscription software business?, What stage / size is the company?
- Targeted: https://sweetgreen.com/press [news] — What stage / size is the company?, Is there any evidence compliance matters right now?
- Readable: 3 page(s)
- **What changed:** ICP 0→0, timing 0→0, decision insufficient_data→insufficient_data. No new evidence found on these pages.

**Round 2** — open questions: Is this a subscription software business?; What stage / size is the company?; Does it sell to enterprises?; What is its SOC 2 / ISO 27001 / GDPR status?; Is it hiring for security, compliance or engineering?; Does it publish security controls or a trust centre?; Is there any evidence compliance matters right now?

- Targeted: https://order.sweetgreen.com/order-product/pesto-chicken-parmesan [product] — Is this a subscription software business?
- Targeted: https://careers.sweetgreen.com/ [careers] — What stage / size is the company?, Is it hiring for security, compliance or engineering?, Is there any evidence compliance matters right now?
- Targeted: https://sweetgreen.com/case-studies [customers] — Does it sell to enterprises?, Is there any evidence compliance matters right now?
- Targeted: https://sweetgreen.com/enterprise [enterprise] — Does it sell to enterprises?
- Readable: 2 page(s)
- New: Hospitality / retail locations (https://careers.sweetgreen.com/)
- **What changed:** ICP 0→0, timing 0→0, decision insufficient_data→not_qualified. 1 new evidence item(s).


## 4. Decision-maker

Not attempted (company not qualified).

## Decision ledger

### WHY THIS COMPANY?

- No ICP criteria were satisfied by evidence.

### WHY NOW?

- No observable buying moment — timing unsupported.

### WHAT COULD MAKE THIS DECISION WRONG?

- Unknown: Funding stage or headcount.
- Unknown: Evidence of enterprise customers or an enterprise motion.
- Unknown: Any SOC 2 / ISO 27001 / GDPR status.
- Unknown: Security, compliance or engineering hiring activity.
- Unknown: A security or trust page describing controls.
- Overall evidence confidence is modest (0.58).
- Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).

## Evidence appendix

| ID | Category | Finding | Type | Conf. | URL | Excerpt |
|---|---|---|---|---|---|---|
| fb89332b27 | other | Business description (homepage / meta description) | explicit | 0.7 | https://sweetgreen.com/ | healthy salads, hearty wraps, grain bowls, and warm plates made in-house from scratch, using whole produce delivered that morning. |
| 70112fe7c7 | non_saas_indicator | Hospitality / retail locations | explicit | 0.6 | https://careers.sweetgreen.com/ | Our restaurants |
| 30c996bfd5 | non_saas_indicator | Food & beverage | explicit | 0.6 | https://sweetgreen.com/ | Check out our regional bakery partners |
