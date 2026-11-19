"""Pydantic data contracts shared by every pipeline stage.

The core rule of the system lives here: any fact that drives a decision is an `Evidence`
object carrying its source URL, a verbatim excerpt, a classification and a confidence.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EvidenceType = Literal["explicit", "inferred", "hypothesis"]
Provenance = Literal["claude", "deterministic_fallback"]

# Signal categories. Each maps to exactly ONE scoring criterion per score (no double counting).
SignalCategory = Literal[
    "certification_in_progress",   # "working towards SOC 2", "SOC 2 Type I" (Type II next)
    "certification_held",          # "SOC 2 Type II certified", "ISO 27001 certified"
    "compliance_mention",          # GDPR / SOC 2 / ISO mentioned without status
    "compliance_hiring",           # job post for security / GRC / compliance, or JD mentioning SOC 2
    "engineering_hiring",          # engineering roles open (scaling)
    "trust_centre",                # trust centre / security portal exists
    "security_page",               # security page content (encryption, SSO, pentests...)
    "security_review_pressure",    # security questionnaires, vendor reviews, procurement, DPA
    "enterprise_orientation",      # enterprise plan / SSO-SAML / enterprise sales motion
    "enterprise_customer",         # named enterprise customer or case study
    "regulated_industry",          # serves healthcare / finance / gov / insurance ...
    "funding",                     # explicit funding round
    "expansion",                   # new markets, regions, enterprise launch
    "competitor_platform",         # Vanta / Drata / Secureframe / Sprinto trust centre detected
    "saas_indicator",
    "non_saas_indicator",
    "other",
]


class Evidence(BaseModel):
    finding: str
    source_url: str
    excerpt: str = Field(description="Short verbatim quote from the source page")
    evidence_type: EvidenceType = "explicit"
    confidence: float = Field(ge=0.0, le=1.0)
    category: SignalCategory = "other"

    @field_validator("excerpt")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = " ".join(v.split())
        return v[:400]

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.category}|{self.source_url}|{self.excerpt[:120]}".encode()).hexdigest()[:10]


class PageRecord(BaseModel):
    url: str
    category: str = "other"
    title: str = ""
    text: str = ""
    status: str = "ok"            # ok | error | blocked_by_robots | not_found | empty
    http_status: Optional[int] = None
    rendered_with: str = "requests"
    discovered_from: str = ""


class ScrapeRecord(BaseModel):
    company: str
    domain: str
    homepage_url: str = ""
    pages_scraped: list[PageRecord] = []
    discovered_links: dict[str, list[str]] = {}
    raw_text: str = ""
    scraping_status: str = "pending"   # success | partial | failed
    errors: list[str] = []

    def page_urls(self) -> set[str]:
        return {p.url for p in self.pages_scraped}

    def ok_pages(self) -> list[PageRecord]:
        return [p for p in self.pages_scraped if p.status == "ok" and p.text]


class ValueWithEvidence(BaseModel):
    value: Optional[str] = None
    evidence: Optional[Evidence] = None


class CompanyProfile(BaseModel):
    company_name: str
    domain: str
    business_model: Optional[str] = None
    business_description: Optional[Evidence] = None
    is_saas: Optional[bool] = None
    is_saas_evidence: list[Evidence] = []
    employee_range: ValueWithEvidence = ValueWithEvidence()
    funding_stage: ValueWithEvidence = ValueWithEvidence()
    enterprise_customers: list[Evidence] = []
    customer_industries: list[Evidence] = []
    tech_stack: list[Evidence] = []


class ComplianceSignals(BaseModel):
    soc2_mentions: list[Evidence] = []
    iso27001_mentions: list[Evidence] = []
    gdpr_mentions: list[Evidence] = []
    security_pages: list[Evidence] = []
    trust_centre: bool = False
    trust_centre_evidence: list[Evidence] = []
    compliance_hiring: list[Evidence] = []
    enterprise_security_signals: list[Evidence] = []


class BuyingMoment(BaseModel):
    signal: str
    category: SignalCategory
    source_url: str
    evidence: str
    why_it_matters: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_further_research: bool = False
    hook_phrase: str = Field("", description="Neutral, factual phrase an email may reference")


class ExtractionResult(BaseModel):
    company_profile: CompanyProfile
    compliance_signals: ComplianceSignals = ComplianceSignals()
    growth_signals: list[Evidence] = []
    other_signals: list[Evidence] = []
    potential_buying_moments: list[BuyingMoment] = []
    missing_information: list[str] = []
    contradictory_information: list[str] = []
    provenance: Provenance = "deterministic_fallback"

    def all_evidence(self) -> list[Evidence]:
        p, c = self.company_profile, self.compliance_signals
        items: list[Evidence] = []
        if p.business_description:
            items.append(p.business_description)
        items += p.is_saas_evidence + p.enterprise_customers + p.customer_industries + p.tech_stack
        for v in (p.employee_range, p.funding_stage):
            if v.evidence:
                items.append(v.evidence)
        items += (c.soc2_mentions + c.iso27001_mentions + c.gdpr_mentions + c.security_pages
                  + c.trust_centre_evidence + c.compliance_hiring + c.enterprise_security_signals)
        items += self.growth_signals + self.other_signals
        seen, out = set(), []
        for e in items:
            if e.id not in seen:
                seen.add(e.id)
                out.append(e)
        return out


class CriterionScore(BaseModel):
    criterion: str
    max_points: int
    points: float
    rationale: str
    evidence_ids: list[str] = []


class Qualification(BaseModel):
    qualified: bool
    decision_status: Literal["qualified", "not_qualified", "insufficient_data"]
    recommended_action: Literal["outreach", "nurture", "manual_review", "disqualify"]
    icp_fit_score: int
    buying_timing_score: int
    evidence_confidence: float
    icp_breakdown: list[CriterionScore] = []
    timing_breakdown: list[CriterionScore] = []
    penalties: list[str] = []
    qualification_reasoning: list[str] = []
    positive_signals: list[str] = []
    negative_signals: list[str] = []
    missing_information: list[str] = []
    risks_and_uncertainty: list[str] = []
    secondary_research_performed: bool = False
    research_rounds: int = 0
    provenance: Provenance = "deterministic_fallback"
    gate_decision: str = ""                  # Evidence Map: QUALIFY | QUALIFY_AND_FLAG | NURTURE | DROP | HAND_TO_HUMAN
    evidence_map: list[dict] = []
    review_flags: list[str] = []             # what the human review gate must verify before anything is sent


class ResearchRound(BaseModel):
    round: int
    missing_before: list[str]
    pages_targeted: list[str]
    pages_successfully_read: list[str]
    new_findings: list[str]
    icp_before: int
    icp_after: int
    timing_before: int
    timing_after: int
    decision_before: str
    decision_after: str
    what_changed: str


class Contact(BaseModel):
    first_name: str
    last_name: str = ""
    full_name: str
    job_title: str
    email: Optional[str] = None
    email_confidence: Optional[int] = None
    verification_status: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str
    source_url: Optional[str] = None


class RankedContact(BaseModel):
    contact: Contact
    relevance_score: float
    role_family: str
    reasons: list[str]


class ContactSelection(BaseModel):
    status: Literal["selected", "needs_review", "not_attempted"]
    contact: Optional[Contact] = None
    role_family: Optional[str] = None
    selection_reasoning: str = ""
    alternative_contacts: list[RankedContact] = []
    providers_tried: list[str] = []
    provider_notes: list[str] = []


class PainPoint(BaseModel):
    pain_point: str
    basis: Literal["observed", "inferred"]
    reasoning: str
    supporting_evidence: list[str] = Field(default_factory=list, description="Evidence excerpts + URLs")
    confidence: float = Field(ge=0.0, le=1.0)


class PainPointResult(BaseModel):
    pain_points: list[PainPoint]
    provenance: Provenance = "deterministic_fallback"


class TraceLine(BaseModel):
    sentence: str
    purpose: str
    evidence: str = ""
    source_url: str = ""


class GeneratedEmail(BaseModel):
    recipient_name: str
    recipient_email: Optional[str] = None
    subject: str
    subject_candidates: list[str] = []
    subject_choice_reason: str = ""
    email_body: str
    personalisation_hook: str
    hook_source_url: str
    pain_point_used: str
    why_this_email_was_written: str
    evidence_to_email_trace: list[TraceLine] = []
    quality_checks: dict[str, bool] = {}
    word_count: int = 0
    provenance: Provenance = "deterministic_fallback"


class DispatchResult(BaseModel):
    status: Literal["pending_review", "rejected_at_review", "dry_run_preview", "sent", "blocked_missing_credentials",
                    "blocked_by_guard", "error", "skipped"]
    delivered_to: Optional[str] = None
    preview_path: Optional[str] = None
    message_id: Optional[str] = None
    detail: str = ""
