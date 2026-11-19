"""Step 3a — Transparent, deterministic qualification.

Scores are computed in code, not by an LLM, so every point can be traced to an evidence ID.
Three dimensions are kept separate on purpose:
  ICP fit           — is this the kind of company Sprinto sells to?
  Buying timing     — is there evidence compliance matters *now*?
  Evidence confidence — how much should we trust the two numbers above?

Rules that keep the scores honest:
  * within one score, a single piece of evidence can earn points for one criterion only;
  * points scale with evidence confidence (weak / inferred evidence earns less);
  * stale evidence (years ≥3 old) is already halved at extraction time;
  * missing information earns zero — it is NOT treated as negative evidence;
  * the deterministic fallback extractor caps confidence (it is not AI-verified).
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from src.evidence_map import decide, evaluate
from src.llm import ClaudeJSON, LLMUnavailable, load_prompt
from src.models import CriterionScore, Evidence, ExtractionResult, Qualification, ScrapeRecord

from pydantic import BaseModel

# ---- Weights (documented in README "Scoring framework"). Starting weights, not facts. ----
ICP_WEIGHTS = {
    "SaaS business model": 25,
    "Relevant growth stage (Series A–C)": 15,
    "Enterprise customer orientation": 20,
    "Relevant customer industry": 10,
    "Company scaling signals": 10,
    "Security / compliance complexity": 20,
}
TIMING_WEIGHTS = {
    "Explicit SOC 2 / ISO 27001 / audit requirement": 30,
    "Enterprise security review / procurement pressure": 25,
    "Security or compliance hiring": 20,
    "Trust centre or compliance activity": 10,
    "Recent enterprise expansion / scaling": 15,
}
THRESHOLDS = {"icp_qualify": 55, "timing_qualify": 35, "confidence_min": 0.45, "icp_reject": 35}
FALLBACK_CONFIDENCE_CAP = 0.75


def _ev_points(evs: list[Evidence], max_points: float, per_item: float) -> float:
    """Diminishing sum: each item contributes per_item × confidence, capped at max_points."""
    total = 0.0
    for e in sorted(evs, key=lambda x: x.confidence, reverse=True):
        total += per_item * e.confidence * (1.0 if e.evidence_type == "explicit" else 0.7)
    return round(min(max_points, total), 1)


class _Claimer:
    """Ensures one evidence item is rewarded by at most one criterion within a score."""

    def __init__(self):
        self.used: set[str] = set()

    def take(self, evs: list[Evidence]) -> list[Evidence]:
        out = [e for e in evs if e.id not in self.used]
        self.used.update(e.id for e in out)
        return out


def _crit(name: str, weights: dict, points: float, rationale: str, evs: list[Evidence]) -> CriterionScore:
    return CriterionScore(criterion=name, max_points=weights[name], points=round(points, 1), rationale=rationale,
                          evidence_ids=[e.id for e in evs])


def score_icp(r: ExtractionResult) -> list[CriterionScore]:
    p, c = r.company_profile, r.compliance_signals
    claim = _Claimer()
    W = ICP_WEIGHTS
    out = []

    saas_ev = claim.take([e for e in p.is_saas_evidence if e.category == "saas_indicator"])
    if p.is_saas is True:
        conf = max([e.confidence for e in saas_ev] or [0.6])
        pts, why = W["SaaS business model"] * min(1.0, 0.6 + conf * 0.5), f"SaaS model supported by {len(saas_ev)} indicator(s)."
    elif p.is_saas is False:
        pts, why = 0, "Evidence indicates a non-SaaS business."
    else:
        pts, why = 0, "SaaS model not established from available pages (missing, not negative)."
    out.append(_crit("SaaS business model", W, pts, why, saas_ev))

    stage = (p.funding_stage.value or "").lower()
    stage_ev = claim.take([p.funding_stage.evidence] if p.funding_stage.evidence else [])
    emp_ev = claim.take([p.employee_range.evidence] if p.employee_range.evidence else [])
    if re.search(r"series [abc]\b", stage):
        pts, why = 15 * (stage_ev[0].confidence if stage_ev else 0.8) / 0.85, f"Explicit {p.funding_stage.value} — inside Sprinto's sweet spot."
    elif re.search(r"series [d-f]\b", stage):
        pts, why = 8, f"{p.funding_stage.value} — later than the typical Series A–C buyer."
    elif "seed" in stage:
        pts, why = 6, "Seed stage — may be early for a compliance platform unless enterprise deals demand it."
    elif emp_ev:
        pts, why = 7, f"No funding stage stated; headcount mention ('{p.employee_range.value}') used as a weak proxy."
    else:
        pts, why = 0, "Growth stage unknown (missing, not negative)."
    out.append(_crit("Relevant growth stage (Series A–C)", W, min(15, pts), why, stage_ev + emp_ev))

    ent_ev = claim.take(p.enterprise_customers + [e for e in c.enterprise_security_signals if e.category == "enterprise_orientation"])
    pts = _ev_points(ent_ev, 20, 9)
    out.append(_crit("Enterprise customer orientation", W, pts,
                     f"{len(ent_ev)} enterprise reference(s) / enterprise-tier signals." if ent_ev else "No enterprise orientation observed.", ent_ev))

    ind_ev = claim.take(p.customer_industries)
    reg = [e for e in ind_ev if e.category == "regulated_industry"]
    pts = 10 * max([e.confidence for e in reg] or [0]) / 0.55 if reg else (4 if ind_ev else 0)
    out.append(_crit("Relevant customer industry", W, min(10, pts),
                     ("Serves regulated industries: " + ", ".join(e.finding.replace("Serves or targets ", "") for e in reg)) if reg
                     else ("Industries identified but not regulated." if ind_ev else "Customer industries not identified."), ind_ev))

    scale_ev = claim.take([g for g in r.growth_signals if g.category in ("engineering_hiring", "expansion", "funding")])
    pts = _ev_points(scale_ev, 10, 3.5)
    out.append(_crit("Company scaling signals", W, pts,
                     f"{len(scale_ev)} scaling signal(s) (hiring, expansion, funding)." if scale_ev else "No scaling signals observed.", scale_ev))

    sec_ev = claim.take(c.security_pages + c.gdpr_mentions + [e for e in c.soc2_mentions + c.iso27001_mentions])
    pts = _ev_points(sec_ev, 20, 5)
    out.append(_crit("Security / compliance complexity", W, pts,
                     f"{len(sec_ev)} security/compliance artefact(s) on the site." if sec_ev else "No security/compliance content observed.", sec_ev))
    return out


def score_timing(r: ExtractionResult) -> tuple[list[CriterionScore], list[str]]:
    c = r.compliance_signals
    claim = _Claimer()
    W = TIMING_WEIGHTS
    out, penalties = [], []
    certs = c.soc2_mentions + c.iso27001_mentions + [e for e in c.compliance_hiring if e.category == "certification_in_progress"]

    in_prog = claim.take([e for e in certs if e.category == "certification_in_progress"])
    held = claim.take([e for e in certs if e.category == "certification_held"])
    mention = claim.take([e for e in certs if e.category == "compliance_mention"])
    if in_prog:
        pts, why = 30 * max(e.confidence for e in in_prog) / 0.9, "Certification work appears to be in progress / audit window open."
    elif held:
        pts, why = 15 + min(5, len({e.source_url for e in held}) * 2), "Certification already held — renewal and multi-framework expansion, not a first audit."
    elif mention:
        pts, why = 8, "Frameworks mentioned without a stated status."
    else:
        pts, why = 0, "No explicit audit or certification requirement observed."
    out.append(_crit("Explicit SOC 2 / ISO 27001 / audit requirement", W, min(30, pts), why, in_prog + held + mention))

    rev = claim.take([e for e in c.enterprise_security_signals if e.category == "security_review_pressure"])
    pts = _ev_points(rev, 25, 12)
    out.append(_crit("Enterprise security review / procurement pressure", W, pts,
                     f"{len(rev)} reference(s) to security reviews, DPAs or procurement." if rev else "No security-review pressure observed.", rev))

    hire = claim.take([e for e in c.compliance_hiring if e.category == "compliance_hiring"])
    eng = claim.take([g for g in r.growth_signals if g.category == "engineering_hiring"])
    pts = _ev_points(hire, 20, 14) + (min(5, len(eng) * 1.5) if eng else 0)
    out.append(_crit("Security or compliance hiring", W, min(20, pts),
                     (f"{len(hire)} security/compliance role(s) open" if hire else "No security roles found")
                     + (f"; {len(eng)} engineering role signal(s)." if eng else "."), hire + eng))

    trust = claim.take(c.trust_centre_evidence)
    pts = 10 * max([e.confidence for e in trust] or [0]) / 0.85 if trust else 0
    out.append(_crit("Trust centre or compliance activity", W, min(10, pts),
                     "Trust centre published." if trust else "No trust centre found.", trust))

    exp = claim.take([g for g in r.growth_signals if g.category in ("expansion", "funding")])
    pts = _ev_points(exp, 15, 8)
    out.append(_crit("Recent enterprise expansion / scaling", W, pts,
                     f"{len(exp)} expansion / funding signal(s)." if exp else "No recent expansion signal.", exp))

    competitors = [e for e in r.other_signals if e.category == "competitor_platform"]
    if competitors:
        names = ", ".join(sorted({e.finding.split(": ")[-1] for e in competitors}))
        penalties.append(f"-10 timing: compliance platform already visible ({names}) — this is a displacement, not a greenfield, conversation.")
    if r.contradictory_information:
        penalties.append(f"-{3 * len(r.contradictory_information)} timing: {len(r.contradictory_information)} contradictory signal(s).")
    return out, penalties


def evidence_confidence(r: ExtractionResult, rec: ScrapeRecord) -> float:
    evs = r.all_evidence()
    if not evs:
        return 0.1
    avg = sum(e.confidence for e in evs) / len(evs)
    explicit_share = sum(1 for e in evs if e.evidence_type == "explicit") / len(evs)
    coverage = 1 - len([m for m in r.missing_information if ":" in m]) / 6
    pages = min(1.0, len(rec.ok_pages()) / 4)
    conf = 0.35 * avg + 0.15 * explicit_share + 0.35 * coverage + 0.15 * pages
    conf -= 0.05 * len(r.contradictory_information)
    if r.provenance == "deterministic_fallback":
        conf = min(conf, FALLBACK_CONFIDENCE_CAP)
    return round(max(0.05, min(1.0, conf)), 2)


def qualify(r: ExtractionResult, rec: ScrapeRecord, research_rounds: int = 0) -> Qualification:
    """Combine the three dimensions into a decision with plain-English reasoning."""
    icp_b = score_icp(r)
    tim_b, penalties = score_timing(r)
    icp = round(sum(c.points for c in icp_b))
    timing = sum(c.points for c in tim_b)
    timing -= sum(int(m.group(1)) for p in penalties for m in [re.match(r"-(\d+) timing", p)] if m)
    timing = max(0, round(timing))
    conf = evidence_confidence(r, rec)
    p = r.company_profile
    missing = [m for m in r.missing_information]
    positives = [f"{c.criterion}: {c.rationale} (+{c.points:g}/{c.max_points})" for c in icp_b + tim_b if c.points > 0]
    negatives = [f"{c.criterion}: {c.rationale}" for c in icp_b + tim_b if c.points == 0]
    negatives += penalties
    reasoning: list[str] = []
    is_existing_sprinto = any("Sprinto" in e.finding for e in r.other_signals if e.category == "competitor_platform")

    # The Evidence Map is the Go / No-Go gate; the scores above explain and rank, they do not overrule it.
    answers = evaluate(r, rec, timing)
    gate, gate_reason, flags = decide(answers, rec, conf, THRESHOLDS["confidence_min"])
    status, action = {"QUALIFY": ("qualified", "outreach"), "QUALIFY_AND_FLAG": ("qualified", "outreach"),
                      "NURTURE": ("not_qualified", "nurture"), "DROP": ("not_qualified", "disqualify"),
                      "HAND_TO_HUMAN": ("insufficient_data", "manual_review")}[gate]
    if is_existing_sprinto:
        reasoning.append("The site appears to use a Sprinto-powered trust centre — likely an existing customer; route to account management, not outbound.")
    reasoning.append(f"Evidence Map → {gate.replace('_', ' ')}: {gate_reason}")
    if gate == "HAND_TO_HUMAN" and (rec.scraping_status == "failed" or len(rec.raw_text) < 300):
        reasoning.append(f"Site read problems: {'; '.join(rec.errors[:2]) or 'very little text'}.")
    reasoning.append(f"Scores: ICP {icp}/100, timing {timing}/100, evidence confidence {conf}.")

    top_icp = sorted(icp_b, key=lambda c: c.points, reverse=True)[:2]
    top_tim = sorted(tim_b, key=lambda c: c.points, reverse=True)[:2]
    reasoning.append("Biggest ICP drivers: " + "; ".join(f"{c.criterion} ({c.points:g}/{c.max_points}) — {c.rationale}" for c in top_icp))
    reasoning.append("Biggest timing drivers: " + "; ".join(f"{c.criterion} ({c.points:g}/{c.max_points}) — {c.rationale}" for c in top_tim))
    if r.provenance == "deterministic_fallback":
        reasoning.append("Extraction ran in deterministic fallback mode (Claude not used); confidence capped at "
                         f"{FALLBACK_CONFIDENCE_CAP}. Results are rule-based, not AI-verified.")

    risks = default_risks(r, icp_b, tim_b, conf)
    return Qualification(qualified=status == "qualified", decision_status=status, recommended_action=action,
                         icp_fit_score=min(100, icp), buying_timing_score=min(100, timing), evidence_confidence=conf,
                         icp_breakdown=icp_b, timing_breakdown=tim_b, penalties=penalties, qualification_reasoning=reasoning,
                         positive_signals=positives, negative_signals=negatives, missing_information=missing,
                         risks_and_uncertainty=risks, secondary_research_performed=research_rounds > 0,
                         research_rounds=research_rounds, provenance=r.provenance, gate_decision=gate,
                         evidence_map=[a.model_dump() for a in answers], review_flags=flags)


def default_risks(r: ExtractionResult, icp_b, tim_b, conf: float) -> list[str]:
    """'What could make this decision wrong?' — generated from the data, not prose templates alone."""
    risks = []
    evs = r.all_evidence()
    inferred = [e for e in evs if e.evidence_type != "explicit"]
    if inferred:
        risks.append(f"{len(inferred)} of {len(evs)} evidence items are inferred rather than explicitly stated.")
    for m in r.missing_information:
        risks.append(f"Unknown: {m.split(': ', 1)[-1]}.")
    stale = [e for e in evs if re.search(r"\b20(1\d|2[0-3])\b", e.excerpt)]
    if stale:
        risks.append(f"{len(stale)} evidence item(s) reference older years — may be outdated (e.g. '{stale[0].excerpt[:80]}').")
    risks += [f"Contradiction: {c}" for c in r.contradictory_information]
    if any(e.category == "competitor_platform" for e in r.other_signals):
        risks.append("A compliance automation vendor already appears on the site; switching costs may block a deal.")
    if any(e.category == "certification_held" for e in r.compliance_signals.soc2_mentions):
        risks.append("Company already holds SOC 2 — the conversation is about continuous compliance / extra frameworks, not a first audit.")
    if r.company_profile.is_saas is None:
        risks.append("SaaS model not confirmed — ICP fit may be overstated or understated.")
    if conf < 0.6:
        risks.append(f"Overall evidence confidence is modest ({conf}).")
    if r.provenance == "deterministic_fallback":
        risks.append("Keyword rules can misread context (e.g. 'SOC 2' in a blog post about a customer, not the company itself).")
    return risks


class CriticReview(BaseModel):
    plain_english_summary: str
    risks_and_uncertainty: list[str] = []
    contradictions: list[str] = []


def critic_review(q: Qualification, r: ExtractionResult, llm: Optional[ClaudeJSON], prompts_dir) -> Qualification:
    """Optional Claude stress-test of the decision. Never alters scores; only adds risks and a summary."""
    if llm is None:
        return q
    evidence = [{"id": e.id, "finding": e.finding, "url": e.source_url, "excerpt": e.excerpt,
                 "type": e.evidence_type, "confidence": e.confidence} for e in r.all_evidence()]
    user = (f"Company: {r.company_profile.company_name} ({r.company_profile.domain})\n"
            f"Decision: {q.decision_status} | ICP {q.icp_fit_score} | Timing {q.buying_timing_score} | Confidence {q.evidence_confidence}\n"
            f"Score breakdown: {[c.model_dump() for c in q.icp_breakdown + q.timing_breakdown]}\n"
            f"Evidence: {evidence}\nMissing: {r.missing_information}")
    try:
        review = llm.call(load_prompt(prompts_dir, "qualification_prompt.txt"), user, CriticReview)
    except LLMUnavailable:
        return q
    q.qualification_reasoning.insert(0, review.plain_english_summary)
    q.risks_and_uncertainty = list(dict.fromkeys(q.risks_and_uncertainty + review.risks_and_uncertainty
                                                 + [f"Contradiction: {c}" for c in review.contradictions]))
    return q
