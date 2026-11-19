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

import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from src.models import Evidence, ExtractionResult, ScrapeRecord

Answer = Literal["yes", "no", "unknown"]
GateDecision = Literal["QUALIFY", "QUALIFY_AND_FLAG", "NURTURE", "DROP", "HAND_TO_HUMAN"]
TIMING_YES = 35   # same bar as qualification THRESHOLDS["timing_qualify"]
TIMING_NO = 15


class MapAnswer(BaseModel):
    key: str
    question: str
    core: bool
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
    stage_fit = bool(re.search(r"series [abc]\b", stage))
    size_fit = n is not None and 50 <= n <= 200
    if stage_fit or size_fit:
        parts = ([p.funding_stage.value] if stage_fit else []) + ([p.employee_range.value] if size_fit else [])
        return "yes", f"Inside the Series A–C / 50–200 employee band ({', '.join(parts)}).", ev, None
    stage_out = bool(re.search(r"series [d-z]\b|ipo|publicly traded|pre-seed", stage))
    size_out = n is not None and not 50 <= n <= 200
    if (stage_out or size_out) and not (stage_fit or size_fit):
        parts = ([p.funding_stage.value] if stage_out else []) + ([p.employee_range.value] if size_out else [])
        return "no", f"Outside the Series A–C / 50–200 employee band ({', '.join(parts)}).", ev, None
    return "unknown", "Neither funding stage nor headcount stated on the pages read.", ev, None


def _audit(c: Ctx):
    explicit = [e for e in c.evs("certification_in_progress", "compliance_hiring", "security_review_pressure")
                if e.evidence_type == "explicit"]
    sprinto = [e for e in c.r.other_signals if e.category == "competitor_platform" and "Sprinto" in e.finding]
    if sprinto:
        return "no", "Sprinto-powered trust centre detected.", sprinto, "Existing Sprinto customer — route to account management."
    if explicit or c.timing >= TIMING_YES:
        basis = "Audit work, compliance hiring or security-review pressure observed" if explicit else \
            f"Buying-timing evidence above the bar ({c.timing}/100)"
        return "yes", basis + ".", explicit or c.evs("certification_held", "trust_centre"), None
    tries = _tries(c.rec, ("security", "trust", "careers", "compliance"))
    if c.timing < TIMING_NO and tries >= 1:
        return "no", f"No audit preparation found after reading {tries} security/trust/careers page(s) (timing {c.timing}/100).", [], None
    return "unknown", f"Weak or unread audit signals (timing {c.timing}/100, {tries} relevant page(s) read).", [], None


def _clients(c: Ctx):
    evs = c.evs("enterprise_customer")
    counted = [e for e in evs if (n := headcount(re.sub(r"\b(19|20)\d\d\b", "", e.excerpt))) and n >= 50]
    if counted or len(evs) >= 2:
        return "yes", "Customer base of meaningful size / named larger customers.", counted or evs, None
    if evs:
        return "unknown", "Customer references exist but size and count are unclear.", evs, None
    return "unknown", "No customer references found.", [], None


def _industry(c: Ctx):
    reg = c.evs("regulated_industry")
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
    Question("saas", "Is it a SaaS business?", "Sells subscription software: pricing per seat/month, free trial, login, API",
             ("homepage", "pricing", "product"), "is_saas is True with ≥1 SaaS indicator", 3,
             "Flag at review gate", "Non-SaaS → DROP", True, _saas),
    Question("growth_stage", "Is it Series A–C / 50–200 employees?", "Named funding round, or a headcount statement",
             ("news (search API)", "about", "careers", "company enrichment (Apollo)"),
             "funding matches Series A/B/C, or headcount 50 ≤ n ≤ 200", 3, "Flag at review gate", "—", True, _growth),
    Question("audit_intent", "Is it preparing for an audit (SOC 2 / ISO 27001)?",
             "Certification in progress, security/GRC hire, security-review process",
             ("security", "trust", "careers", "compliance"),
             "explicit in-progress/hiring/review evidence, or timing score ≥ 35", 4, "Nurture (right company, wrong time)",
             "Sprinto trust centre → existing customer", True, _audit),
    Question("clients", "Does it have >50 clients / larger customers?", "'Trusted by 500+ teams', named enterprise logos",
             ("homepage", "customers"), "customer count ≥ 50 or ≥ 2 enterprise references", 2, "Neutral", "—", False, _clients),
    Question("industry", "Does it serve a regulated industry?", "Healthcare, fintech, insurance, government customers",
             ("homepage", "news"), "regulated_industry evidence present", 1, "Neutral", "—", False, _industry),
    Question("cloud_stack", "Is it on AWS / GCP / Azure?", "Explicit 'hosted on AWS' statement",
             ("security", "careers", "company enrichment (Apollo)"), "explicit infrastructure statement", 2, "Neutral", "—",
             False, _cloud),
]


def _tries(rec: ScrapeRecord, cats) -> int:
    return sum(1 for p in rec.ok_pages() if p.category in cats)


def evaluate(r: ExtractionResult, rec: ScrapeRecord, timing: int) -> list[MapAnswer]:
    c = Ctx(r, rec, timing)
    out = []
    for q in QUESTIONS:
        ans, basis, evs, sc = q.check(c)
        out.append(MapAnswer(key=q.key, question=q.question, core=q.core, answer=ans, basis=basis, evidence=_cite(evs),
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
        if [a.key for a in no] == ["audit_intent"] and len(yes) == 2:
            return "NURTURE", "ICP fit, but no audit preparation observed — right company, wrong time.", []
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
             "core" if q.core else "supporting"] for q in QUESTIONS]
