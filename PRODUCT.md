# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary: Mesa faculty and classmates grading a case-study build (MESA Case 02, Sprinto). They open the public
dashboard or the control panel once or twice, short on time, and need to see quickly that every qualification
decision is backed by evidence and that the system is safe. Secondary: the student operator, who runs research,
settles gaps on the decision desk and signs off drafts in the local control panel.

## Product Purpose
Evidence-driven outbound research for Sprinto (SOC 2 / ISO 27001 / GDPR compliance automation). It reads a SaaS
company's own pages, answers a written Evidence Map (Go / No-Go), finds the right person, and drafts a short email
that opens with a real, cited fact. Success: a viewer leaves convinced that nothing was guessed.

## Positioning
Evidence, not guesses. Every answer quotes the line on the company's site it rests on; unknowns are shown as unknown
and sent to a person; a person signs off every email, and sends can only reach the operator's own test inbox.

## Operating Context
Flask control panel (app.py) run locally at 127.0.0.1:5050, also deployed as a public sandbox on Vercel
(sprinto-panel.vercel.app); a static public dashboard (export_site.py → sprinto-dashboard.vercel.app). Python
pipeline: scrape, extract, Evidence Map gate, contact, pain points, draft, review, test-inbox dispatch, learning log.

## Capabilities and Constraints
- Research up to 3 websites; funding-news scan and audit-signal lead search need a Serper key (local only).
- Decision desk (qualify / out of scope with a reason), draft desk (edit, sign off, decline, verdict ticks), outcomes.
- Learning log: repeated reviewer reactions become lessons applied to later drafts; account-specific facts never reused.
- Public sandbox: rate-limited, read-only for anything that changes real data or spends credits; nothing can be sent.
- Claude extraction is optional; without a key a labelled rule-based fallback runs.

## Brand Commitments
- Visual references chosen by the user: OGAKI, Lightship RV, UNESCO Virtual Museum, Breakthrough Energy (serif
  headlines, lime accent). Since Nov 2026 the ground is a cool "ledger paper" (#f2f4ee, white cards, ink #1c211b) and
  the text face is Schibsted Grotesk, replacing the cream ground and Instrument Sans the review flagged as generic.
- One site, one look: landing /, results /dashboard, control panel /app share the menu, logo and tokens in
  src/site_chrome.py. A classmate's app (sprinto-outreach-delta.vercel.app) is a structural reference
  only: never copy its wording.
- No em dashes or en dashes in visible copy (the user reads them as machine-written).
- "Case-study build, not affiliated with Sprinto."

## Evidence on Hand
Five real companies researched (Rootly, Attio, Plain, incident.io, Sweetgreen) with cited evidence in
output/state and output/company_reports; Apollo enrichment for Rootly and Plain; CTO titles verified on company
sites. No real replies, meetings or deals exist beyond outcomes the operator logs; do not fabricate any.

## Product Principles
1. Show the receipt: every claim on screen links to its source.
2. Unknown is an honest answer; gaps go to a person, never to a guess.
3. A person signs off every email; the test inbox is the only possible recipient.
4. Measured and estimated numbers are always labelled and kept apart.

## Accessibility & Inclusion
WCAG 2.2 AA: contrast, keyboard operation, visible focus, readable text sizes.
