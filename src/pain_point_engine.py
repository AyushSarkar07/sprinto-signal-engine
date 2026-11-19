"""Step 5 — Person-specific pain points.

A pain point is only proposed when (a) it fits the person's role family and (b) the company's
evidence contains a trigger for it. Each result says whether it is OBSERVED (the evidence shows
the problem context directly) or INFERRED (a plausible consequence of what we observed).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.llm import ClaudeJSON, LLMUnavailable, load_prompt
from src.models import Contact, Evidence, ExtractionResult, PainPoint, PainPointResult

log = logging.getLogger(__name__)

SECURITY_ROLES = {"CISO", "Head of Security", "Head of Compliance / GRC"}
ENG_ROLES = {"CTO", "VP of Engineering", "DevOps / Infrastructure lead"}
EXEC_ROLES = {"CEO / Founder", "COO / Operations"}

# (pain point, roles it applies to, trigger categories, observed-if categories, reasoning template)
LIBRARY: list[tuple[str, set, set, set, str]] = [
    ("Audit evidence collection pulling engineers off the roadmap during the {framework} window",
     ENG_ROLES, {"certification_in_progress", "compliance_hiring"}, {"certification_in_progress"},
     "Evidence shows {framework} work under way; as {role} at a {stage} company, {first} likely owns the engineering time that audit evidence requests consume."),
    ("Security questionnaires and vendor reviews slowing enterprise deals",
     ENG_ROLES | EXEC_ROLES, {"security_review_pressure", "enterprise_orientation", "enterprise_customer", "trust_centre"},
     {"security_review_pressure"},
     "The site points to an enterprise motion ({signal}); enterprise buyers send security questionnaires that usually land with the {role}."),
    ("Keeping SOC 2 / ISO 27001 controls continuously audit-ready as the company scales",
     SECURITY_ROLES | ENG_ROLES, {"certification_held", "engineering_hiring", "funding"}, {"certification_held"},
     "{company} already references {framework}; certifications must be re-evidenced every year while headcount and systems grow ({signal})."),
    ("Managing audit evidence and control ownership across many tools and teams",
     SECURITY_ROLES, {"certification_in_progress", "certification_held", "compliance_hiring", "trust_centre"}, {"certification_in_progress"},
     "As {role}, {first} owns audit readiness; the evidence ({signal}) suggests an active programme where evidence is spread across tools."),
    ("Adding a second framework (ISO 27001 / GDPR) without duplicating the control work",
     SECURITY_ROLES | ENG_ROLES, {"expansion", "regulated_industry", "certification_held"}, set(),
     "Signals of expansion or regulated customers ({signal}) typically bring additional frameworks; mapping controls once avoids parallel audits."),
    ("Standing up a compliance programme before a dedicated security team exists",
     ENG_ROLES | EXEC_ROLES, {"compliance_hiring", "enterprise_orientation", "funding"}, {"compliance_hiring"},
     "{company} is growing ({signal}) and no dedicated security lead is visible; until one exists, compliance work usually falls to the {role}."),
    ("Answering customer security reviews in regulated industries",
     SECURITY_ROLES | ENG_ROLES | EXEC_ROLES, {"regulated_industry"}, set(),
     "{company} serves {signal}; buyers in these sectors require formal attestations and detailed reviews."),
]


def _evidence_by_cat(r: ExtractionResult) -> dict[str, list[Evidence]]:
    out: dict[str, list[Evidence]] = {}
    for e in r.all_evidence():
        out.setdefault(e.category, []).append(e)
    return out


def deterministic_pain_points(r: ExtractionResult, contact: Contact, role_family: str) -> PainPointResult:
    by_cat = _evidence_by_cat(r)
    framework = "SOC 2"
    certs = r.compliance_signals.soc2_mentions + r.compliance_signals.iso27001_mentions
    if certs:
        framework = "ISO 27001" if "ISO" in certs[0].excerpt and "SOC" not in certs[0].excerpt else "SOC 2"
    stage = r.company_profile.funding_stage.value or "growing"
    scored = []
    for template, roles, triggers, observed_if, why in LIBRARY:
        if role_family not in roles:
            continue
        ev = [e for c in triggers for e in by_cat.get(c, [])]
        if not ev:
            continue
        ev.sort(key=lambda e: e.confidence, reverse=True)
        observed = any(e.category in observed_if for e in ev)
        conf = round(min(0.9, (0.55 if observed else 0.35) + 0.08 * min(len(ev), 4) + 0.1 * ev[0].confidence), 2)
        signal = ev[0].finding.split(": ", 1)[-1][:90]
        if ev[0].category == "regulated_industry":
            signal = ", ".join(sorted({e.finding.replace("Serves or targets ", "") for e in ev if e.category == "regulated_industry"}))
        scored.append((conf, PainPoint(
            pain_point=template.format(framework=framework),
            basis="observed" if observed else "inferred",
            reasoning=why.format(framework=framework, role=contact.job_title, first=contact.first_name, stage=stage,
                                 company=r.company_profile.company_name, signal=signal),
            supporting_evidence=[f"\"{e.excerpt[:160]}\" — {e.source_url}" for e in ev[:3]],
            confidence=conf)))
    scored.sort(key=lambda t: t[0], reverse=True)
    return PainPointResult(pain_points=[p for _, p in scored[:2]], provenance="deterministic_fallback")


def identify_pain_points(r: ExtractionResult, contact: Contact, role_family: str, llm: Optional[ClaudeJSON],
                         prompts_dir) -> PainPointResult:
    if llm is not None:
        evidence = [{"finding": e.finding, "category": e.category, "excerpt": e.excerpt, "url": e.source_url,
                     "type": e.evidence_type, "confidence": e.confidence} for e in r.all_evidence()]
        user = (f"Company: {r.company_profile.company_name} ({r.company_profile.domain})\n"
                f"Person: {contact.full_name}, {contact.job_title} (role family: {role_family})\n"
                f"Buying moments: {[m.model_dump() for m in r.potential_buying_moments]}\nEvidence: {evidence}")
        try:
            res = llm.call(load_prompt(prompts_dir, "pain_point_prompt.txt"), user, PainPointResult)
            res.provenance = "claude"
            res.pain_points = res.pain_points[:2]
            if res.pain_points:
                return res
        except LLMUnavailable as exc:
            log.warning("Claude pain-point step failed, using fallback: %s", exc)
    return deterministic_pain_points(r, contact, role_family)
