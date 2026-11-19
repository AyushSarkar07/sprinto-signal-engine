# incident.io — Sprinto Signal Engine research report

*Domain:* `incident.io` · *Generated:* 2026-11-03 15:49 · *Extraction:* deterministic fallback — rule-based, not AI-verified

## Decision

**NOT_QUALIFIED** → recommended action: **nurture**

| Dimension | Value |
|---|---|
| ICP fit | 68/100 |
| Buying timing | 15/100 |
| Evidence confidence | 0.74 |
| Secondary research | 2 round(s) |

- Evidence Map → NURTURE: ICP fit, but 'Is it preparing for an audit (SOC 2 / ISO 27001)?' stayed unanswered after research — right company, wrong time → nurture.
- Scores: ICP 68/100, timing 15/100, evidence confidence 0.74.
- Biggest ICP drivers: SaaS business model (22.5/25) — SaaS model supported by 6 indicator(s).; Enterprise customer orientation (15.8/20) — 4 enterprise reference(s) / enterprise-tier signals.
- Biggest timing drivers: Explicit SOC 2 / ISO 27001 / audit requirement (17/30) — Certification already held — renewal and multi-framework expansion, not a first audit.; Trust centre or compliance activity (8.2/10) — Trust centre published.
- Extraction ran in deterministic fallback mode (Claude not used); confidence capped at 0.75. Results are rule-based, not AI-verified.

### Evidence Map → **NURTURE**

| Question (core in bold) | Answer | Basis | Pages read / budget | If unanswered | Evidence |
|---|---|---|---|---|---|
| **Is it a SaaS business?** | YES | Subscription-software indicators found (pricing/trial/login/API). | 1/3 | Flag at review gate | "something we shipped for them whilst on a train to Marseille for a company offsite! This responsiveness showed alignment with Intercom's nee" — https://incident.io/customers/fin<br>"Get started for free" — https://incident.io/ |
| **Is it Series A–C / 50–200 employees?** | YES | Inside the Series A–C / 50–200 employee band (200+ people). | 2/3 | Flag at review gate | "200+ people across NY, SF and London" — https://incident.io/careers |
| **Is it preparing for an audit (SOC 2 / ISO 27001)?** | UNKNOWN | Weak or unread audit signals (timing 15/100, 2 relevant page(s) read). | 2/4 | Nurture (right company, wrong time) | — |
| Does it have >50 clients / larger customers? | YES | Customer base of meaningful size / named larger customers. | 4/2 | Neutral | "Trusted by industry leaders" — https://incident.io/customers<br>"Why we’re loved by users and easily adopted" — https://incident.io/customers/fin |
| Does it serve a regulated industry? | YES | Serves regulated buyers: financial services. | 2/1 | Neutral | "I've even gotten teams like payments, member support, trust and safety, and security interested, too,” says Jeremy." — https://incident.io/customers/etsy |
| Is it on AWS / GCP / Azure? | UNKNOWN | Cloud provider not stated. | 2/2 | Neutral | — |

## 1. Website intelligence

Scraping status: **partial** · pages read: 8 of 9 attempted

| Type | Status | URL | Fetched via |
|---|---|---|---|
| homepage | ok | https://incident.io/ | requests |
| about | ok | https://incident.io/incident-response-microsoft-teams | requests |
| security | ok | https://incident.io/security | requests |
| trust | not_found | https://incident.io/trust | requests |
| customers | ok | https://incident.io/customers | requests |
| news | ok | https://incident.io/blog | requests |
| careers | ok | https://incident.io/careers | requests |
| customers | ok | https://incident.io/customers/fin | requests |
| customers | ok | https://incident.io/customers/etsy | requests |

Errors: https://incident.io/trust: not_found

## 2. Extracted company profile

| Field | Value |
|---|---|
| Business | incident.io is a software reliability platform unifying on-call, agentic root cause analysis, incident response, and status pages – helping teams resolve issues |
| SaaS? | True (B2B SaaS (rule-based assessment)) |
| Funding stage | not stated |
| Headcount | 200+ people |
| Industries | financial services |
| Tech stack (explicit only) | none stated |
| Trust centre | True |

### Buying moments

| Signal | Conf. | Needs research | Why it matters commercially | Evidence |
|---|---|---|---|---|
| Mentions SOC 2 Type I — appears to be held | 0.8 | no | An existing certification must be renewed every year and usually expands to further frameworks as the customer base grows; continuous compliance becomes the ongoing cost. | "We're SOC 2 Type I & II and GDPR compliant to ensure your data stays safe." — https://incident.io/security |
| References a trust center | 0.7 | no | A trust centre signals that customers are actively asking for security documentation during deals. | "Visit the trust center" — https://incident.io/security |
| Customer stories page exists: Customers \| incident.io | 0.6 | no | Named larger customers suggest the company is already exposed to enterprise security requirements. | "We're proud to be working with some incredible companies, empowering them with world-class incident response. Read our c" — https://incident.io/customers |
| Serves or targets financial services | 0.55 | yes | Customers in regulated industries (finance, healthcare, public sector) routinely require formal attestations from vendors. | "I've even gotten teams like payments, member support, trust and safety, and security interested, too,” says Jeremy." — https://incident.io/customers/etsy |

**Missing information:** Security, compliance or engineering hiring activity

## 3. Qualification scoring

### ICP fit

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| SaaS business model | 22.5/25 | SaaS model supported by 6 indicator(s). | 71e4866cff, 081a3ff82e, d0086179a5, cd7894810b, f5e5576794, a386aac79e |
| Relevant growth stage (Series A–C) | 7/15 | No funding stage stated; headcount mention ('200+ people') used as a weak proxy. | 6d5ebb4cef |
| Enterprise customer orientation | 15.8/20 | 4 enterprise reference(s) / enterprise-tier signals. | 7b81626994, 58197f3299, 012a6da66e, 72d1b645a1 |
| Relevant customer industry | 10/10 | Serves regulated industries: financial services | 10b3b23746 |
| Company scaling signals | 0/10 | No scaling signals observed. |  |
| Security / compliance complexity | 13/20 | 4 security/compliance artefact(s) on the site. | 2427b61ace, b9d8554ab3, e66e6051a1, aa4d5b1501 |

### Buying timing

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| Explicit SOC 2 / ISO 27001 / audit requirement | 17/30 | Certification already held — renewal and multi-framework expansion, not a first audit. | aa4d5b1501 |
| Enterprise security review / procurement pressure | 0/25 | No security-review pressure observed. |  |
| Security or compliance hiring | 0/20 | No security roles found. |  |
| Trust centre or compliance activity | 8.2/10 | Trust centre published. | d959812696 |
| Recent enterprise expansion / scaling | 0/15 | No recent expansion signal. |  |

Penalties: -10 timing: compliance platform already visible (Vanta) — this is a displacement, not a greenfield, conversation.

### Research agent log

**Round 1** — open questions: What stage / size is the company?; Is it hiring for security, compliance or engineering?; Is there any evidence compliance matters right now?

- Targeted: https://incident.io/blog [news] — What stage / size is the company?, Is there any evidence compliance matters right now?
- Targeted: https://incident.io/careers [careers] — What stage / size is the company?, Is it hiring for security, compliance or engineering?, Is there any evidence compliance matters right now?
- Targeted: https://incident.io/customers/fin [customers] — Is there any evidence compliance matters right now?
- Readable: 3 page(s)
- New: Describes itself as SaaS (https://incident.io/customers/fin)
- New: Customer reference: loved by users and easily adopted (https://incident.io/customers/fin)
- New: Headcount mention: 200+
people (https://incident.io/careers)
- **What changed:** ICP 44→55, timing 15→15, decision insufficient_data→not_qualified. 3 new evidence item(s).

**Round 2** — open questions: Is it hiring for security, compliance or engineering?; Is there any evidence compliance matters right now?

- Targeted: https://incident.io/customers/etsy [customers] — Is there any evidence compliance matters right now?
- Readable: 1 page(s)
- New: Customer reference: loved by users and easily adopted (https://incident.io/customers/etsy)
- New: Serves or targets financial services (https://incident.io/customers/etsy)
- **What changed:** ICP 55→68, timing 15→15, decision not_qualified→not_qualified. 2 new evidence item(s).


## 4. Decision-maker

Not attempted (company not qualified).

## Decision ledger

### WHY THIS COMPANY?

- SaaS business model +22.5/25: SaaS model supported by 6 indicator(s). [71e4866cff] "something we shipped for them whilst on a train to Marseille for a company offsite! This responsiveness showed" (https://incident.io/customers/fin); [081a3ff82e] "Get started for free" (https://incident.io/)
- Relevant growth stage (Series A–C) +7/15: No funding stage stated; headcount mention ('200+ people') used as a weak proxy. [6d5ebb4cef] "200+ people across NY, SF and London" (https://incident.io/careers)
- Enterprise customer orientation +15.8/20: 4 enterprise reference(s) / enterprise-tier signals. [7b81626994] "Trusted by industry leaders" (https://incident.io/customers); [58197f3299] "Why we’re loved by users and easily adopted" (https://incident.io/customers/fin)
- Relevant customer industry +10/10: Serves regulated industries: financial services [10b3b23746] "I've even gotten teams like payments, member support, trust and safety, and security interested, too,” says Je" (https://incident.io/customers/etsy)
- Security / compliance complexity +13/20: 4 security/compliance artefact(s) on the site. [2427b61ace] "Vulnerability Disclosure Policy" (https://incident.io/security); [b9d8554ab3] "We encrypt your data using AES-256, the gold standard in encryption technology and safeguard passwords using a" (https://incident.io/security)

### WHY NOW?

- Explicit SOC 2 / ISO 27001 / audit requirement +17/30: Certification already held — renewal and multi-framework expansion, not a first audit. [aa4d5b1501] "We're SOC 2 Type I & II and GDPR compliant to ensure your data stays safe." (https://incident.io/security)
- Trust centre or compliance activity +8.2/10: Trust centre published. [d959812696] "Visit the trust center" (https://incident.io/security)
- Buying moment — Mentions SOC 2 Type I — appears to be held: An existing certification must be renewed every year and usually expands to further frameworks as the customer base grows; continuous compliance becomes the ongoing cost. (https://incident.io/security)
- Buying moment — References a trust center: A trust centre signals that customers are actively asking for security documentation during deals. (https://incident.io/security)
- Buying moment — Customer stories page exists: Customers | incident.io: Named larger customers suggest the company is already exposed to enterprise security requirements. (https://incident.io/customers)

### WHAT COULD MAKE THIS DECISION WRONG?

- 7 of 19 evidence items are inferred rather than explicitly stated.
- Unknown: Security, compliance or engineering hiring activity.
- A compliance automation vendor already appears on the site; switching costs may block a deal.
- Company already holds SOC 2 — the conversation is about continuous compliance / extra frameworks, not a first audit.
- Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).
- -10 timing: compliance platform already visible (Vanta) — this is a displacement, not a greenfield, conversation.

## Evidence appendix

| ID | Category | Finding | Type | Conf. | URL | Excerpt |
|---|---|---|---|---|---|---|
| ec72550ac2 | other | Business description (homepage / meta description) | explicit | 0.7 | https://incident.io/ | incident.io is a software reliability platform unifying on-call, agentic root cause analysis, incident response, and status pages – helping teams resolve issues faster. |
| 71e4866cff | saas_indicator | Describes itself as SaaS | explicit | 0.6 | https://incident.io/customers/fin | something we shipped for them whilst on a train to Marseille for a company offsite! This responsiveness showed alignment with Intercom's needs as a fast-moving SaaS company, further strengthening thei |
| 081a3ff82e | saas_indicator | Self-serve free trial / sign-up | explicit | 0.6 | https://incident.io/ | Get started for free |
| d0086179a5 | saas_indicator | Product demo / sales-led motion | explicit | 0.6 | https://incident.io/ | Get a demo |
| cd7894810b | saas_indicator | Product integrations | inferred | 0.4 | https://incident.io/ | Integrations |
| f5e5576794 | saas_indicator | Platform positioning | inferred | 0.4 | https://incident.io/ | incident.io is a software reliability platform unifying on-call, agentic root cause analysis, incident response, and status pages – helping teams resolve issues faster. |
| a386aac79e | saas_indicator | Workflow / automation product | inferred | 0.4 | https://incident.io/ | Workflows |
| 7b81626994 | enterprise_customer | Customer reference: Trusted by industry leaders | inferred | 0.55 | https://incident.io/customers | Trusted by industry leaders |
| 58197f3299 | enterprise_customer | Customer reference: loved by users and easily adopted | inferred | 0.55 | https://incident.io/customers/fin | Why we’re loved by users and easily adopted |
| 012a6da66e | enterprise_customer | Customer reference: loved by users and easily adopted | inferred | 0.55 | https://incident.io/customers/etsy | Why we’re loved by users and easily adopted |
| 72d1b645a1 | enterprise_customer | Customer stories page exists: Customers \| incident.io | explicit | 0.6 | https://incident.io/customers | We're proud to be working with some incredible companies, empowering them with world-class incident response. Read our customer stories to find out more about how we've helped them. |
| 10b3b23746 | regulated_industry | Serves or targets financial services | inferred | 0.55 | https://incident.io/customers/etsy | I've even gotten teams like payments, member support, trust and safety, and security interested, too,” says Jeremy. |
| 6d5ebb4cef | other | Headcount mention: 200+ people | explicit | 0.7 | https://incident.io/careers | 200+ people across NY, SF and London |
| aa4d5b1501 | certification_held | Mentions SOC 2 Type I — appears to be held | explicit | 0.8 | https://incident.io/security | We're SOC 2 Type I & II and GDPR compliant to ensure your data stays safe. |
| e66e6051a1 | compliance_mention | Mentions GDPR | explicit | 0.6 | https://incident.io/security | We're SOC 2 Type I & II and GDPR compliant to ensure your data stays safe. |
| 2427b61ace | security_page | Security control described: Vulnerability Disclosure | explicit | 0.6 | https://incident.io/security | Vulnerability Disclosure Policy |
| b9d8554ab3 | security_page | Security control described: AES-256 | explicit | 0.6 | https://incident.io/security | We encrypt your data using AES-256, the gold standard in encryption technology and safeguard passwords using a secure cryptographic one-way hash function (SHA-256). |
| d959812696 | trust_centre | References a trust center | explicit | 0.7 | https://incident.io/security | Visit the trust center |
| f0495dfe7a | competitor_platform | Compliance platform detected: Vanta | explicit | 0.8 | https://incident.io/ | Link to https://incident.io/customers/vanta |
