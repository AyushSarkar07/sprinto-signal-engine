"""Step 6 — Evidence-based email generation.

Personalisation chain:  observation → business implication → role-specific challenge → Sprinto value → soft CTA.
Every sentence is traced back to the evidence it relies on. Claude writes the email when available; otherwise
a deterministic composer assembles it from the same chain. Both outputs must pass the same quality gate.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel

from src.llm import ClaudeJSON, LLMUnavailable, load_prompt
from src.models import BuyingMoment, Contact, ExtractionResult, GeneratedEmail, PainPoint, TraceLine

log = logging.getLogger(__name__)

BANNED = ["i came across", "hope this finds you", "impressed by", "reaching out", "synergy", "game-changer",
          "game changer", "revolutioni", "cutting-edge", "seamless", "leverage", "touch base", "circle back",
          "world-class", "best-in-class", "act now", "limited time", "don't miss"]
SPRINTO_VALUE = "Sprinto automates evidence collection and continuous control monitoring for SOC 2, ISO 27001 and GDPR"

IMPLICATION = {
    "certification_in_progress": "That stage usually means an audit window where engineers get pulled into screenshots, access reviews and policy evidence.",
    "certification_held": "Keeping that current tends to mean re-collecting the same evidence every year while the team and stack keep growing.",
    "compliance_hiring": "Teams at that point often find the new hire spends their first months chasing evidence rather than improving security.",
    "trust_centre": "That usually means customers are asking for security documentation during deals.",
    "security_review_pressure": "That usually means security questionnaires sit right inside the sales cycle.",
    "enterprise_orientation": "Larger buyers tend to bring SOC 2 requests and long security questionnaires into the deal.",
    "enterprise_customer": "Larger buyers tend to bring SOC 2 requests and long security questionnaires into the deal.",
    "regulated_industry": "Buyers in those sectors usually ask for formal attestations before they sign.",
    "funding": "Growth like that tends to bring the first SOC 2 or ISO 27001 requests from bigger customers.",
    "expansion": "Moves like that often add a framework or two to the list buyers ask about.",
    "engineering_hiring": "A growing team multiplies the access, change and vendor evidence an auditor asks for.",
}
# Role-facing question per pain point (keys are pain-point prefixes from pain_point_engine.LIBRARY).
QUESTIONS = {
    "Audit evidence collection": "Is audit evidence collection pulling your engineers off the roadmap at the moment?",
    "Security questionnaires": "Are security questionnaires starting to slow down your larger deals?",
    "Keeping SOC 2 / ISO 27001 controls": "Is keeping those controls audit-ready getting harder as the team grows?",
    "Managing audit evidence": "Is audit evidence still spread across a lot of tools and owners on your side?",
    "Adding a second framework": "Is a second framework, like ISO 27001 or GDPR, on the roadmap yet?",
    "Standing up a compliance programme": "Is compliance sitting with you until that security hire lands?",
    "Answering customer security reviews": "Are customer security reviews taking up more of your time than they should?",
}
TOPIC = {
    "certification_in_progress": "audit prep", "certification_held": "staying audit-ready", "compliance_hiring": "the security hire",
    "trust_centre": "your trust centre", "security_review_pressure": "security reviews", "enterprise_orientation": "enterprise security reviews",
    "enterprise_customer": "enterprise security reviews", "regulated_industry": "regulated buyers", "funding": "post-raise compliance",
    "expansion": "new-market compliance", "engineering_hiring": "compliance as you scale",
}


def word_count(body: str) -> int:
    """Words in the body excluding the greeting line and the sign-off block."""
    lines = [l for l in body.strip().splitlines()]
    if lines and lines[0].lower().startswith("hi "):
        lines = lines[1:]
    text = "\n".join(lines)
    text = re.split(r"\n\s*(best|thanks|cheers|regards)[,\s]", text, flags=re.I)[0]
    return len(re.findall(r"\b[\w'’/-]+\b", text))


def choose_hook(extraction: ExtractionResult, pain: Optional[PainPoint]) -> Optional[BuyingMoment]:
    moments = [m for m in extraction.potential_buying_moments if m.source_url]
    if not moments:
        return None
    if pain:  # the hook must be the evidence that supports the pain point, so the email tells one story
        for sup in pain.supporting_evidence:
            for m in moments:
                if m.evidence[:60] and m.evidence[:60] in sup:
                    return m
        for m in moments:
            if any(m.source_url in s for s in pain.supporting_evidence):
                return m
    order = ["certification_in_progress", "compliance_hiring", "security_review_pressure", "trust_centre",
             "certification_held", "enterprise_orientation", "regulated_industry", "enterprise_customer", "funding",
             "expansion", "engineering_hiring"]
    moments.sort(key=lambda m: (order.index(m.category) if m.category in order else 99, -m.confidence))
    return moments[0]


def quality_checks(body: str, first_name: str, hook_url: str, grounded_urls: set[str]) -> dict[str, bool]:
    low = body.lower()
    wc = word_count(body)
    return {
        "length_60_110_words": 60 <= wc <= 110,
        "greets_by_first_name": body.strip().lower().startswith(f"hi {first_name.lower()},"),
        "hook_is_grounded_in_evidence": hook_url in grounded_urls,
        "no_banned_phrases": not any(b in low for b in BANNED),
        "no_exclamation_marks": "!" not in body,
        "single_cta": body.count("?") <= 2,
        "no_unsupported_sprinto_claims": not re.search(r"\b\d+[,\d]*\+? (customers|companies)\b|\bin \d+ (days|weeks)\b|guarantee", low),
    }


def _subject_pick(cands: list[str], company: str) -> tuple[str, str]:
    def score(s: str) -> int:
        n = len(s.split())
        return (2 if re.search(r"SOC 2|ISO|audit|security|review|hire|trust", s, re.I) else 0) + \
               (1 if company.lower() in s.lower() else 0) + (1 if n <= 5 else 0) - (2 if n > 7 else 0)
    best = max(cands, key=score)
    return best, f"Chosen for specificity to the observed signal and brevity (score {score(best)} vs " \
                 f"{', '.join(str(score(c)) for c in cands if c != best)})."


def compose_deterministic(extraction: ExtractionResult, contact: Contact, role_family: str, pain: PainPoint,
                          hook: BuyingMoment, sender: str) -> GeneratedEmail:
    company = extraction.company_profile.company_name
    obs = f"Noticed {hook.hook_phrase or hook.signal.lower()}."
    obs = obs[0].upper() + obs[1:]
    implication = IMPLICATION.get(hook.category, IMPLICATION["enterprise_orientation"])
    pp = pain.pain_point[0].lower() + pain.pain_point[1:]
    challenge = next((q for k, q in QUESTIONS.items() if pain.pain_point.startswith(k)),
                     f"Curious whether {pp} is on your plate right now?")
    if pain.basis != "observed" and pain.pain_point.startswith("Standing up a compliance programme"):
        # No security job posting was observed, so the email must not imply one.
        challenge = f"Who owns compliance at {company} today: does it still sit with you?"
    outcome = ("so your team spends its time on security work rather than spreadsheets of evidence"
               if role_family in ("CISO", "Head of Security", "Head of Compliance / GRC")
               else "so audit prep stops being a side project for engineering")
    value = f"{SPRINTO_VALUE}, {outcome}."
    cta = "If it's relevant, would a 20-minute conversation be useful?"
    body = f"Hi {contact.first_name},\n\n{obs} {implication}\n\n{challenge}\n\n{value} {cta}\n\nBest,\n{sender or 'Sprinto Growth Team'}"
    topic = TOPIC.get(hook.category, "compliance")
    cands = [f"{topic} at {company}", f"{company} and {'SOC 2' if 'ISO' not in pp else 'ISO 27001'}",
             f"question on {topic}"]
    subject, why_subj = _subject_pick(cands, company)
    trace = [
        TraceLine(sentence=obs, purpose="Website observation (hook)", evidence=hook.evidence, source_url=hook.source_url),
        TraceLine(sentence=implication, purpose="Business implication of the observation", evidence=hook.why_it_matters,
                  source_url=hook.source_url),
        TraceLine(sentence=challenge, purpose=f"Role-specific challenge ({pain.basis})", evidence="; ".join(pain.supporting_evidence[:2]),
                  source_url=hook.source_url),
        TraceLine(sentence=value, purpose="Relevant Sprinto value proposition (core product, no extra claims)"),
        TraceLine(sentence=cta, purpose="Single low-pressure CTA"),
    ]
    return GeneratedEmail(recipient_name=contact.full_name, recipient_email=contact.email, subject=subject,
                          subject_candidates=cands, subject_choice_reason=why_subj, email_body=body,
                          personalisation_hook=hook.hook_phrase or hook.signal, hook_source_url=hook.source_url,
                          pain_point_used=pain.pain_point,
                          why_this_email_was_written=(f"{hook.signal} ({hook.source_url}) suggests {hook.why_it_matters[0].lower()}"
                                                      f"{hook.why_it_matters[1:]} {contact.full_name} ({contact.job_title}) is the likely owner of "
                                                      f"'{pain.pain_point}'."),
                          evidence_to_email_trace=trace, provenance="deterministic_fallback")


class ClaudeEmailDraft(BaseModel):
    subject_candidates: list[str]
    subject: str
    subject_choice_reason: str
    email_body: str
    personalisation_hook: str
    hook_source_url: str
    pain_point_used: str
    why_this_email_was_written: str
    evidence_to_email_trace: list[TraceLine]


def generate_email(extraction: ExtractionResult, contact: Contact, role_family: str, pains: list[PainPoint],
                   llm: Optional[ClaudeJSON], prompts_dir, sender: str = "") -> Optional[GeneratedEmail]:
    """Return a validated email, or None when there is no grounded hook (we never fabricate one)."""
    pain = pains[0] if pains else None
    hook = choose_hook(extraction, pain)
    if hook is None or pain is None:
        return None
    grounded = {e.source_url for e in extraction.all_evidence()} | {m.source_url for m in extraction.potential_buying_moments}
    email: Optional[GeneratedEmail] = None
    if llm is not None:
        user = (f"Recipient: {contact.full_name} (first name: {contact.first_name}), {contact.job_title}, role family {role_family}\n"
                f"Company: {extraction.company_profile.company_name}\n"
                f"Hook evidence: {hook.model_dump()}\nPrimary pain point: {pain.model_dump()}\n"
                f"Other buying moments: {[m.model_dump() for m in extraction.potential_buying_moments[:4]]}\n"
                f"Sign off as: {sender or 'Sprinto Growth Team'}\nRequired JSON schema: {ClaudeEmailDraft.model_json_schema()}")
        system = load_prompt(prompts_dir, "email_prompt.txt")
        for attempt in range(2):
            try:
                d = llm.call(system, user, ClaudeEmailDraft)
            except LLMUnavailable as exc:
                log.warning("Claude email step failed, using fallback: %s", exc)
                break
            checks = quality_checks(d.email_body, contact.first_name, d.hook_source_url, grounded)
            if all(checks.values()):
                email = GeneratedEmail(recipient_name=contact.full_name, recipient_email=contact.email, **d.model_dump(),
                                       provenance="claude")
                break
            failed = [k for k, v in checks.items() if not v]
            log.info("Claude email failed checks %s (attempt %d)", failed, attempt + 1)
            user += f"\n\nYour previous draft failed these checks: {failed}. Hook URL must be {hook.source_url}. Rewrite."
    if email is None:
        email = compose_deterministic(extraction, contact, role_family, pain, hook, sender)
    email.quality_checks = quality_checks(email.email_body, contact.first_name, email.hook_source_url, grounded)
    email.word_count = word_count(email.email_body)
    return email
