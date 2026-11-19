# Attio — Sprinto Signal Engine research report

*Domain:* `attio.com` · *Generated:* 2026-11-19 11:08 · *Extraction:* deterministic fallback — rule-based, not AI-verified

## Decision

**NOT_QUALIFIED** → recommended action: **disqualify**

| Dimension | Value |
|---|---|
| ICP fit | 46/100 |
| Buying timing | 7/100 |
| Evidence confidence | 0.72 |
| Secondary research | 0 round(s) |

- Evidence Map → DROP: Short-circuit on 'Is it free of a competing compliance platform?': Already uses Vanta; a displacement, not a first purchase. Not cold outbound.
- Scores: ICP 46/100, timing 7/100, evidence confidence 0.72.
- Biggest ICP drivers: SaaS business model (22.5/25) — SaaS model supported by 5 indicator(s).; Relevant growth stage (Series A–C) (15/15) — Explicit Series C — inside Sprinto's sweet spot.
- Biggest timing drivers: Trust centre or compliance activity (10/10) — Trust centre published.; Recent enterprise expansion / scaling (6.8/15) — 1 expansion / funding signal(s).
- Extraction ran in deterministic fallback mode (Claude not used); confidence capped at 0.75. Results are rule-based, not AI-verified.

### Evidence Map → **DROP**

| Question (core in bold) | Answer | Basis | Pages read / budget | If unanswered | Evidence |
|---|---|---|---|---|---|
| Is there still something to certify? | UNKNOWN | Its trust centre is drawn by JavaScript, so the certifications it lists could not be read. | 2/2 | Treat as pass | — |
| Is it free of a competing compliance platform? | NO | Trust centre runs on Vanta (detected in its page source). | 2/2 | Treat as pass | "Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source)" — https://attio.com/security |
| **Is it a SaaS business?** | YES | Subscription-software indicators found (pricing/trial/login/API). | 1/3 | Flag at review gate | "Start for free" — https://attio.com/<br>"Talk to sales" — https://attio.com/ |
| **Is it Series A–C / 50–200 employees?** | YES | Inside the Series A–C / 50–200 employee band (Series C, 190+ team members). | 1/3 | Flag at review gate | "Raised $125M Series C" — https://attio.com/<br>"190+ team members." — https://attio.com/about |
| **Is it preparing for an audit (SOC 2 / ISO 27001)?** | NO | No certification under way and no security/compliance hire on the 2 security, trust or careers page(s) read. | 2/4 | Nurture (right company, wrong time) | — |
| Does it have >50 clients / larger customers? | YES | A stated customer count of 50 or more. | 2/2 | Neutral | "Trusted by 30,000+ customers." — https://attio.com/ |
| Does it serve a regulated industry? | UNKNOWN | Customer industries not identified as regulated. | 3/2 | Neutral | — |
| Is it on AWS / GCP / Azure? | UNKNOWN | Cloud provider not stated. | 1/2 | Neutral | — |

## 1. Website intelligence

Scraping status: **success** · pages read: 5 of 5 attempted

| Type | Status | URL | Fetched via |
|---|---|---|---|
| homepage | ok | https://attio.com/ | requests |
| about | ok | https://attio.com/about | requests |
| security | ok | https://attio.com/security | requests |
| trust | ok | https://trust.attio.com/ | requests |
| customers | ok | https://attio.com/customers | requests |

## 2. Extracted company profile

| Field | Value |
|---|---|
| Business | The system for revenue teams to build pipeline, accelerate deals, and grow accounts around the clock. |
| SaaS? | True (B2B SaaS (rule-based assessment)) |
| Funding stage | Series C |
| Headcount | 190+ team members |
| Industries | not identified |
| Tech stack (explicit only) | none stated |
| Trust centre | True |

### Buying moments

| Signal | Conf. | Needs research | Why it matters commercially | Evidence |
|---|---|---|---|---|
| Trust centre page is live | 0.85 | no | A trust centre signals that customers are actively asking for security documentation during deals. | "Attio Trust Center" — https://trust.attio.com/ |
| Funding announcement: Raised $125M Series C | 0.85 | no | A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it. | "Raised $125M Series C" — https://attio.com/ |
| Customer stories page exists: Customers \| Attio | 0.6 | no | Named larger customers suggest the company is already exposed to enterprise security requirements. | "Discover how thousands of companies use Attio to scale their business." — https://attio.com/customers |

**Missing information:** Any SOC 2 / ISO 27001 / GDPR status; Security, compliance or engineering hiring activity

## 3. Qualification scoring

### ICP fit

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| SaaS business model | 22.5/25 | SaaS model supported by 5 indicator(s). | 363b00a68e, 1e938472fe, cae74f4992, 5541433d8f, 46f2433c77 |
| Relevant growth stage (Series A–C) | 15/15 | Explicit Series C — inside Sprinto's sweet spot. | 950dd2cfe3, af49a70815 |
| Enterprise customer orientation | 8.9/20 | 2 enterprise reference(s) / enterprise-tier signals. | 7468d1a24f, 5c78683444 |
| Relevant customer industry | 0/10 | Customer industries not identified. |  |
| Company scaling signals | 0/10 | No scaling signals observed. |  |
| Security / compliance complexity | 0/20 | No security/compliance content observed. |  |

### Buying timing

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| Explicit SOC 2 / ISO 27001 / audit requirement | 0/30 | No explicit audit or certification requirement observed. |  |
| Enterprise security review / procurement pressure | 0/25 | No security-review pressure observed. |  |
| Security or compliance hiring | 0/20 | No security roles found. |  |
| Trust centre or compliance activity | 10/10 | Trust centre published. | 6266911d73, 0b5e63181c |
| Recent enterprise expansion / scaling | 6.8/15 | 1 expansion / funding signal(s). | 950dd2cfe3 |

Penalties: -10 timing: compliance platform already visible (Trust centre runs on Vanta) — this is a displacement, not a greenfield, conversation.

### Research agent log

- Stopped before round 1: Clear disqualification — further research would not change the outcome.

## 4. Decision-maker

Not attempted (company not qualified).

## Decision ledger

### WHY THIS COMPANY?

- SaaS business model +22.5/25: SaaS model supported by 5 indicator(s). [363b00a68e] "Start for free" (https://attio.com/); [1e938472fe] "Talk to sales" (https://attio.com/)
- Relevant growth stage (Series A–C) +15/15: Explicit Series C — inside Sprinto's sweet spot. [950dd2cfe3] "Raised $125M Series C" (https://attio.com/); [af49a70815] "190+ team members." (https://attio.com/about)
- Enterprise customer orientation +8.9/20: 2 enterprise reference(s) / enterprise-tier signals. [7468d1a24f] "Trusted by 30,000+ customers." (https://attio.com/); [5c78683444] "Discover how thousands of companies use Attio to scale their business." (https://attio.com/customers)

### WHY NOW?

- Trust centre or compliance activity +10/10: Trust centre published. [6266911d73] "Attio Trust Center" (https://trust.attio.com/); [0b5e63181c] "Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source)" (https://attio.com/security)
- Recent enterprise expansion / scaling +6.8/15: 1 expansion / funding signal(s). [950dd2cfe3] "Raised $125M Series C" (https://attio.com/)
- Buying moment — Trust centre page is live: A trust centre signals that customers are actively asking for security documentation during deals. (https://trust.attio.com/)
- Buying moment — Funding announcement: Raised $125M Series C: A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it. (https://attio.com/)
- Buying moment — Customer stories page exists: Customers | Attio: Named larger customers suggest the company is already exposed to enterprise security requirements. (https://attio.com/customers)

### WHAT COULD MAKE THIS DECISION WRONG?

- 4 of 14 evidence items are inferred rather than explicitly stated.
- Unknown: Any SOC 2 / ISO 27001 / GDPR status.
- Unknown: Security, compliance or engineering hiring activity.
- A compliance automation vendor already appears on the site; switching costs may block a deal.
- Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).
- -10 timing: compliance platform already visible (Trust centre runs on Vanta) — this is a displacement, not a greenfield, conversation.

## Evidence appendix

| ID | Category | Finding | Type | Conf. | URL | Excerpt |
|---|---|---|---|---|---|---|
| e132b32a58 | other | Business description (homepage / meta description) | explicit | 0.7 | https://attio.com/ | The system for revenue teams to build pipeline, accelerate deals, and grow accounts around the clock. |
| 363b00a68e | saas_indicator | Self-serve free trial / sign-up | explicit | 0.6 | https://attio.com/ | Start for free |
| 1e938472fe | saas_indicator | Product demo / sales-led motion | explicit | 0.6 | https://attio.com/ | Talk to sales |
| cae74f4992 | saas_indicator | Developer API | inferred | 0.4 | https://attio.com/ | Joshua to send documentation on the public API |
| 5541433d8f | saas_indicator | Platform positioning | inferred | 0.4 | https://attio.com/ | Attio is the platform that builds pipeline, advances deals, and grows accounts around the clock. |
| 46f2433c77 | saas_indicator | Workflow / automation product | inferred | 0.4 | https://attio.com/ | It covers the workflow automations you flagged. |
| 7468d1a24f | enterprise_customer | Customer reference: Trusted by 30,000+ customers | inferred | 0.55 | https://attio.com/ | Trusted by 30,000+ customers. |
| 5c78683444 | enterprise_customer | Customer stories page exists: Customers \| Attio | explicit | 0.6 | https://attio.com/customers | Discover how thousands of companies use Attio to scale their business. |
| af49a70815 | other | Headcount mention: 190+ team members | explicit | 0.7 | https://attio.com/about | 190+ team members. |
| 950dd2cfe3 | funding | Funding announcement: Raised $125M Series C | explicit | 0.85 | https://attio.com/ | Raised $125M Series C |
| 6266911d73 | trust_centre | Trust centre page is live | explicit | 0.85 | https://trust.attio.com/ | Attio Trust Center |
| 0b5e63181c | trust_centre | References a Trust centre | explicit | 0.7 | https://attio.com/security | Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source) |
| 41fa6b3d2f | competitor_platform | Trust centre runs on Vanta | explicit | 0.9 | https://attio.com/security | Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source) |
| 628f31e55d | competitor_platform | Trust centre runs on Vanta | explicit | 0.9 | https://trust.attio.com/ | Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source) |
