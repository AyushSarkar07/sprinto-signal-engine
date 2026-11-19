"""The Evidence Map: the Go / No-Go gate, written down as data before any scoring.

One row per question we must answer to qualify a company (the ICP from the planning whiteboard). Each
row states the specific fact that settles it, where that fact usually lives, a code-checkable
"sufficient when" rule, how many tries (pages read from its sources) it is worth, what happens if it
stays unanswered, and whether one answer short-circuits the whole assessment.

Decision rule over the three CORE questions (SaaS, growth stage, audit intent):
  * any short-circuit                        → DROP (or hand to account management for existing customers)
  * a core question answered NO              → DROP, or NURTURE when only audit intent is missing
  * all three YES                            → QUALIFY
  * two YES + one UNKNOWN                    → the unknown row's "If unanswered" rule: QUALIFY-AND-FLAG
                                               (review gate checks it), or NURTURE when the unknown is audit intent
  * otherwise                                → HAND TO A HUMAN (never an automatic rejection)
Supporting questions (clients, industry, cloud stack) never gate; they feed priority and the email.
Worst case — site unreachable or nearly empty: hand to a human, never reject.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from src.models import Evidence, ExtractionResult, ScrapeRecord

Answer = Literal["yes", "no", "unknown"]
GateDecision = Literal["QUALIFY", "QUALIFY_AND_FLAG", "NURTURE", "DROP", "HAND_TO_HUMAN"]
TIMING_YES = 35   # same bar as qualification THRESHOLDS["timing_qualify"]
TIMING_NO = 15
FUNDING_MAX_MONTHS = 24      # an older round says little about today's stage
AUDIT_SIGNAL_MAX_DAYS = 90   # a dated audit signal (e.g. a job post) must be this fresh to count as "now"
TRUST_VENDORS = ("Vanta", "Drata", "Secureframe", "Thoropass", "Sprinto")
TODAY = dt.date.today


class MapAnswer(BaseModel):
    key: str
    question: str
    core: bool
    role: str = "core"                      # gate (can only drop) | core (decides) | supporting (informs)
    answer: Answer
    basis: str
    evidence: list[str] = []
    tries_used: int = 0
    limit: int = 0
    if_unanswered: str = ""
    short_circuit_hit: Optional[str] = None


@dataclass(frozen=True)
class Question:
    key: str
    question: str
    data: str
    where: tuple[str, ...]          # page categories (scraper.classify_url) + external sources
    sufficient_when: str
    limit: int
    if_unanswered: str
    short_circuit: str
    core: bool
    check: Callable[["Ctx"], tuple[Answer, str, list[Evidence], Optional[str]]]


@dataclass
class Ctx:
    r: ExtractionResult
    rec: ScrapeRecord
    timing: int

    def evs(self, *cats: str) -> list[Evidence]:
        return [e for e in self.r.all_evidence() if e.category in cats]


def _cite(evs: list[Evidence], n: int = 2) -> list[str]:
    return [f"\"{e.excerpt[:140]}\" — {e.source_url}" for e in evs[:n]]


def months_old(text: str) -> Optional[int]:
    """Age in months of the newest 'YYYY-MM(-DD)' or bare year in the text; None if undated."""
    ym = [(int(y), int(m)) for y, m in re.findall(r"\b(20[0-3]\d)-(0[1-9]|1[0-2])\b", text)]
    if not ym:
        ym = [(int(y), 6) for y in re.findall(r"\b(20[0-3]\d)\b", text)]  # bare year: assume mid-year
    if not ym:
        return None
    y, m = max(ym)
    now = TODAY()
    return (now.year - y) * 12 + (now.month - m)


def days_old(text: str) -> Optional[int]:
    m = re.search(r"posted: (\d{4}-\d{2}-\d{2})", text)
    if not m:
        return None
    return (TODAY() - dt.date.fromisoformat(m.group(1))).days


def headcount(text: Optional[str]) -> Optional[int]:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None


# ---------------------------------------------------------------- checks (code decides "sufficient")

def _saas(c: Ctx):
    p = c.r.company_profile
    if p.is_saas is True:
        return "yes", "Subscription-software indicators found (pricing/trial/login/API).", p.is_saas_evidence, None
    if p.is_saas is False:
        return "no", "Evidence describes a non-software business.", c.evs("non_saas_indicator"), \
            "Not SaaS — outside Sprinto's ICP whatever else is true."
    return "unknown", "No SaaS indicators on the pages read.", [], None


def _growth(c: Ctx):
    p = c.r.company_profile
    stage = (p.funding_stage.value or "").lower()
    n = headcount(p.employee_range.value)
    ev = [e for e in (p.funding_stage.evidence, p.employee_range.evidence) if e]
    age = months_old(p.funding_stage.evidence.excerpt) if p.funding_stage.evidence else None
    stale = age is not None and age > FUNDING_MAX_MONTHS
    stage_fit = bool(re.search(r"series [abc]\b", stage)) and not stale
    size_fit = n is not None and 50 <= n <= 200
    if stage_fit or size_fit:
        parts = ([p.funding_stage.value] if stage_fit else []) + ([p.employee_range.value] if size_fit else [])
        note = f" The {p.funding_stage.value} round is {age} months old (limit {FUNDING_MAX_MONTHS}), so only headcount counts." if stale else ""
        return "yes", f"Inside the Series A–C / 50–200 employee band ({', '.join(parts)}).{note}", ev, None
    stage_out = bool(re.search(r"series [d-z]\b|ipo|publicly traded|pre-seed", stage))
    size_out = n is not None and not 50 <= n <= 200
    if (stage_out or size_out) and not (stage_fit or size_fit):
        parts = ([p.funding_stage.value] if stage_out else []) + ([p.employee_range.value] if size_out else [])
        return "no", f"Outside the Series A–C / 50–200 employee band ({', '.join(parts)}).", ev, None
    if stale:
        return "unknown", f"Only a {p.funding_stage.value} round from {age} months ago (limit {FUNDING_MAX_MONTHS}); no headcount found.", ev, None
    return "unknown", "Neither funding stage nor headcount stated on the pages read.", ev, None


def _audit(c: Ctx):
    """Preparing for an audit means something FORWARD-looking: a certification under way, or a security/GRC hire.
    A trust centre, a held certificate, an offered DPA or a "start your security review" button all show a programme
    that already exists; on their own they are a reason to wait, not a buying moment."""
    sprinto = [e for e in c.r.other_signals if e.category == "competitor_platform" and "Sprinto" in e.finding]
    if sprinto:
        return "no", "Sprinto-powered trust centre detected.", sprinto, "Existing Sprinto customer: route to account management."
    in_prog = [e for e in c.evs("certification_in_progress") if e.evidence_type == "explicit"]
    hires = [e for e in c.evs("compliance_hiring") if e.evidence_type == "explicit"]
    stale = [e for e in hires if (d := days_old(e.excerpt)) is not None and d > AUDIT_SIGNAL_MAX_DAYS]
    hires = [e for e in hires if e not in stale]
    forward = in_prog + hires
    if forward:
        parts = (["a certification still in progress"] if in_prog else []) + ([f"{len(hires)} open security/compliance role(s)"] if hires else [])
        dated = [d for e in hires if (d := days_old(e.excerpt)) is not None]
        note = f"; newest job post is {min(dated)} days old" if dated else ("; job post undated, check it is still open" if hires else "")
        return "yes", "Forward-looking signal: " + " and ".join(parts) + note + ".", forward, None
    held = [e for e in c.evs("certification_held")]
    platform = [e for e in c.r.compliance_signals.trust_centre_evidence if e.finding.startswith("Trust centre runs on")]
    if held or platform:
        what = []
        if held:
            what.append("already holds " + ", ".join(sorted({n for e in held for n in ("SOC 2", "ISO 27001") if n.replace(" ", "") in e.excerpt.replace(" ", "").upper().replace("SOC2", "SOC2")})) or "a certification")
        if platform:
            what.append("runs its trust centre on " + platform[0].finding.split(" on ")[-1])
        extra = f"; {len(stale)} older job post(s) ignored" if stale else ""
        return "no", f"Mature programme: {' and '.join(what)}. Nothing read points to a new audit{extra}.", (held[:1] + platform[:1]), None
    tries = _tries(c.rec, ("security", "trust", "careers", "compliance"))
    if tries >= 1:
        return "no", f"No certification under way and no security/compliance hire on the {tries} security, trust or careers page(s) read.", [], None
    return "unknown", "No security, trust or careers page could be read, so audit plans are unknown.", [], None


def _certs(c: Ctx):
    s = c.r.compliance_signals
    soc2 = [e for e in s.soc2_mentions if e.category == "certification_held"]
    iso = [e for e in s.iso27001_mentions if e.category == "certification_held"]
    gdpr = s.gdpr_mentions
    if soc2 and iso and gdpr:
        return "no", "Already holds SOC 2 and ISO 27001 and states GDPR compliance.", soc2[:1] + iso[:1], \
            "Already certified for every framework Sprinto sells; nothing new to win."
    held = [n for n, x in (("SOC 2", soc2), ("ISO 27001", iso)) if x]
    if held:
        return "yes", f"Holds {', '.join(held)} but not every framework; renewals and the next framework are still open.", soc2[:1] + iso[:1], None
    if s.soc2_mentions or s.iso27001_mentions:
        return "yes", "Frameworks mentioned but not confirmed as held.", (s.soc2_mentions + s.iso27001_mentions)[:2], None
    js_portal = [p for p in c.rec.ok_pages() if p.text.startswith("Trust centre platform:")]
    if js_portal:
        return "unknown", "Its trust centre is drawn by JavaScript, so the certifications it lists could not be read.", [], None
    pages = _tries(c.rec, ("security", "trust", "compliance"))
    return ("yes" if pages else "unknown"), ("No certification claimed on the security/trust pages read." if pages
                                              else "No security or trust page read yet."), [], None


def _vendor(c: Ctx):
    hits = [e for e in c.r.other_signals if e.category == "competitor_platform"]
    for e in hits:
        page_cat = next((p.category for p in c.rec.pages_scraped if p.url == e.source_url), "")
        vendor = next((v for v in TRUST_VENDORS if v.lower() in (e.finding + e.excerpt).lower()), None)
        on_trust = page_cat in ("trust", "security", "compliance") or re.search(r"trust\.|security\.", e.source_url) \
            or re.search(r"powered by|managed (with|by)|Trust centre platform:", e.excerpt, re.I)
        if vendor and on_trust and vendor != "Sprinto":
            return "no", f"Trust centre runs on {vendor} (detected in its page source).", [e], \
                f"Already uses {vendor}; a displacement, not a first purchase. Not cold outbound."
    trust_tool = [e for e in c.r.compliance_signals.trust_centre_evidence if e.finding.startswith("Trust centre runs on")]
    if trust_tool:
        return "yes", f"{trust_tool[0].finding}, a trust-centre tool rather than compliance automation.", trust_tool[:1], None
    if hits:
        return "yes", "A compliance vendor is mentioned (e.g. as a customer), but not as the platform behind their trust centre.", hits[:1], None
    pages = _tries(c.rec, ("security", "trust", "compliance"))
    return ("yes" if pages else "unknown"), ("No compliance platform behind the trust/security pages read." if pages
                                              else "No security or trust page read yet."), [], None


def _clients(c: Ctx):
    # Testimonials ("we love it") say nothing about size; only counts and named large-company claims do.
    evs = [e for e in c.evs("enterprise_customer") if not re.search(r"[\u201c\"]|\b(we|our|us|I)\b", e.excerpt)]
    counted = [e for e in evs if (n := headcount(re.sub(r"\b(19|20)\d\d\b|Fortune ?\d+|Global ?\d+|Inc\.? ?\d+", "", e.excerpt))) and n >= 50]
    big = [e for e in evs if re.search(r"Fortune ?(100|500)|Global 2000|largest|enterprises like|leading (banks|enterprises)", e.excerpt, re.I)]
    if counted or big:
        return "yes", ("A stated customer count of 50 or more." if counted else "Names Fortune / Global 2000 scale customers."), (counted + big)[:2], None
    if evs:
        return "unknown", "Customer references exist but size and count are unclear.", evs, None
    return "unknown", "No customer references found.", [], None


def _industry(c: Ctx):
    # Needs two separate mentions, or one in the company's own self-description (homepage/about), to count.
    reg = c.evs("regulated_industry")
    own = [e for e in reg if next((p.category for p in c.rec.pages_scraped if p.url == e.source_url), "") in ("homepage", "about", "product", "pricing", "enterprise")]
    if not (own or len({e.source_url for e in reg}) >= 2):
        return "unknown", ("Only one passing mention of a regulated industry; not enough to count." if reg
                           else "Customer industries not identified as regulated."), reg[:1], None
    if reg:
        return "yes", "Serves regulated buyers: " + ", ".join(sorted({e.finding.replace("Serves or targets ", "") for e in reg})) + ".", reg, None
    return "unknown", "Customer industries not identified as regulated.", [], None


def _cloud(c: Ctx):
    cloud = r"AWS|Amazon Web Services|GCP|Google Cloud|Azure"
    tech = [e for e in c.r.company_profile.tech_stack if re.search(cloud, e.excerpt + e.finding)]
    if tech:
        return "yes", "Runs on a major cloud (Sprinto integrates with AWS/GCP/Azure).", tech, None
    for p in c.rec.ok_pages():
        m = re.search(rf"Technologies detected: [^.]*?\b({cloud})\b", p.text) if p.category == "enrichment" else None
        if m:
            return "yes", f"{m.group(1)} in the technologies list of {p.title}.", \
                [Evidence(finding=f"Cloud: {m.group(1)}", source_url=p.url, excerpt=m.group(0), confidence=0.6,
                          evidence_type="inferred", category="other")], None
    return "unknown", "Cloud provider not stated.", [], None


QUESTIONS: list[Question] = [
    Question("certifications", "Is there still something to certify?", "Which of SOC 2 / ISO 27001 / GDPR they already hold",
             ("security", "trust", "compliance"), "not all of SOC 2 + ISO 27001 + GDPR held", 2, "Treat as pass",
             "Holds all three → DROP", False, _certs),
    Question("competitor_vendor", "Is it free of a competing compliance platform?", "Vanta / Drata / Secureframe / Thoropass etc. powering the trust centre (read from the page source)",
             ("trust", "security"), "no competitor vendor behind the trust centre", 2, "Treat as pass",
             "Competitor trust centre → DROP", False, _vendor),
    Question("saas", "Is it a SaaS business?", "Sells subscription software: pricing per seat/month, free trial, login, API",
             ("homepage", "pricing", "product"), "is_saas is True with ≥1 SaaS indicator", 3,
             "Flag at review gate", "Non-SaaS → DROP", True, _saas),
    Question("growth_stage", "Is it Series A–C / 50–200 employees?", "Named funding round, or a headcount statement",
             ("news (search API)", "about", "careers", "company enrichment (Apollo)"),
             f"Series A/B/C within {FUNDING_MAX_MONTHS} months, or headcount 50 ≤ n ≤ 200", 3, "Flag at review gate", "—", True, _growth),
    Question("audit_intent", "Is it preparing for an audit (SOC 2 / ISO 27001)?",
             "Certification in progress, security/GRC hire, security-review process",
             ("security", "trust", "careers", "compliance"),
             "a certification in progress, or a security/GRC hire (job posts ≤ 90 days old); trust centres, held certificates and offered DPAs do not count", 4, "Nurture (right company, wrong time)",
             "Sprinto trust centre → existing customer", True, _audit),
    Question("clients", "Does it have >50 clients / larger customers?", "'Trusted by 500+ teams', named enterprise logos",
             ("homepage", "customers"), "stated count ≥ 50 or Fortune / Global 2000 customers; testimonials do not count", 2, "Neutral", "—", False, _clients),
    Question("industry", "Does it serve a regulated industry?", "Healthcare, fintech, insurance, government customers",
             ("homepage", "about", "customers"), "two separate mentions, or one in their own self-description", 2, "Neutral", "—", False, _industry),
    Question("cloud_stack", "Is it on AWS / GCP / Azure?", "Explicit 'hosted on AWS' statement",
             ("security", "careers", "company enrichment (Apollo)"), "explicit infrastructure statement", 2, "Neutral", "—",
             False, _cloud),
]


GATES = {"certifications", "competitor_vendor"}


def _tries(rec: ScrapeRecord, cats) -> int:
    return sum(1 for p in rec.ok_pages() if p.category in cats)


def evaluate(r: ExtractionResult, rec: ScrapeRecord, timing: int) -> list[MapAnswer]:
    c = Ctx(r, rec, timing)
    out = []
    for q in QUESTIONS:
        ans, basis, evs, sc = q.check(c)
        role = "core" if q.core else ("gate" if q.key in GATES else "supporting")
        out.append(MapAnswer(key=q.key, question=q.question, core=q.core, role=role, answer=ans, basis=basis, evidence=_cite(evs),
                             tries_used=_tries(rec, q.where), limit=q.limit, if_unanswered=q.if_unanswered,
                             short_circuit_hit=sc))
    return out


def decide(answers: list[MapAnswer], rec: ScrapeRecord, confidence: float, confidence_min: float = 0.45) \
        -> tuple[GateDecision, str, list[str]]:
    """Return (decision, one-line reason, flags for the human review gate)."""
    if rec.scraping_status == "failed" or len(rec.raw_text) < 300:
        return "HAND_TO_HUMAN", "Worst case: the site could not be read — a human decides; this is not a rejection.", []
    for a in answers:
        if a.short_circuit_hit:
            return "DROP", f"Short-circuit on '{a.question}': {a.short_circuit_hit}", []
    core = [a for a in answers if a.core]
    yes = [a for a in core if a.answer == "yes"]
    no = [a for a in core if a.answer == "no"]
    unknown = [a for a in core if a.answer == "unknown"]
    if no:
        saas_yes = any(a.key == "saas" and a.answer == "yes" for a in core)
        if [a.key for a in no] == ["audit_intent"] and saas_yes:
            gap = [a.question for a in unknown]
            return "NURTURE", ("A SaaS fit, but nothing shows an audit coming: check back later."
                               + (f" Also unknown: {gap[0]}" if gap else "")), []
        return "DROP", "Fails ICP: " + "; ".join(f"{a.question} → no ({a.basis})" for a in no), []
    flags = [f"Unknown: {a.question} — {a.basis} Verify before sending." for a in unknown]
    if len(yes) == 3:
        if confidence < confidence_min:
            return "QUALIFY_AND_FLAG", f"All core questions answered yes, but evidence confidence is low ({confidence}).", \
                [f"Low evidence confidence ({confidence}) — double-check the cited sources."]
        return "QUALIFY", "SaaS, in the growth band, and preparing for an audit — all backed by cited evidence.", []
    if len(yes) == 2 and len(unknown) == 1:
        # The unknown row's own "If unanswered" rule applies: an unknown buying moment means nurture, not outreach.
        if unknown[0].if_unanswered.startswith("Nurture"):
            return "NURTURE", f"ICP fit, but '{unknown[0].question}' stayed unanswered after research — right company, wrong time → nurture.", []
        return "QUALIFY_AND_FLAG", f"Two of three core questions answered yes; '{unknown[0].question}' is unknown.", flags
    return "HAND_TO_HUMAN", f"Only {len(yes)} of 3 core questions answered — too little to qualify or reject automatically.", flags


def map_table() -> list[list[str]]:
    """The evidence map itself, for the README / reports."""
    return [[q.question, q.data, ", ".join(q.where), q.sufficient_when, f"{q.limit} pages", q.if_unanswered, q.short_circuit,
             "core" if q.core else ("gate" if q.key in GATES else "supporting")] for q in QUESTIONS]
