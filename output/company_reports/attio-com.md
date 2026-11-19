# Attio — Sprinto Signal Engine research report

*Domain:* `attio.com` · *Generated:* 2026-11-03 15:49 · *Extraction:* deterministic fallback — rule-based, not AI-verified

## Decision

**QUALIFIED** → recommended action: **outreach**

| Dimension | Value |
|---|---|
| ICP fit | 56/100 |
| Buying timing | 34/100 |
| Evidence confidence | 0.75 |
| Secondary research | 1 round(s) |

- Evidence Map → QUALIFY: SaaS, in the growth band, and preparing for an audit — all backed by cited evidence.
- Scores: ICP 56/100, timing 34/100, evidence confidence 0.75.
- Biggest ICP drivers: SaaS business model (22.5/25) — SaaS model supported by 8 indicator(s).; Relevant growth stage (Series A–C) (15/15) — Explicit Series C — inside Sprinto's sweet spot.
- Biggest timing drivers: Security or compliance hiring (16.9/20) — 1 security/compliance role(s) open; 4 engineering role signal(s).; Trust centre or compliance activity (10/10) — Trust centre published.
- Extraction ran in deterministic fallback mode (Claude not used); confidence capped at 0.75. Results are rule-based, not AI-verified.

### Evidence Map → **QUALIFY**

| Question (core in bold) | Answer | Basis | Pages read / budget | If unanswered | Evidence |
|---|---|---|---|---|---|
| **Is it a SaaS business?** | YES | Subscription-software indicators found (pricing/trial/login/API). | 1/3 | Flag at review gate | "New VP Sales from enterprise SaaS" — https://attio.com/<br>"Start for free" — https://attio.com/ |
| **Is it Series A–C / 50–200 employees?** | YES | Inside the Series A–C / 50–200 employee band (Series C, 190+ team members). | 2/3 | Flag at review gate | "Raised $125M Series C" — https://attio.com/<br>"190+ team members." — https://attio.com/about |
| **Is it preparing for an audit (SOC 2 / ISO 27001)?** | YES | Audit work, compliance hiring or security-review pressure observed. | 3/4 | Nurture (right company, wrong time) | "JOB: Security Engineering Lead" — https://attio.com/careers |
| Does it have >50 clients / larger customers? | YES | Customer base of meaningful size / named larger customers. | 3/2 | Neutral | "Trusted by 30,000+ customers." — https://attio.com/ |
| Does it serve a regulated industry? | UNKNOWN | Customer industries not identified as regulated. | 1/1 | Neutral | — |
| Is it on AWS / GCP / Azure? | UNKNOWN | Cloud provider not stated. | 2/2 | Neutral | — |

## 1. Website intelligence

Scraping status: **partial** · pages read: 8 of 9 attempted

| Type | Status | URL | Fetched via |
|---|---|---|---|
| homepage | ok | https://attio.com/ | requests |
| about | ok | https://attio.com/about | requests |
| security | ok | https://attio.com/security | requests |
| trust | ok | https://trust.attio.com/ | requests |
| customers | ok | https://attio.com/customers | requests |
| compliance | not_found | https://attio.com/compliance | requests |
| legal | ok | https://attio.com/privacy-preferences | requests |
| careers | ok | https://attio.com/careers | requests |
| customers | ok | https://attio.com/customers/modal | requests |

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
| Open security/compliance role: Security Engineering Lead | 0.85 | no | Hiring for security or compliance shows the company is building the function now; new owners typically choose tooling in their first months. | "JOB: Security Engineering Lead" — https://attio.com/careers |
| Trust centre page is live | 0.85 | no | A trust centre signals that customers are actively asking for security documentation during deals. | "Attio Trust Center" — https://trust.attio.com/ |
| Funding announcement: Raised $125M Series C | 0.85 | no | A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it. | "Raised $125M Series C" — https://attio.com/ |
| Open engineering role: Senior Platform Engineer | 0.75 | no | A growing engineering team multiplies the systems, access and change-management evidence an auditor will ask for. | "JOB: Senior Platform Engineer" — https://attio.com/careers |
| Customer stories page exists: Customers \| Attio | 0.6 | no | Named larger customers suggest the company is already exposed to enterprise security requirements. | "Discover how thousands of companies use Attio to scale their business." — https://attio.com/customers |

**Missing information:** Any SOC 2 / ISO 27001 / GDPR status

## 3. Qualification scoring

### ICP fit

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| SaaS business model | 22.5/25 | SaaS model supported by 8 indicator(s). | 8549084bff, 363b00a68e, 1e938472fe, 2e512dfc5f, cae74f4992, 572c7bd359, 5541433d8f, 46f2433c77 |
| Relevant growth stage (Series A–C) | 15/15 | Explicit Series C — inside Sprinto's sweet spot. | 950dd2cfe3, af49a70815 |
| Enterprise customer orientation | 8.9/20 | 2 enterprise reference(s) / enterprise-tier signals. | 7468d1a24f, 5c78683444 |
| Relevant customer industry | 0/10 | Customer industries not identified. |  |
| Company scaling signals | 10/10 | 4 scaling signal(s) (hiring, expansion, funding). | 9b03975d25, af4e01a655, f082c9450a, a21f5a0262 |
| Security / compliance complexity | 0/20 | No security/compliance content observed. |  |

### Buying timing

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| Explicit SOC 2 / ISO 27001 / audit requirement | 0/30 | No explicit audit or certification requirement observed. |  |
| Enterprise security review / procurement pressure | 0/25 | No security-review pressure observed. |  |
| Security or compliance hiring | 16.9/20 | 1 security/compliance role(s) open; 4 engineering role signal(s). | be535ca80d, 9b03975d25, af4e01a655, f082c9450a, a21f5a0262 |
| Trust centre or compliance activity | 10/10 | Trust centre published. | 6266911d73, 1d4338cc38 |
| Recent enterprise expansion / scaling | 6.8/15 | 1 expansion / funding signal(s). | 950dd2cfe3 |

### Research agent log

**Round 1** — open questions: What is its SOC 2 / ISO 27001 / GDPR status?; Is it hiring for security, compliance or engineering?; Is there any evidence compliance matters right now?

- Targeted: https://attio.com/compliance [compliance] — What is its SOC 2 / ISO 27001 / GDPR status?
- Targeted: https://attio.com/privacy-preferences [legal] — What is its SOC 2 / ISO 27001 / GDPR status?
- Targeted: https://attio.com/careers [careers] — Is it hiring for security, compliance or engineering?, Is there any evidence compliance matters right now?
- Targeted: https://attio.com/customers/modal [customers] — Is there any evidence compliance matters right now?
- Readable: 3 page(s)
- New: Customer login to a hosted product (https://attio.com/privacy-preferences)
- New: Product integrations (https://attio.com/customers/modal)
- New: Open security/compliance role: Security Engineering Lead (https://attio.com/careers)
- New: Open engineering role: Senior Platform Engineer (https://attio.com/careers)
- New: Open engineering role: Senior Product Engineer [Backend] (https://attio.com/careers)
- New: Open engineering role: Staff Product Engineer (https://attio.com/careers)
- New: Open engineering role: Solutions Engineer [Pre and Post-Sales] - Mid-Market (https://attio.com/careers)
- **What changed:** ICP 46→56, timing 17→34, decision not_qualified→qualified. 7 new evidence item(s).

- Stopped before round 2: Decision already well supported.

## 4. Decision-maker

Status: **selected** · providers tried: Manual mapping (Apollo / research), Company website (team page)

- Hunter.io skipped: HUNTER_API_KEY not set.
- Manual mapping returned 1 contact(s)
- Company website listed 0 named leader(s)

Alexander Christie, CTO & Co-founder (relevance 67.0): CTO: accountable for technical controls and usually sponsors the first SOC 2. A security function exists, so the CTO is one step removed from day-to-day compliance. No email address available — reachable only after manual verification. Email not yet verified — the test preview will show the prospect address as unavailable.

| Name | Title | Email | Source | Source URL |
|---|---|---|---|---|
| Alexander Christie | CTO & Co-founder | not available | attio.com engineering blog byline | https://attio.com/engineering/blog/introducing-universal-context |

## 5. Pain points

**Standing up a compliance programme before a dedicated security team exists** — observed, confidence 0.8

Attio is growing (Security Engineering Lead) and no dedicated security lead is visible; until one exists, compliance work usually falls to the CTO & Co-founder.

- "JOB: Security Engineering Lead" — https://attio.com/careers
- "Raised $125M Series C" — https://attio.com/

**Security questionnaires and vendor reviews slowing enterprise deals** — inferred, confidence 0.75

The site points to an enterprise motion (Trust centre page is live); enterprise buyers send security questionnaires that usually land with the CTO & Co-founder.

- "Attio Trust Center" — https://trust.attio.com/
- "Attio Trust Center" — https://attio.com/security
- "Discover how thousands of companies use Attio to scale their business." — https://attio.com/customers

## 6. Generated email

**Subject:** the security hire at Attio  
*Candidates:* the security hire at Attio / Attio and SOC 2 / question on the security hire — Chosen for specificity to the observed signal and brevity (score 4 vs 4, 3).

```
Hi Alexander,

Noticed you're hiring for a Security Engineering Lead. Teams at that point often find the new hire spends their first months chasing evidence rather than improving security.

Is compliance sitting with you until that security hire lands?

Sprinto automates evidence collection and continuous control monitoring for SOC 2, ISO 27001 and GDPR, so audit prep stops being a side project for engineering. If it's relevant, would a 20-minute conversation be useful?

Best,
Sprinto Growth Team
```

Word count: 71 · quality checks: length_60_110_words=pass, greets_by_first_name=pass, hook_is_grounded_in_evidence=pass, no_banned_phrases=pass, no_exclamation_marks=pass, single_cta=pass, no_unsupported_sprinto_claims=pass

### Evidence → email trace

| Sentence | Purpose | Evidence | Source |
|---|---|---|---|
| Noticed you're hiring for a Security Engineering Lead. | Website observation (hook) | JOB: Security Engineering Lead | https://attio.com/careers |
| Teams at that point often find the new hire spends their first months chasing evidence rather than improving security. | Business implication of the observation | Hiring for security or compliance shows the company is building the function now; new owners typically choose tooling in | https://attio.com/careers |
| Is compliance sitting with you until that security hire lands? | Role-specific challenge (observed) | "JOB: Security Engineering Lead" — https://attio.com/careers; "Raised $125M Series C" — https://attio.com/ | https://attio.com/careers |
| Sprinto automates evidence collection and continuous control monitoring for SOC 2, ISO 27001 and GDPR, so audit prep stops being a side project for engineering. | Relevant Sprinto value proposition (core product, no extra claims) |  |  |
| If it's relevant, would a 20-minute conversation be useful? | Single low-pressure CTA |  |  |

## 7. Dispatch

Status: **pending_review** — Waiting for a human at the review gate.
Preview file: `/Users/anishasarkar/sprinto-case-study/sprinto-signal-engine/output/review/attio-com.txt`

## Decision ledger

### WHY THIS COMPANY?

- SaaS business model +22.5/25: SaaS model supported by 8 indicator(s). [8549084bff] "New VP Sales from enterprise SaaS" (https://attio.com/); [363b00a68e] "Start for free" (https://attio.com/)
- Relevant growth stage (Series A–C) +15/15: Explicit Series C — inside Sprinto's sweet spot. [950dd2cfe3] "Raised $125M Series C" (https://attio.com/); [af49a70815] "190+ team members." (https://attio.com/about)
- Enterprise customer orientation +8.9/20: 2 enterprise reference(s) / enterprise-tier signals. [7468d1a24f] "Trusted by 30,000+ customers." (https://attio.com/); [5c78683444] "Discover how thousands of companies use Attio to scale their business." (https://attio.com/customers)
- Company scaling signals +10/10: 4 scaling signal(s) (hiring, expansion, funding). [9b03975d25] "JOB: Senior Platform Engineer" (https://attio.com/careers); [af4e01a655] "JOB: Senior Product Engineer [Backend]" (https://attio.com/careers)

### WHY NOW?

- Security or compliance hiring +16.9/20: 1 security/compliance role(s) open; 4 engineering role signal(s). [be535ca80d] "JOB: Security Engineering Lead" (https://attio.com/careers); [9b03975d25] "JOB: Senior Platform Engineer" (https://attio.com/careers)
- Trust centre or compliance activity +10/10: Trust centre published. [6266911d73] "Attio Trust Center" (https://trust.attio.com/); [1d4338cc38] "Attio Trust Center" (https://attio.com/security)
- Recent enterprise expansion / scaling +6.8/15: 1 expansion / funding signal(s). [950dd2cfe3] "Raised $125M Series C" (https://attio.com/)
- Buying moment — Open security/compliance role: Security Engineering Lead: Hiring for security or compliance shows the company is building the function now; new owners typically choose tooling in their first months. (https://attio.com/careers)
- Buying moment — Trust centre page is live: A trust centre signals that customers are actively asking for security documentation during deals. (https://trust.attio.com/)
- Buying moment — Funding announcement: Raised $125M Series C: A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it. (https://attio.com/)

### WHY THIS PERSON?

- Alexander Christie, CTO & Co-founder (relevance 67.0): CTO: accountable for technical controls and usually sponsors the first SOC 2. A security function exists, so the CTO is one step removed from day-to-day compliance. No email address available — reachable only after manual verification. Email not yet verified — the test preview will show the prospect address as unavailable.

### WHY THIS PAIN POINT?

- Standing up a compliance programme before a dedicated security team exists [observed, confidence 0.8]: Attio is growing (Security Engineering Lead) and no dedicated security lead is visible; until one exists, compliance work usually falls to the CTO & Co-founder. Evidence: "JOB: Security Engineering Lead" — https://attio.com/careers | "Raised $125M Series C" — https://attio.com/
- Security questionnaires and vendor reviews slowing enterprise deals [inferred, confidence 0.75]: The site points to an enterprise motion (Trust centre page is live); enterprise buyers send security questionnaires that usually land with the CTO & Co-founder. Evidence: "Attio Trust Center" — https://trust.attio.com/ | "Attio Trust Center" — https://attio.com/security

### WHY THIS EMAIL?

- Hook: you're hiring for a Security Engineering Lead (https://attio.com/careers)
- Pain point used: Standing up a compliance programme before a dedicated security team exists
- Open security/compliance role: Security Engineering Lead (https://attio.com/careers) suggests hiring for security or compliance shows the company is building the function now; new owners typically choose tooling in their first months. Alexander Christie (CTO & Co-founder) is the likely owner of 'Standing up a compliance programme before a dedicated security team exists'.

### WHAT COULD MAKE THIS DECISION WRONG?

- 5 of 20 evidence items are inferred rather than explicitly stated.
- Unknown: Any SOC 2 / ISO 27001 / GDPR status.
- Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).

## Evidence appendix

| ID | Category | Finding | Type | Conf. | URL | Excerpt |
|---|---|---|---|---|---|---|
| e132b32a58 | other | Business description (homepage / meta description) | explicit | 0.7 | https://attio.com/ | The system for revenue teams to build pipeline, accelerate deals, and grow accounts around the clock. |
| 8549084bff | saas_indicator | Describes itself as SaaS | explicit | 0.6 | https://attio.com/ | New VP Sales from enterprise SaaS |
| 363b00a68e | saas_indicator | Self-serve free trial / sign-up | explicit | 0.6 | https://attio.com/ | Start for free |
| 1e938472fe | saas_indicator | Product demo / sales-led motion | explicit | 0.6 | https://attio.com/ | Talk to sales |
| 2e512dfc5f | saas_indicator | Customer login to a hosted product | explicit | 0.6 | https://attio.com/privacy-preferences | Because we do not ask you to sign in to make this choice (we store it in a cookie on this browser), you will need to make it again on another browser or device, or if you clear your cookies. |
| cae74f4992 | saas_indicator | Developer API | inferred | 0.4 | https://attio.com/ | Joshua to send documentation on the public API |
| 572c7bd359 | saas_indicator | Product integrations | inferred | 0.4 | https://attio.com/customers/modal | Integrations |
| 5541433d8f | saas_indicator | Platform positioning | inferred | 0.4 | https://attio.com/ | Attio is the platform that builds pipeline, advances deals, and grows accounts around the clock. |
| 46f2433c77 | saas_indicator | Workflow / automation product | inferred | 0.4 | https://attio.com/ | It covers the workflow automations you flagged. |
| 7468d1a24f | enterprise_customer | Customer reference: Trusted by 30,000+ customers | inferred | 0.55 | https://attio.com/ | Trusted by 30,000+ customers. |
| 5c78683444 | enterprise_customer | Customer stories page exists: Customers \| Attio | explicit | 0.6 | https://attio.com/customers | Discover how thousands of companies use Attio to scale their business. |
| af49a70815 | other | Headcount mention: 190+ team members | explicit | 0.7 | https://attio.com/about | 190+ team members. |
| 950dd2cfe3 | funding | Funding announcement: Raised $125M Series C | explicit | 0.85 | https://attio.com/ | Raised $125M Series C |
| 6266911d73 | trust_centre | Trust centre page is live | explicit | 0.85 | https://trust.attio.com/ | Attio Trust Center |
| 1d4338cc38 | trust_centre | References a Trust Center | explicit | 0.7 | https://attio.com/security | Attio Trust Center |
| be535ca80d | compliance_hiring | Open security/compliance role: Security Engineering Lead | explicit | 0.85 | https://attio.com/careers | JOB: Security Engineering Lead |
| 9b03975d25 | engineering_hiring | Open engineering role: Senior Platform Engineer | explicit | 0.75 | https://attio.com/careers | JOB: Senior Platform Engineer |
| af4e01a655 | engineering_hiring | Open engineering role: Senior Product Engineer [Backend] | explicit | 0.75 | https://attio.com/careers | JOB: Senior Product Engineer [Backend] |
| f082c9450a | engineering_hiring | Open engineering role: Staff Product Engineer | explicit | 0.75 | https://attio.com/careers | JOB: Staff Product Engineer |
| a21f5a0262 | engineering_hiring | Open engineering role: Solutions Engineer [Pre and Post-Sales] - Mid-Market | explicit | 0.75 | https://attio.com/careers | JOB: Solutions Engineer [Pre and Post-Sales] - Mid-Market |
