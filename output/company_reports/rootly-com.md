# Rootly — Sprinto Signal Engine research report

*Domain:* `rootly.com` · *Generated:* 2026-11-03 15:49 · *Extraction:* deterministic fallback — rule-based, not AI-verified

## Decision

**QUALIFIED** → recommended action: **outreach**

| Dimension | Value |
|---|---|
| ICP fit | 80/100 |
| Buying timing | 39/100 |
| Evidence confidence | 0.74 |
| Secondary research | 1 round(s) |

- Evidence Map → QUALIFY: SaaS, in the growth band, and preparing for an audit — all backed by cited evidence.
- Scores: ICP 80/100, timing 39/100, evidence confidence 0.74.
- Biggest ICP drivers: SaaS business model (22.5/25) — SaaS model supported by 6 indicator(s).; Enterprise customer orientation (20/20) — 4 enterprise reference(s) / enterprise-tier signals.
- Biggest timing drivers: Explicit SOC 2 / ISO 27001 / audit requirement (19/30) — Certification already held — renewal and multi-framework expansion, not a first audit.; Enterprise security review / procurement pressure (8.4/25) — 1 reference(s) to security reviews, DPAs or procurement.
- Extraction ran in deterministic fallback mode (Claude not used); confidence capped at 0.75. Results are rule-based, not AI-verified.

### Evidence Map → **QUALIFY**

| Question (core in bold) | Answer | Basis | Pages read / budget | If unanswered | Evidence |
|---|---|---|---|---|---|
| **Is it a SaaS business?** | YES | Subscription-software indicators found (pricing/trial/login/API). | 1/3 | Flag at review gate | "Get started for free" — https://rootly.com/<br>"Book a demo" — https://rootly.com/ |
| **Is it Series A–C / 50–200 employees?** | YES | Inside the Series A–C / 50–200 employee band (Series A, 92 employees). | 2/3 | Flag at review gate | "Latest funding: Series A round (2023-08)." — enrichment://apollo.io/rootly.com<br>"Headcount: 92 employees." — enrichment://apollo.io/rootly.com |
| **Is it preparing for an audit (SOC 2 / ISO 27001)?** | YES | Audit work, compliance hiring or security-review pressure observed. | 3/4 | Nurture (right company, wrong time) | "Start your security review" — https://security.rootly.com/ |
| Does it have >50 clients / larger customers? | YES | Customer base of meaningful size / named larger customers. | 3/2 | Neutral | "Loved by fast-growing startups and the Fortune 500." — https://rootly.com/<br>"See how teams from the Fortune 100 to fast-growing startups use Rootly for incident response, on-call, retrospectives, and AI SRE." — https://rootly.com/customers |
| Does it serve a regulated industry? | YES | Serves regulated buyers: financial services, healthcare. | 2/1 | Neutral | "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." — https://rootly.com/security<br>"Cyber Insurance" — https://security.rootly.com/ |
| Is it on AWS / GCP / Azure? | YES | AWS in the technologies list of Apollo.io company record for rootly.com. | 3/2 | Neutral | "Technologies detected: Amazon AWS" — enrichment://apollo.io/rootly.com |

## 1. Website intelligence

Scraping status: **partial** · pages read: 9 of 10 attempted

| Type | Status | URL | Fetched via |
|---|---|---|---|
| homepage | ok | https://rootly.com/ | requests |
| about | ok | https://rootly.com/about | requests |
| security | ok | https://rootly.com/security | requests |
| trust | access_restricted | https://rootly.com/trust | requests |
| customers | ok | https://rootly.com/customers | requests |
| enrichment | ok | enrichment://apollo.io/rootly.com | requests |
| careers | ok | https://rootly.com/careers | requests |
| security | ok | https://security.rootly.com/ | requests |
| customers | ok | https://rootly.com/customers/capa | requests |
| news | ok | https://rootly.com/blog | requests |

Errors: https://rootly.com/trust: access_restricted

## 2. Extracted company profile

| Field | Value |
|---|---|
| Business | The all-in-one AI incident management platform for fast-moving engineering teams to detect, manage, resolve, and learn from incidents faster. |
| SaaS? | True (B2B SaaS (rule-based assessment)) |
| Funding stage | Series A |
| Headcount | 92 employees |
| Industries | healthcare, financial services |
| Tech stack (explicit only) | none stated |
| Trust centre | True |

### Buying moments

| Signal | Conf. | Needs research | Why it matters commercially | Evidence |
|---|---|---|---|---|
| Mentions SOC2 — appears to be held | 0.8 | no | An existing certification must be renewed every year and usually expands to further frameworks as the customer base grows; continuous compliance becomes the ongoing cost. | "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." — https://rootly.com/security |
| References a Trust Center | 0.7 | no | A trust centre signals that customers are actively asking for security documentation during deals. | "Rootly Trust Center \| Powered by SafeBase" — https://security.rootly.com/ |
| Security review / procurement process: security review | 0.7 | no | References to security questionnaires, DPAs or procurement suggest deals already pass through vendor security review. | "Start your security review" — https://security.rootly.com/ |
| Enterprise orientation: Fortune 500 | 0.65 | no | Selling to enterprises almost always triggers SOC 2 / ISO 27001 requests in procurement. | "Loved by fast-growing startups and the Fortune 500." — https://rootly.com/ |
| Customer stories page exists: Rootly \| Customer Stories | 0.6 | no | Named larger customers suggest the company is already exposed to enterprise security requirements. | "See how teams from the Fortune 100 to fast-growing startups use Rootly for incident response, on-call, retrospectives, a" — https://rootly.com/customers |
| Serves or targets healthcare | 0.55 | yes | Customers in regulated industries (finance, healthcare, public sector) routinely require formal attestations from vendors. | "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." — https://rootly.com/security |
| Funding announcement: Series A round | 0.42 | yes | A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it. | "Latest funding: Series A round (2023-08)." — enrichment://apollo.io/rootly.com |

**Missing information:** Security, compliance or engineering hiring activity

## 3. Qualification scoring

### ICP fit

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| SaaS business model | 22.5/25 | SaaS model supported by 6 indicator(s). | bcc558f5e9, 135ee99d81, afca70acf5, 51888a39c4, 44d4738607, df09c930b5 |
| Relevant growth stage (Series A–C) | 7.4/15 | Explicit Series A — inside Sprinto's sweet spot. | 9ea8ee1ab8, 4a0c2560a1 |
| Enterprise customer orientation | 20/20 | 4 enterprise reference(s) / enterprise-tier signals. | eab89c40bb, 0b501829d6, 056bf5ac60, 399039550a |
| Relevant customer industry | 10/10 | Serves regulated industries: healthcare, financial services | 562dba2ff5, ed254e56dd |
| Company scaling signals | 0/10 | No scaling signals observed. |  |
| Security / compliance complexity | 20/20 | 7 security/compliance artefact(s) on the site. | 76a871df87, 9e8083a358, 16ae7060f6, 861e451534, 1ebf0e9702, 4260150cd6, 4f69184f9d |

### Buying timing

| Criterion | Points | Rationale | Evidence IDs |
|---|---|---|---|
| Explicit SOC 2 / ISO 27001 / audit requirement | 19/30 | Certification already held — renewal and multi-framework expansion, not a first audit. | 1ebf0e9702, 4260150cd6, 4f69184f9d |
| Enterprise security review / procurement pressure | 8.4/25 | 1 reference(s) to security reviews, DPAs or procurement. | 00b1c9de87 |
| Security or compliance hiring | 0/20 | No security roles found. |  |
| Trust centre or compliance activity | 8.2/10 | Trust centre published. | 574a3c7827 |
| Recent enterprise expansion / scaling | 3.4/15 | 1 expansion / funding signal(s). | 9ea8ee1ab8 |

### Research agent log

**Round 1** — open questions: Is it hiring for security, compliance or engineering?; Is there any evidence compliance matters right now?

- Targeted: https://rootly.com/careers [careers] — Is it hiring for security, compliance or engineering?, Is there any evidence compliance matters right now?
- Targeted: https://security.rootly.com/ [security] — Is there any evidence compliance matters right now?
- Targeted: https://rootly.com/customers/capa [customers] — Is there any evidence compliance matters right now?
- Targeted: https://rootly.com/blog [news] — Is there any evidence compliance matters right now?
- Readable: 4 page(s)
- New: Serves or targets financial services (https://security.rootly.com/)
- New: Mentions SOC 2 — appears to be held (https://security.rootly.com/)
- New: Mentions SOC 2 (in a blog/news post — may not describe the company itself) (https://rootly.com/blog)
- New: Security control described: Pentest (https://security.rootly.com/)
- New: References a Trust Center (https://security.rootly.com/)
- New: Security review / procurement process: security review (https://security.rootly.com/)
- **What changed:** ICP 73→80, timing 20→39, decision not_qualified→qualified. 6 new evidence item(s).

- Stopped before round 2: Decision already well supported.

## 4. Decision-maker

Status: **selected** · providers tried: Manual mapping (Apollo / research), Company website (team page)

- Hunter.io skipped: HUNTER_API_KEY not set.
- Manual mapping returned 0 contact(s)
- Company website listed 2 named leader(s)

Quentin Rousseau, CTO and Co-founder (relevance 67.0): CTO: accountable for technical controls and usually sponsors the first SOC 2. A security function exists, so the CTO is one step removed from day-to-day compliance. No email address available — reachable only after manual verification. Preferred over JJ Tang (CEO and Co-founder, score 40.0). Email not yet verified — the test preview will show the prospect address as unavailable.

| Name | Title | Email | Source | Source URL |
|---|---|---|---|---|
| Quentin Rousseau | CTO and Co-founder | not available | Company website (team page) | https://rootly.com/about |

Alternatives considered:

| Name | Title | Relevance | Why |
|---|---|---|---|
| JJ Tang | CEO and Co-founder | 40.0 | CEO / Founder: final sponsor in small companies, but far from the evidence work. |

## 5. Pain points

**Security questionnaires and vendor reviews slowing enterprise deals** — observed, confidence 0.9

The site points to an enterprise motion (security review); enterprise buyers send security questionnaires that usually land with the CTO and Co-founder.

- "Start your security review" — https://security.rootly.com/
- "Rootly Trust Center | Powered by SafeBase" — https://security.rootly.com/
- "Loved by fast-growing startups and the Fortune 500." — https://rootly.com/

**Keeping SOC 2 / ISO 27001 controls continuously audit-ready as the company scales** — observed, confidence 0.87

Rootly already references SOC 2; certifications must be re-evidenced every year while headcount and systems grow (Mentions SOC2 — appears to be held).

- "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." — https://rootly.com/security
- "SOC 2 Report" — https://security.rootly.com/
- "Latest funding: Series A round (2023-08)." — enrichment://apollo.io/rootly.com

## 6. Generated email

**Subject:** security reviews at Rootly  
*Candidates:* security reviews at Rootly / Rootly and SOC 2 / question on security reviews — Chosen for specificity to the observed signal and brevity (score 4 vs 4, 3).

```
Hi Quentin,

Noticed your trust centre says "Start your security review". That usually means security questionnaires sit right inside the sales cycle.

Are security questionnaires starting to slow down your larger deals?

Sprinto automates evidence collection and continuous control monitoring for SOC 2, ISO 27001 and GDPR, so audit prep stops being a side project for engineering. If it's relevant, would a 20-minute conversation be useful?

Best,
Sprinto Growth Team
```

Word count: 64 · quality checks: length_60_110_words=pass, greets_by_first_name=pass, hook_is_grounded_in_evidence=pass, no_banned_phrases=pass, no_exclamation_marks=pass, single_cta=pass, no_unsupported_sprinto_claims=pass

### Evidence → email trace

| Sentence | Purpose | Evidence | Source |
|---|---|---|---|
| Noticed your trust centre says "Start your security review". | Website observation (hook) | Start your security review | https://security.rootly.com/ |
| That usually means security questionnaires sit right inside the sales cycle. | Business implication of the observation | References to security questionnaires, DPAs or procurement suggest deals already pass through vendor security review. | https://security.rootly.com/ |
| Are security questionnaires starting to slow down your larger deals? | Role-specific challenge (observed) | "Start your security review" — https://security.rootly.com/; "Rootly Trust Center \| Powered by SafeBase" — https://secur | https://security.rootly.com/ |
| Sprinto automates evidence collection and continuous control monitoring for SOC 2, ISO 27001 and GDPR, so audit prep stops being a side project for engineering. | Relevant Sprinto value proposition (core product, no extra claims) |  |  |
| If it's relevant, would a 20-minute conversation be useful? | Single low-pressure CTA |  |  |

## 7. Dispatch

Status: **pending_review** — Waiting for a human at the review gate.
Preview file: `/Users/anishasarkar/sprinto-case-study/sprinto-signal-engine/output/review/rootly-com.txt`

## Decision ledger

### WHY THIS COMPANY?

- SaaS business model +22.5/25: SaaS model supported by 6 indicator(s). [bcc558f5e9] "Get started for free" (https://rootly.com/); [135ee99d81] "Book a demo" (https://rootly.com/)
- Relevant growth stage (Series A–C) +7.4/15: Explicit Series A — inside Sprinto's sweet spot. [9ea8ee1ab8] "Latest funding: Series A round (2023-08)." (enrichment://apollo.io/rootly.com); [4a0c2560a1] "Headcount: 92 employees." (enrichment://apollo.io/rootly.com)
- Enterprise customer orientation +20/20: 4 enterprise reference(s) / enterprise-tier signals. [eab89c40bb] "Loved by fast-growing startups and the Fortune 500." (https://rootly.com/); [0b501829d6] "See how teams from the Fortune 100 to fast-growing startups use Rootly for incident response, on-call, retrosp" (https://rootly.com/customers)
- Relevant customer industry +10/10: Serves regulated industries: healthcare, financial services [562dba2ff5] "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." (https://rootly.com/security); [ed254e56dd] "Cyber Insurance" (https://security.rootly.com/)
- Security / compliance complexity +20/20: 7 security/compliance artefact(s) on the site. [76a871df87] "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." (https://rootly.com/security); [9e8083a358] "Audit log" (https://rootly.com/security)

### WHY NOW?

- Explicit SOC 2 / ISO 27001 / audit requirement +19/30: Certification already held — renewal and multi-framework expansion, not a first audit. [1ebf0e9702] "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." (https://rootly.com/security); [4260150cd6] "SOC 2 Report" (https://security.rootly.com/)
- Enterprise security review / procurement pressure +8.4/25: 1 reference(s) to security reviews, DPAs or procurement. [00b1c9de87] "Start your security review" (https://security.rootly.com/)
- Trust centre or compliance activity +8.2/10: Trust centre published. [574a3c7827] "Rootly Trust Center | Powered by SafeBase" (https://security.rootly.com/)
- Recent enterprise expansion / scaling +3.4/15: 1 expansion / funding signal(s). [9ea8ee1ab8] "Latest funding: Series A round (2023-08)." (enrichment://apollo.io/rootly.com)
- Buying moment — Mentions SOC2 — appears to be held: An existing certification must be renewed every year and usually expands to further frameworks as the customer base grows; continuous compliance becomes the ongoing cost. (https://rootly.com/security)
- Buying moment — References a Trust Center: A trust centre signals that customers are actively asking for security documentation during deals. (https://security.rootly.com/)
- Buying moment — Security review / procurement process: security review: References to security questionnaires, DPAs or procurement suggest deals already pass through vendor security review. (https://security.rootly.com/)

### WHY THIS PERSON?

- Quentin Rousseau, CTO and Co-founder (relevance 67.0): CTO: accountable for technical controls and usually sponsors the first SOC 2. A security function exists, so the CTO is one step removed from day-to-day compliance. No email address available — reachable only after manual verification. Preferred over JJ Tang (CEO and Co-founder, score 40.0). Email not yet verified — the test preview will show the prospect address as unavailable.
- Alternative: JJ Tang (CEO and Co-founder) relevance 40.0 — CEO / Founder: final sponsor in small companies, but far from the evidence work.

### WHY THIS PAIN POINT?

- Security questionnaires and vendor reviews slowing enterprise deals [observed, confidence 0.9]: The site points to an enterprise motion (security review); enterprise buyers send security questionnaires that usually land with the CTO and Co-founder. Evidence: "Start your security review" — https://security.rootly.com/ | "Rootly Trust Center | Powered by SafeBase" — https://security.rootly.com/
- Keeping SOC 2 / ISO 27001 controls continuously audit-ready as the company scales [observed, confidence 0.87]: Rootly already references SOC 2; certifications must be re-evidenced every year while headcount and systems grow (Mentions SOC2 — appears to be held). Evidence: "SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC." — https://rootly.com/security | "SOC 2 Report" — https://security.rootly.com/

### WHY THIS EMAIL?

- Hook: your trust centre says "Start your security review" (https://security.rootly.com/)
- Pain point used: Security questionnaires and vendor reviews slowing enterprise deals
- Security review / procurement process: security review (https://security.rootly.com/) suggests references to security questionnaires, DPAs or procurement suggest deals already pass through vendor security review. Quentin Rousseau (CTO and Co-founder) is the likely owner of 'Security questionnaires and vendor reviews slowing enterprise deals'.

### WHAT COULD MAKE THIS DECISION WRONG?

- 8 of 24 evidence items are inferred rather than explicitly stated.
- Unknown: Security, compliance or engineering hiring activity.
- 1 evidence item(s) reference older years — may be outdated (e.g. 'Latest funding: Series A round (2023-08).').
- Company already holds SOC 2 — the conversation is about continuous compliance / extra frameworks, not a first audit.
- Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).

## Evidence appendix

| ID | Category | Finding | Type | Conf. | URL | Excerpt |
|---|---|---|---|---|---|---|
| 0f9430fa71 | other | Business description (homepage / meta description) | explicit | 0.7 | https://rootly.com/ | The all-in-one AI incident management platform for fast-moving engineering teams to detect, manage, resolve, and learn from incidents faster. |
| bcc558f5e9 | saas_indicator | Self-serve free trial / sign-up | explicit | 0.6 | https://rootly.com/ | Get started for free |
| 135ee99d81 | saas_indicator | Product demo / sales-led motion | explicit | 0.6 | https://rootly.com/ | Book a demo |
| afca70acf5 | saas_indicator | Developer API | inferred | 0.4 | https://rootly.com/ | Connect all your existing tools—Slack, Jira, Zoom—and extend further with our Terraform provider, API, or MCP server. |
| 51888a39c4 | saas_indicator | Product integrations | inferred | 0.4 | https://rootly.com/ | Explore all integrations |
| 44d4738607 | saas_indicator | Platform positioning | inferred | 0.4 | https://rootly.com/ | The all-in-one AI incident management platform for fast-moving engineering teams to detect, manage, resolve, and learn from incidents faster. |
| df09c930b5 | saas_indicator | Workflow / automation product | inferred | 0.4 | https://rootly.com/ | Workflows → |
| eab89c40bb | enterprise_customer | Customer reference: Loved by fast-growing startups and the Fortune 500 | inferred | 0.55 | https://rootly.com/ | Loved by fast-growing startups and the Fortune 500. |
| 0b501829d6 | enterprise_customer | Customer stories page exists: Rootly \| Customer Stories | explicit | 0.6 | https://rootly.com/customers | See how teams from the Fortune 100 to fast-growing startups use Rootly for incident response, on-call, retrospectives, and AI SRE. |
| 562dba2ff5 | regulated_industry | Serves or targets healthcare | inferred | 0.55 | https://rootly.com/security | SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC. |
| ed254e56dd | regulated_industry | Serves or targets financial services | inferred | 0.55 | https://security.rootly.com/ | Cyber Insurance |
| 4a0c2560a1 | other | Headcount mention: 92 employees | explicit | 0.7 | enrichment://apollo.io/rootly.com | Headcount: 92 employees. |
| 9ea8ee1ab8 | funding | Funding announcement: Series A round | explicit | 0.42 | enrichment://apollo.io/rootly.com | Latest funding: Series A round (2023-08). |
| 1ebf0e9702 | certification_held | Mentions SOC2 — appears to be held | explicit | 0.8 | https://rootly.com/security | SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC. |
| 4260150cd6 | certification_held | Mentions SOC 2 — appears to be held | explicit | 0.8 | https://security.rootly.com/ | SOC 2 Report |
| 4f69184f9d | compliance_mention | Mentions SOC 2 (in a blog/news post — may not describe the company itself) | inferred | 0.35 | https://rootly.com/blog | Audit-ready incident records: what SOC 2 auditors look for and how to evaluate tools |
| 861e451534 | compliance_mention | Mentions GDPR | explicit | 0.6 | https://rootly.com/security | SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC. |
| 76a871df87 | security_page | Security control described: audit logs | explicit | 0.6 | https://rootly.com/security | SOC2, HIPAA, GDPR compliant with private incidents, audit logs, and granular RBAC. |
| 9e8083a358 | security_page | Security control described: Audit log | explicit | 0.6 | https://rootly.com/security | Audit log |
| 16ae7060f6 | security_page | Security control described: Pentest | explicit | 0.6 | https://security.rootly.com/ | Pentest Report |
| 574a3c7827 | trust_centre | References a Trust Center | explicit | 0.7 | https://security.rootly.com/ | Rootly Trust Center \| Powered by SafeBase |
| 056bf5ac60 | enterprise_orientation | Enterprise orientation: Fortune 500 | explicit | 0.65 | https://rootly.com/ | Loved by fast-growing startups and the Fortune 500. |
| 399039550a | enterprise_orientation | Enterprise orientation: Enterprise-grade | explicit | 0.65 | https://rootly.com/security | Enterprise-grade incident management for security teams. |
| 00b1c9de87 | security_review_pressure | Security review / procurement process: security review | explicit | 0.7 | https://security.rootly.com/ | Start your security review |
