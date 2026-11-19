# Sprinto Signal Engine

An evidence-driven outbound prospecting system for Sprinto (SOC 2 / ISO 27001 / GDPR compliance automation).
It turns a list of domains into **researched, qualified, explainable** outreach opportunities — and refuses to
fabricate anything it cannot source.

```
Define ICP → Shortlist → Deep research (scrape site + news + enrichment) → Evidence Map Go / No-Go
   → Hunter / Apollo → POC → Draft email → HUMAN REVIEW GATE → Send (test inbox only) → Track opens, replies, revenue
```

This follows the planning whiteboard (ICP: SaaS, Series A–C, preparing for an audit, 50–200 employees,
client count and size, industry, AWS/GCP/Azure) and the "Evidence Map — fill this before you build" exercise.

**Design principle:** optimise for relevant buying opportunities, not emails sent. Every decision carries a
source URL, a verbatim excerpt, an evidence type (explicit / inferred / hypothesis) and a confidence.

---

## Quick start

```bash
cd sprinto-signal-engine
python3.12 -m venv .venv && source .venv/bin/activate     # Python 3.11+ works
pip install -r requirements.txt
cp .env.example .env                                      # then fill in what you have (all optional)
python main.py --input data/prospects.csv
pytest -q
```

Other options:

| Command | What it does |
|---|---|
| `python main.py --input data/prospects.csv --limit 3` | first 3 companies only |
| `python main.py --company rootly` | one company (name or domain match) |
| `python main.py --dry-run` | force preview-only, regardless of `.env` |
| `python main.py --resume` | skip completed companies; resume others at the failed stage (scrapes + Claude calls are cached) |
| `python main.py --no-claude` | force the deterministic fallback |
| `python main.py --output output/run2` | write to a separate output folder |
| `python main.py --gmail-auth` | one-time Gmail OAuth consent (opens browser) |
| `python main.py --check` | **credential preflight**: tests each configured key with a free, read-only call (Claude `GET /v1/models`, Hunter `/v2/account`, Gmail token refresh, SMTP login) and sends nothing. Exit code 1 if anything fails |
| `python main.py --revenue` | rebuild the revenue & conversion report from saved runs |
| `python main.py --record-outcome "Rootly" replied` | log a real outcome (`contacted`, `opened`, `replied`, `meeting`, `opportunity`, `won`, `lost`); add `--deal-value 12000` for opportunity/won |
| `python main.py --review` / `--approve "X"` / `--reject "X" --reason "…"` | human review gate: nothing is sent until approved |
| `python export_site.py` then `cd sprinto-dashboard && vercel deploy --prod` | rebuild and publish the static results dashboard (live: https://sprinto-dashboard.vercel.app) |
| `python main.py --send-test` | **explicit test-send mode** (also requires `DRY_RUN=false`) |

---

## Credentials (all optional — the system degrades honestly)

| Variable | Used for | Where to get it | If missing |
|---|---|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-opus-5-5`) | AI extraction, decision critique, pain points, email writing | console.anthropic.com → API Keys | Deterministic rule-based fallback, labelled *"not AI-verified"*, confidence capped at 0.75 |
| `HUNTER_API_KEY` | Contact discovery (Domain Search) | hunter.io → API (free tier: 25 searches/month) | Manual CSV, then the company's own team page; otherwise **flagged for review** |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | Sending the test preview | Google Cloud Console → enable Gmail API → OAuth consent screen (add yourself as test user) → Credentials → OAuth client ID → *Desktop app* | Preview saved to `output/generated_emails/`, status `blocked_missing_credentials` |
| `EMAIL_BACKEND=smtp`, `SMTP_USER`, `SMTP_APP_PASSWORD` | SMTP alternative | myaccount.google.com/apppasswords (needs 2-step verification) | — |
| `TEST_TO_EMAIL` | **The only address that can ever receive mail** | your own inbox | Nothing can be sent (`blocked_by_guard`) |
| `SEARCH_PROVIDER=serper`, `SERPER_API_KEY` | Optional external discovery in the research agent | serper.dev | Research agent uses on-site discovery only |

`config.Settings.describe()` prints which integrations are configured at start-up **without printing values**; a
logging filter also redacts any configured secret that reaches a log line.

---

## Control panel (`app.py`)

A local multi-page web app, so the pipeline can be driven without the command line:

```bash
.venv/bin/python app.py          # open http://127.0.0.1:5050
```

| Page | What it does |
|---|---|
| **Overview** | Status, the route from website to signed-off email with counts, both desks, a per-run scorecard (qualified, sent to your desk, pages read, rewritten by you), why accounts were ruled out, which gaps reached a person, latest reactions |
| **Run research** | Research up to 3 websites; **Scan funding news** (Series A to C headlines, ranked, websites resolved, keeps researching until N qualify); list sites showing audit signals; live log; past runs |
| **Accounts** | Every account, searchable (⌘K) and filterable; each opens **How it decided**: rule-outs, the three deciding questions and extra colour, each with its quote, source and date, plus scores, who to write to and the draft |
| **Decision desk** | Accounts with a gap in the map: mark as qualified or out of scope (a reason is required), or research again |
| **Draft desk** | Tweak, sign off or decline drafts; quick verdict ticks; why this person, the opening fact, line-by-line sources; log real replies |
| **Learning log** | Write, react, log, distil, recall, use: lessons kept from repeated reviewer reactions, applied to later drafts, with "lesson used vs not" edit rates and a switch-off control |

Structure was informed by a classmate's app (used only as a structural reference; all wording is our own). The panel
listens only on 127.0.0.1, every form carries a per-session token, and it has no extra powers: sending still needs
`DRY_RUN=false`, a sign-off, and goes only to `TEST_TO_EMAIL`. Design reviewed with Impeccable (product brief in
`PRODUCT.md`) and tested with Playwright in Chrome, Firefox, WebKit and on iPhone 15 (screenshots in `test-screenshots/`).

### Online version: https://sprinto-panel.vercel.app

The same panel, deployed to Vercel in **public sandbox mode**. It switches on automatically on Vercel, or locally with `PUBLIC_MODE=1`.
Anyone can use it without a password, so it's built to be harmless:

- **Research a company** works. It runs inside the request (about 5 to 60 seconds) and is limited to 4 runs per visitor per hour,
  one at a time. Results go to a temporary sandbox seeded from a read-only snapshot of the real results.
- **Nothing can be sent.** `DRY_RUN` is forced on and `TEST_TO_EMAIL` is blanked, so the recipient guard blocks every send.
- **No paid lookups.** Hunter and Serper keys are never used, and Claude stays off unless a key is set in the Vercel project.
- **Local-only actions:** approve or reject, log outcomes, re-run, lead search and publish are disabled online, because they
  change real data or spend credits.

To redeploy after new local runs:

```bash
./build_panel_deploy.sh && cd sprinto-panel && vercel deploy --prod
```

## Evidence Map: the Go / No-Go gate (`src/evidence_map.py`)

The map is written down as data before any scoring. Each answer is YES, NO or UNKNOWN, decided by code
and cited to a source:

| Question | Data that answers it | Where it lives | Sufficient when (code-checked) | Limit | If unanswered | Short-circuit | Role |
|---|---|---|---|---|---|---|---|
| Is it a SaaS business? | Sells subscription software: pricing per seat/month, free trial, login, API | homepage, pricing, product | is_saas is True with ≥1 SaaS indicator | 3 pages | Flag at review gate | Non-SaaS → DROP | core |
| Is it Series A–C / 50–200 employees? | Named funding round, or a headcount statement | news (search API), about, careers, company enrichment (Apollo) | funding matches Series A/B/C, or headcount 50 ≤ n ≤ 200 | 3 pages | Flag at review gate | — | core |
| Is it preparing for an audit (SOC 2 / ISO 27001)? | Certification in progress, security/GRC hire, security-review process | security, trust, careers, compliance | explicit in-progress/hiring/review evidence, or timing score ≥ 35 | 4 pages | Nurture (right company, wrong time) | Sprinto trust centre → existing customer | core |
| Does it have >50 clients / larger customers? | 'Trusted by 500+ teams', named enterprise logos | homepage, customers | customer count ≥ 50 or ≥ 2 enterprise references | 2 pages | Neutral | — | supporting |
| Does it serve a regulated industry? | Healthcare, fintech, insurance, government customers | homepage, news | regulated_industry evidence present | 1 pages | Neutral | — | supporting |
| Is it on AWS / GCP / Azure? | Explicit 'hosted on AWS' statement | security, careers, company enrichment (Apollo) | explicit infrastructure statement | 2 pages | Neutral | — | supporting |
| **Worst case** | Site unreachable or nearly empty | — | — | — | Hand to a human (never an automatic rejection) | — | — |

**Decision rule** over the three core questions:

| Core answers | Decision |
|---|---|
| Any short-circuit | **DROP** (an existing Sprinto customer goes to account management) |
| A core question is NO | **DROP**, or **NURTURE** if only audit intent is missing |
| 3 YES | **QUALIFY** |
| 2 YES + 1 UNKNOWN | **QUALIFY-AND-FLAG**: the unknown becomes a checklist item at the review gate. If the unknown is audit intent, its own "if unanswered" rule applies instead: **NURTURE** |
| Otherwise | **HAND TO A HUMAN** |

That is our answer to "two of three answered, one unknown": **qualify-and-flag**, unless the unknown is the
buying moment itself. A cold email with no buying moment has no hook, so that case nurtures.
The ICP, timing and confidence scores still exist. They explain and rank the decision but cannot overrule
the gate. Every company report has the full map table, with the evidence behind each answer.

## Human review gate (`src/review_gate.py`)

**Draft → Review → Send.** No email is dispatched until a person approves it.

```bash
python main.py --review                      # what's waiting, plus the Evidence Map flags to check
# edit output/review/<company>.txt in place (keep the "Subject:" line)
python main.py --approve "Rootly" --send-test
python main.py --reject "Plain" --reason "hook is product copy, not a real process"
```

When a draft is approved, the tool measures the word-level change between the draft and the approved text.
**More than 50% rewritten counts as a heavy edit**, which is the whiteboard's "changes the email > 50%"
quality signal. The heavy-edit rate is reported overall and by email angle. A high rate produces a
recommendation to fix that template before sending more.

## External evidence (`src/external_sources.py`)

Websites rarely state their funding round or headcount, so two optional sources fill that gap. Both go
through the same extractor and grounding check as site pages:

- **News, via the Serper news API** (`SEARCH_PROVIDER=serper`, `SERPER_API_KEY`). The Google News RSS feed is
  **not** scraped: `news.google.com/robots.txt` disallows `/rss`, and its terms limit it to personal feed
  readers. A headline counts only if it names the company exactly. Common-word names like "Plain" need a
  tighter match.
- **Company enrichment** (`data/company_enrichment.csv`): one row per field, each with its source and
  retrieval date, filled from a real lookup such as Apollo.io organisation enrichment. Rows without a
  source are ignored, and website evidence always comes first.

## Architecture

```
sprinto-signal-engine/
├── main.py                     CLI, live terminal summary
├── config.py                   env-driven settings, logging + secret redaction
├── data/
│   ├── prospects.csv           demo list (5 real companies)
│   ├── prospects_edge_cases.csv  unreachable domain (robustness demo)
│   └── contacts_override.csv   manual / Apollo contact mapping (empty template — add only real people)
├── prompts/                    Claude prompts, editable independently of code
├── src/
│   ├── models.py               Pydantic contracts (Evidence, BuyingMoment, Qualification, …)
│   ├── scraper.py              STEP 1  polite scraping, link discovery, ATS job-board APIs
│   ├── llm.py                  Claude JSON wrapper: retry, schema repair, cache
│   ├── signal_extractor.py     STEP 2  Claude extractor + deterministic extractor + grounding check
│   ├── evidence_map.py         STEP 3  Evidence Map Go / No-Go gate (core + supporting questions)
│   ├── qualification_engine.py STEP 3a transparent ICP / timing / confidence scoring
│   ├── research_agent.py       STEP 3b secondary-investigation loop (≤2 rounds, page budget)
│   ├── contact_discovery.py    STEP 4  Hunter / manual / team-page providers + role ranking
│   ├── pain_point_engine.py    STEP 5  role × evidence pain points (observed vs inferred)
│   ├── email_generator.py      STEP 6  personalisation chain + quality gate + sentence trace
│   ├── review_gate.py          STEP 6b human approval, edit-distance tracking (>50% = heavy edit)
│   ├── email_dispatcher.py     STEP 7  Gmail OAuth / SMTP, TEST_TO_EMAIL allowlist guard
│   ├── external_sources.py     news (Serper) + enrichment (Apollo CSV) as citable pages
│   ├── revenue_tracker.py      funnel, open rate, revenue, expected-value queue, angle optimiser
│   ├── preflight.py            --check credential tests (read-only)
│   ├── decision_ledger.py      six-question ledger, per-company + consolidated reports
│   └── pipeline.py             orchestration, per-stage isolation, checkpoint / resume
├── output/
│   ├── company_reports/*.md    one research report per company
│   ├── generated_emails/       .eml / .txt test previews
│   ├── decision_ledger.json    machine-readable ledger
│   ├── pipeline_summary.csv    one row per company
│   ├── pipeline_report.md      consolidated report
│   └── state/, cache/          resume checkpoints, page / API caches
└── tests/                      84 offline tests (fake HTTP, fake Claude client)
```

### What each stage does

1. **Scraper** — tries `https://`, `https://www.`, `http://`; respects `robots.txt`; per-host delay; timeouts;
   never fetches a URL twice (in-memory set + disk cache); strips scripts, nav, footers, forms, cookie/consent
   banners and duplicate lines; fixes mis-declared charsets. Links are classified by path segments and anchor text
   (not exact paths), including external trust centres (SafeBase, Vanta, Drata…) and job boards
   (Greenhouse / Lever / Ashby, read through their public JSON APIs). 401/403/429 are recorded as
   `access_restricted` and **not bypassed**. Playwright is optional (`USE_PLAYWRIGHT=true`) for JS-only pages.
2. **Signal extraction** — Claude returns JSON validated against the `ExtractionResult` Pydantic schema; invalid
   output triggers up to two repair requests showing the validation error, then a labelled fallback. Without
   Claude, a transparent regex extractor produces the same contract. **Both** pass `ground_evidence`, which
   discards any claim whose excerpt is not found verbatim on the cited page. Context rules prevent
   mis-attribution: customer case studies and blog posts can't create company facts (funding, SOC 2 status,
   expansion), careers-page "insurance" benefits don't count as an insurance industry, and short product-mock-up
   strings ("Security review underway" inside a CRM screenshot) don't count as a security-review process.
3. **Qualification + research agent** — deterministic scoring (below). If evidence is thin, the agent maps each
   gap to page types (careers → hiring, trust/security → certifications, customers → enterprise traction, news →
   funding), reads unseen pages within budget, re-extracts, re-scores and logs *what changed and why*.
4. **Contact discovery** — providers in `CONTACT_PROVIDERS` order. Ranking weighs role relevance, problem
   ownership *in this company* (e.g. CTO +8 when no security function exists, −8 when one does), domain match
   (−60 for a wrong-domain email), verification status and email confidence. Team-page parsing only reads
   about/team pages and skips quoted testimonials, so customers are never mistaken for staff.
5. **Pain points** — a library of role-specific challenges, each requiring evidence triggers; each result is
   marked `observed` or `inferred` with supporting excerpts.
6. **Email** — chain: observation → implication → role challenge → Sprinto value → one soft CTA. Three subject
   lines, best one picked with a stated reason. Quality gate: 60–110 words, first-name greeting, grounded hook,
   no banned phrases / exclamation marks / invented Sprinto claims. Every sentence is traced to its evidence.
7. **Dispatch** — see safety model.

### Scoring framework (starting weights, documented in `qualification_engine.py`)

| ICP fit (0–100) | pts | Buying timing (0–100) | pts |
|---|---|---|---|
| SaaS business model | 25 | Explicit SOC 2 / ISO 27001 / audit requirement (in-progress 30, held ≈15–20, mention 8) | 30 |
| Growth stage (Series A–C full; seed 6; D+ 8; headcount proxy 7) | 15 | Enterprise security review / procurement pressure | 25 |
| Enterprise customer orientation | 20 | Security or compliance hiring (+ small credit for eng hiring) | 20 |
| Regulated customer industry (else 4) | 10 | Trust centre | 10 |
| Scaling signals | 10 | Recent expansion / funding | 15 |
| Security / compliance complexity | 20 | Penalties: −10 incumbent compliance platform visible; −3 per contradiction | |

Honesty rules: points scale with confidence and explicitness; evidence citing a year ≥3 years old is halved; one
evidence item earns points for **one** criterion per score; missing information earns 0 and is stated as
*"missing, not negative"*.

**Evidence confidence** = 35% mean evidence confidence + 15% share explicit + 35% coverage of six key questions
+ 15% pages read − 5% per contradiction (capped at 0.75 in fallback mode).

**Decision:** `qualified` needs ICP ≥ 55 **and** timing ≥ 35 **and** confidence ≥ 0.45. Good fit with weak
timing → `not_qualified` / *nurture*. Non-SaaS → `not_qualified` / *disqualify*. Unreadable site or thin evidence
→ `insufficient_data` / *manual review* (explicitly **not** a rejection).

### Safety model for email

- `DRY_RUN=true` by default → `.eml` previews only. Real sending needs `DRY_RUN=false` **and** `--send-test`.
- The dispatcher never receives the prospect's address as a destination: the MIME `To:` is built from
  `TEST_TO_EMAIL` only. The prospect appears only inside the body as *"Intended recipient / Original prospect email"*.
- `assert_allowed_recipient` rejects any address ≠ `TEST_TO_EMAIL`, lists (`,` `;`), CR/LF header injection,
  display-name tricks (`"me@x" <evil@y>`), and an unset/invalid `TEST_TO_EMAIL`.
- `assert_message_safe` re-checks the finished message immediately before each Gmail/SMTP call: exactly one `To`,
  no `Cc` / `Bcc` / `Resent-*`.

---

## Revenue & conversion tracking (`src/revenue_tracker.py`)

Every run ends with a revenue section and writes `output/revenue/`: `revenue_report.md`, `priority_queue.csv`
and `revenue_metrics.json`. `--revenue` rebuilds them from saved runs without scraping again.

Open rate is tracked by logging `opened` outcomes, and a reply implies an open. Tracking pixels aren't used:
they need a hosted endpoint and are unreliable under Apple Mail Privacy Protection.

**Measured versus estimated.** These two are never mixed:

| Kind | Where it comes from | Examples |
|---|---|---|
| Measured | Pipeline counts, plus outcomes a person logs in `data/outcomes.csv` | won revenue, open opportunity value, contacted→reply rate |
| Estimated | Planning assumptions in `data/revenue_assumptions.json`, updated by the logged outcomes | expected revenue, P(win), revenue blocked at each gap |

The tool never emails prospects, so market outcomes (replies, meetings, deals) can only come from what a
person records after real outreach done outside this demo. With no outcomes logged, measured revenue is
**0** and every estimate is labelled as one.

**Funnel.** Prospects → scraped → qualified → decision-maker found → email ready → contacted → replied →
meeting → opportunity → won. The report shows step conversion and conversion from the first stage.

**Conversion model.** Each transition (contacted→replied, replied→meeting, meeting→opportunity,
opportunity→won) is a Beta posterior. The prior comes from the assumptions file, then logged outcomes
take over. Companies still in progress don't count as failures; only a `lost` outcome does.

**How it maximises revenue.**
1. **Expected-value ranking.** Each qualified company's expected revenue is P(win from its current stage) × ACV.
   ACV is either the deal value you recorded or an assumed amount by headcount band. Before a reply,
   P(win) is scaled by the buying-timing score: 0.5 + timing/50, capped between 0.5 and 2. This lift is a
   stated heuristic, to be replaced by segment data. `priority_queue.csv` is the outreach order.
2. **Revenue blocked at each gap.** For example, "USD 122 blocked because no decision-maker was found
   (Attio, Plain)". This shows which fix earns the most: finding contacts, finding email hooks, or follow-ups.
3. **Angle optimisation (Thompson sampling).** Once `min_sends_to_learn` (10) contacted outcomes exist,
   the email step reorders the evidence-backed pain points by sampled reply rate per pain-point family.
   It only picks among pain points the evidence already supports, at confidence ≥ 0.5. It never invents
   an angle and never changes qualification.
4. **Funnel-leak alerts.** A stage converting below 75% of plan, with at least 5 decided trials, is flagged.

**Edit `data/revenue_assumptions.json`** with Sprinto's real ACV and historical rates. The shipped numbers
are placeholders. Defaults: reply 5%, meeting 50%, opportunity 50%, won 33%, ACV USD 6k/12k/25k by headcount band.

## Demo results (real run, 19 Nov 2026, rule-based reading: no Claude key on this machine)

| Company | Decision | Why (each reason is quoted from their own pages in the company report) |
|---|---|---|
| Attio | **DROP** | Trust centre runs on **Vanta** (found `vanta-entry-loader` in trust.attio.com's page source): a competitor is already in place |
| Plain | **DROP** | Trust centre runs on **Vanta** (trust.plain.com page source); already SOC 2 Type II certified |
| Rootly | **NURTURE** | Already holds SOC 2 (plus GDPR, CCPA) and runs its trust centre on **SafeBase**; nothing points to a new audit |
| incident.io | **NURTURE** | Already SOC 2 Type I & II; nothing points to a new audit |
| Sweetgreen | **DROP** (short-circuit) | Not SaaS (restaurant control case) |

**None of these five is a lead today, and that is the correct answer.** An earlier version qualified Rootly, Attio and
Plain. A manual review found the reasons were false buying signals: Rootly's "Start your security review" is a
SafeBase trust-centre button for *its customers*, and Plain's "Data Processing Agreement" is a document Plain *offers*.
Both show a mature programme, not a need. The guardrails below now prevent this, and the three stale drafts were
withdrawn automatically. New leads come from **Run research → Scan funding news** (needs a Serper key) or from
researching specific websites.

## Guardrails against false buying signals

| Guardrail | What it stops |
|---|---|
| **Trust-centre platform read from the page source** (`scraper.detect_trust_platform`) | Vanta, Drata, Secureframe, Sprinto, Thoropass, Scrut, Oneleet, Delve or TrustCloud behind a trust centre drops the account. SafeBase, Conveyor or Whistic marks a mature programme. Matched only on specific signatures (loader names, "Powered by" lines, platform hosts), so a SafeBase page that lists Drata hosts in its own configuration is not misread. |
| **Trust-centre buttons and offered documents are not pressure** | "Start your security review", "Request access", "Get access", offered DPAs and subprocessor lists show the company *answering* reviews. |
| **Audit intent must look forward** | Only a certification in progress, or a security/GRC job post 90 days old or newer, counts as "preparing for an audit". A held certificate, a trust centre or a timing score alone never qualifies an account. |
| **Mature programme → nurture** | Held certificate plus no forward signal means "check back later", not outreach. |
| **JavaScript trust centres** | When a trust centre is drawn by JavaScript, its certifications are marked *unknown*, never "none claimed". |
| **Own pages only for "is it SaaS?"** | Customer stories, blog posts and job ads describe other companies; the word "SaaS" only counts in the company's own title or description. |
| **Industry needs two mentions** | Its own compliance (HIPAA) or insurance ("Cyber Insurance") is not a customer industry; one passing mention is not enough. |
| **Customer size needs a count or a named scale** | Testimonials do not count; "Fortune 500" is a scale claim, not a count of 500. |
| **Stale drafts are withdrawn** | If new evidence or a rule change disqualifies an account, its pending draft leaves the desk and can never be signed off. |
| **Lessons never carry facts between accounts** | A reviewer sentence with numbers, money or names is never reused on another account. |


Open `output/company_reports/rootly-com.md` for the full journey. Scores change when Claude extraction is enabled,
since it reads context better than regex rules.

### One full prospect journey: Rootly (all evidence is real and cited in the report)

1. **Research** — read 8 pages, including `rootly.com/security` and the SafeBase trust centre `security.rootly.com`.
2. **Buying moments** — *"SOC2, HIPAA, GDPR compliant…"* (security page); *"Rootly Trust Center | Powered by
   SafeBase"*; *"Start your security review"*; *"Loved by fast-growing startups and the Fortune 500."*
3. **Research agent** — round 1 targeted the blog, careers and trust centre to answer *stage*, *hiring* and
   *timing* questions. Timing rose from 17 to 36 and the decision changed from `not_qualified` to `qualified`
   (logged in the report).
4. **Decision-maker** — Quentin Rousseau, *CTO and Co-founder*, read from rootly.com/about and ranked above the
   CEO. No email was found because Hunter isn't configured, and the system says so instead of guessing.
5. **Pain point** (observed) — security questionnaires slowing enterprise deals.
6. **Email** — hook: *your trust centre says "Start your security review"*.

---

## Tests (`pytest -q` → **108 passed**)

| Scenario required | Test |
|---|---|
| 1 Website unreachable | `test_scraper::test_unreachable_website_does_not_crash` |
| 2 Very little information | `test_scraper::test_very_little_information_is_insufficient_not_rejected` |
| 3 No compliance on homepage, security page exists | `test_scraper::test_security_page_found_by_research_agent` |
| 4 Not a SaaS business | `test_qualification::test_non_saas_is_not_qualified_even_with_security_words` |
| 5 SaaS, no buying signals | `test_qualification::test_saas_without_buying_signals_is_nurture_not_outreach` |
| 6 Qualified, no decision-maker | `test_contact_discovery::test_no_decision_maker_flags_for_review` |
| 7 Hunter returns multiple contacts | `test_contact_discovery::test_hunter_multiple_contacts_ranked_by_relevance_not_seniority` |
| 8 Incomplete contact mapping | `test_contact_discovery::test_incomplete_manual_mapping_rows_are_skipped` |
| 9 Claude returns invalid JSON | `test_qualification::test_invalid_json_from_claude_is_repaired` (+ persistent-failure fallback) |
| 10 API request fails | `test_qualification::test_api_request_failure_falls_back_cleanly` |
| 11 Gmail credentials missing | `test_email_safety::test_missing_gmail_credentials_reported_not_faked` |
| 12 Send to non-test address | `test_email_safety` — 11 bypass attempts, Cc/Bcc/Resent, tampered `To`, unset `TEST_TO_EMAIL` |
| + Evidence Map & review gate | `test_evidence_map_and_review`: 3-yes qualify, 2-yes + unknown qualify-and-flag, audit unknown → nurture, non-SaaS short-circuit, worst case → human, enrichment feeds the gate, news filter, nothing sent before approval, edited text is what's sent, >50% heavy-edit metric |
| + Revenue & conversion | `test_revenue`: measured vs estimated, funnel maths, in-progress ≠ lost, EV ranking, recorded deal value overrides ACV, optimiser only promotes supported pain points |
| + Credential preflight | `test_preflight` — verdicts per integration, keys never echoed, SMTP check logs in but cannot send |

The suite also covers robots.txt, cleaning, link discovery, caching, double-count prevention, missing ≠ negative,
staleness and competitor penalties, grounding of invented claims (fallback and Claude), testimonial filtering,
email rules, the no-hook → no-email rule, dry-run never sending, and pipeline isolation + resume.

---

## Defending the system to faculty

- **"Why this company?"** Point at the ICP table in the report: each point links to an evidence ID, and the
  appendix resolves that ID to a URL and a verbatim quote. Nothing is scored that can't be clicked and checked.
- **"Why now?"** Fit and timing are separate. incident.io is a good fit with no current trigger, so the system
  says *nurture* instead of manufacturing urgency.
- **"How do you know the AI didn't make it up?"** Every extracted claim must quote the page verbatim or it is
  dropped (`ground_evidence`). The test suite proves that an invented SOC 2 claim gets dropped.
- **"Why this person?"** The ranking explains itself, e.g. *"a security function exists, so the CTO is one step
  removed"*. The alternatives and their scores are listed.
- **"What if it's wrong?"** Every report ends with *WHAT COULD MAKE THIS DECISION WRONG?*, built from data:
  inferred vs explicit counts, unanswered questions, stale years, contradictions, incumbent tools.
- **"Could it spam real prospects?"** No. The prospect's address is never passed as a destination, and two
  independent guards plus 20+ tests block every other route.

## Known limitations

- Revenue figures are only as real as the outcomes logged. Until outcomes exist, expected revenue rests on
  placeholder ACV and conversion assumptions; edit `data/revenue_assumptions.json`.

- Fallback extraction is keyword-based and can misread context. Reports label it, and confidence is capped.
- Sites that block bots (403) are recorded as restricted and never bypassed, so some pages stay unread.
- The team-page provider only finds leaders a company publishes about itself. Hunter or a manual CSV is needed for
  verified emails.
- The weights are a documented starting hypothesis. Calibrate them against real won/lost deals.
