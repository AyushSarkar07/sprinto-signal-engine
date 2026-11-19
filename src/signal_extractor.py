"""Step 2 — Signal extraction.

Two interchangeable extractors produce the same `ExtractionResult` contract:
  * `extract_with_claude`  — Claude reads the scraped pages and returns schema-validated JSON;
  * `extract_deterministic` — a transparent rule/regex extractor used when Claude is unavailable.
Both outputs pass through `ground_evidence`, which drops any evidence whose excerpt cannot be
found verbatim on the cited page. Nothing un-sourced survives into qualification.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Iterable, Optional

from src.llm import ClaudeJSON, LLMUnavailable, load_prompt
from src.models import (BuyingMoment, CompanyProfile, ComplianceSignals, Evidence, ExtractionResult, PageRecord,
                        ScrapeRecord, ValueWithEvidence)

log = logging.getLogger(__name__)
CURRENT_YEAR = dt.date.today().year

PAGE_LABEL = {"homepage": "your homepage", "security": "your security page", "trust": "your trust centre",
              "compliance": "your compliance page", "customers": "your customer stories", "careers": "your careers page",
              "enterprise": "your enterprise page", "about": "your about page", "pricing": "your pricing page",
              "legal": "your legal pages", "news": "your newsroom", "product": "your product pages"}

# ------------------------------------------------------------------ helpers

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def excerpt_around(text: str, start: int, end: int, width: int = 160) -> str:
    """Return the sentence(s) surrounding a match, trimmed to ~2*width characters, verbatim."""
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    seg_start = max(text.rfind("\n", lo, start), text.rfind(". ", lo, start))
    seg_start = seg_start + 1 if seg_start >= 0 else lo
    nl = text.find("\n", end, hi)
    dot = text.find(". ", end, hi)
    cands = [c for c in (nl, dot) if c != -1]
    seg_end = (min(cands) + 1) if cands else hi
    return " ".join(text[seg_start:seg_end].split())[:400]


def staleness_factor(excerpt: str) -> tuple[float, Optional[int]]:
    """Down-weight evidence that cites an old year (e.g. 'raised Series A in 2019')."""
    years = [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", excerpt)]
    if not years:
        return 1.0, None
    newest = max(years)
    if newest <= CURRENT_YEAR - 3:
        return 0.5, newest
    return 1.0, newest


def find_all(pages: Iterable[PageRecord], pattern: str, category: str, finding: str, confidence: float,
             evidence_type: str = "explicit", per_page: int = 1, flags=re.I, categories: Optional[set] = None,
             limit: int = 4, exclude: Optional[set] = None) -> list[Evidence]:
    out: list[Evidence] = []
    rx = re.compile(pattern, flags)
    for p in pages:
        if categories and p.category not in categories:
            continue
        if exclude and p.category in exclude:
            continue
        n = 0
        for m in rx.finditer(p.text):
            ex = excerpt_around(p.text, m.start(), m.end())
            if len(ex) < 8:
                continue
            factor, _ = staleness_factor(ex)
            out.append(Evidence(finding=finding.format(match=m.group(0).strip()), source_url=p.url, excerpt=ex,
                                evidence_type=evidence_type, confidence=round(confidence * factor, 2), category=category))
            n += 1
            if n >= per_page:
                break
        if len(out) >= limit:
            break
    return out


def _dedupe(items: list[Evidence]) -> list[Evidence]:
    seen, out = set(), []
    for e in items:
        k = (e.source_url, _norm(e.excerpt)[:100])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


# ------------------------------------------------------------------ deterministic extractor

SAAS_STRONG = [
    (r"\bsoftware[- ]as[- ]a[- ]service\b|\bSaaS\b", "Describes itself as SaaS"),
    (r"\bfree trial\b|\b(start|try) (it )?(for )?free\b|\bsign up free\b|\bget started (for )?free\b", "Self-serve free trial / sign-up"),
    (r"\b(book|request|get|schedule) a (live )?demo\b|\btalk to sales\b", "Product demo / sales-led motion"),
    (r"\bper (user|seat)\b|\b/(user|seat)/(mo|month)\b|\bbilled (annually|monthly)\b", "Subscription pricing"),
    (r"\b(log ?in|sign ?in)\b", "Customer login to a hosted product"),
]
SAAS_SUPPORT = [
    (r"\bAPI\b|\bSDK\b", "Developer API"),
    (r"\bintegrat(es|ions?) with\b|\bintegrations\b", "Product integrations"),
    (r"\b(cloud[- ]based|cloud platform|platform)\b", "Platform positioning"),
    (r"\bdashboard\b|\bworkflows?\b|\bautomat(e|ion)\b", "Workflow / automation product"),
]
NON_SAAS = [
    (r"\badd to (cart|bag)\b|\bfree shipping\b|\bshop (now|all)\b|\bcheckout\b", "Physical goods e-commerce"),
    (r"\bour (restaurants?|cafes?|stores?|menu|locations)\b|\breservations?\b", "Hospitality / retail locations"),
    (r"\b(consulting|consultancy) (services|firm)\b|\bwe are an? (digital |creative |marketing |design )?agency\b", "Services firm / agency"),
    (r"\blaw firm\b|\battorneys?\b|\bpractice areas\b", "Law firm"),
    (r"\bhotel\b|\bresort\b|\bbook your stay\b", "Hospitality"),
    (r"\bcoffee\b.*\broast|\bbakery\b|\bbrewery\b", "Food & beverage"),
]
INDUSTRIES = {
    "healthcare": r"\bhealthcare\b|\bhospitals?\b|\bpatients?\b|\bclinical\b|\bHIPAA\b|\bhealth systems?\b",
    "financial services": r"\bfintech\b|\bbanks?\b|\bbanking\b|\bfinancial (services|institutions)\b|\blending\b|\bpayments?\b|\binsurance\b|\binsurers?\b",
    "government / public sector": r"\bgovernment\b|\bpublic sector\b|\bfederal\b|\bFedRAMP\b",
    "education": r"\buniversit(y|ies)\b|\bhigher education\b|\bK-12\b",
    "legal": r"\blegal teams?\b|\blaw firms\b",
}
REGULATED = {"healthcare", "financial services", "government / public sector"}
COMPETITORS = {"vanta": "Vanta", "drata": "Drata", "secureframe": "Secureframe", "sprinto": "Sprinto",
               "thoropass": "Thoropass", "scrut": "Scrut"}

# Customer stories and blog posts describe OTHER companies or generic topics.
ABOUT_OTHERS = {"customers", "news"}
SOC2 = r"SOC ?2(?:®)?(?: Type (?:II|I|1|2)\b)?"
ISO = r"ISO(?:/IEC)?[ -]?27001"
IN_PROGRESS = r"(working (towards|toward|on)|in progress|pursuing|underway|currently undergoing|in the process of|on track to|expected (in|by)|coming soon|planned|we are preparing)"
HELD = r"(certified|certification|compliant|compliance|audited|attest|report|achieved|completed|accredited)"
SECURITY_PAGE_TERMS = r"\b(AES[- ]?256|encrypt(ed|ion) (at rest|in transit)|TLS ?1\.[23]|penetration test(s|ing)?|pen[- ]?tests?|bug bounty|vulnerability disclosure|role[- ]based access|single sign[- ]on|SSO|SAML|SCIM|data residency|audit logs?)\b"
REVIEW_PRESSURE = r"\b(security questionnaires?|security reviews?|vendor (risk )?(assessments?|reviews?)|procurement|data processing (agreement|addendum)|DPA\b|sub-?processors?|SIG (lite|core)|CAIQ|request (our|the) (SOC 2 )?report|NDA to (access|view))"
ENTERPRISE = r"\b(enterprise[- ](grade|ready|plan|customers?|security|edition|teams?)|for (the )?enterprise|Fortune (500|100)|global 2000|dedicated (account|customer success) manager|custom (SLA|contract)s?|\bSLA\b)"
FUNDING = r"(?:rais(?:ed|es|ing)|closes?|closed|secur(?:ed|es)|announc(?:ed|es))[^.\n]{0,80}?(?:\$|€|£|US\$)\s?\d[\d.,]*\s?(?:M|million|B|billion|mn)\b[^.\n]{0,100}|\b(?:Seed|Series [A-F])\b (?:round|funding|financing|investment)"
STAGE_RX = re.compile(r"\b(Series [A-F]|Seed|pre-seed)\b", re.I)
EMPLOYEES = r"\b(\d{1,3}(?:,\d{3})?)\+?\s+(employees|team members|people|teammates|staff)\b|\bteam of (\d{1,3}(?:,\d{3})?)\b"
EXPANSION = r"\b(expand(ing|s|ed)? (into|to|our)|launch(ing|es|ed)? (in|our|a new)|new office|now available in|opening (an )?office|international expansion|entering the [A-Z][a-z]+ market)\b"
TECH_EXPLICIT = r"\b(hosted|built|runs|running|deployed|infrastructure) (on|in) (AWS|Amazon Web Services|Google Cloud( Platform)?|GCP|Microsoft Azure|Azure)\b"
SECURITY_ROLE = re.compile(r"\b(security|CISO|GRC|compliance|trust|privacy|risk|devsecops|infosec|governance)\b", re.I)
ENG_ROLE = re.compile(r"\b(engineer|engineering|developer|SRE|devops|architect|platform|infrastructure|data scientist)\b", re.I)


def _saas_assessment(pages: list[PageRecord]) -> tuple[Optional[bool], list[Evidence], list[Evidence]]:
    strong = [e for pat, f in SAAS_STRONG for e in find_all(pages, pat, "saas_indicator", f, 0.6, limit=1)]
    support = [e for pat, f in SAAS_SUPPORT for e in find_all(pages, pat, "saas_indicator", f, 0.4, "inferred", limit=1)]
    non = [e for pat, f in NON_SAAS for e in find_all(pages, pat, "non_saas_indicator", f, 0.6, limit=1)]
    explicit_saas = any("Describes itself as SaaS" == e.finding for e in strong)
    score = len(strong) * 2 + len(support) - len(non) * 2
    if (explicit_saas or len(strong) >= 2) and score >= 4 and len(non) <= 1:
        verdict: Optional[bool] = True
    elif len(non) >= 2 and len(strong) <= 1:
        verdict = False
    else:
        verdict = None
    return verdict, strong + support, non


def _job_lines(pages: list[PageRecord]) -> list[tuple[PageRecord, str, list[str]]]:
    jobs = []
    for p in pages:
        if p.category != "careers":
            continue
        lines = p.text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("JOB: "):
                jds = []
                j = i + 1
                while j < len(lines) and lines[j].startswith("  JD: "):
                    jds.append(lines[j][6:])
                    j += 1
                jobs.append((p, line[5:], jds))
        if not any(l.startswith("JOB: ") for l in lines):  # plain HTML careers page: role-like short lines
            for line in lines:
                if 6 < len(line) < 90 and (SECURITY_ROLE.search(line) or ENG_ROLE.search(line)) and \
                        re.search(r"\b(engineer|manager|lead|head|director|analyst|architect|officer|specialist|VP)\b", line, re.I):
                    jobs.append((p, line, []))
    return jobs


def extract_deterministic(rec: ScrapeRecord) -> ExtractionResult:
    pages = rec.ok_pages()
    profile = CompanyProfile(company_name=rec.company, domain=rec.domain)
    comp = ComplianceSignals()
    growth: list[Evidence] = []
    other: list[Evidence] = []
    contradictions: list[str] = []

    home = next((p for p in pages if p.category == "homepage"), pages[0] if pages else None)
    if home:
        first = next((l for l in home.text.splitlines() if len(l) > 40), home.text[:200])
        profile.business_description = Evidence(finding="Business description (homepage / meta description)",
                                                source_url=home.url, excerpt=first[:300], confidence=0.7, category="other")

    profile.is_saas, saas_ev, non_ev = _saas_assessment(pages)
    profile.is_saas_evidence = saas_ev + non_ev
    profile.business_model = {True: "B2B SaaS (rule-based assessment)", False: "Not SaaS (rule-based assessment)",
                              None: "Unclear from available pages"}[profile.is_saas]
    if saas_ev and len(non_ev) >= 1 and profile.is_saas is not False:
        contradictions.append("Pages show both software-product and non-software (goods/services) indicators.")

    # Funding / stage
    fund = find_all(pages, FUNDING, "funding", "Funding announcement: {match}", 0.85, per_page=2, limit=4,
                    exclude={"customers"})  # a company's own newsroom is the right place for its funding news
    growth += fund
    stages = []
    for e in fund:
        m = STAGE_RX.search(e.excerpt)
        if m:
            stages.append((m.group(1).title().replace("Pre-Seed", "Pre-seed"), e))
    if stages:
        stage, ev = stages[0]
        profile.funding_stage = ValueWithEvidence(value=stage, evidence=ev)
        if len({s for s, _ in stages}) > 1:
            contradictions.append(f"Multiple funding stages mentioned ({', '.join(sorted({s for s, _ in stages}))}); "
                                  "may be funding history — latest round not confirmed.")
    emp = find_all(pages, EMPLOYEES, "other", "Headcount mention: {match}", 0.7, limit=2)
    if emp:
        profile.employee_range = ValueWithEvidence(value=re.search(EMPLOYEES, emp[0].excerpt, re.I).group(0)
                                                   if re.search(EMPLOYEES, emp[0].excerpt, re.I) else None, evidence=emp[0])

    # Industries
    for ind, pat in INDUSTRIES.items():
        for e in find_all(pages, pat, "regulated_industry" if ind in REGULATED else "other",
                          f"Serves or targets {ind}", 0.55, "inferred", limit=1, exclude={"careers", "legal", "news"}):
            profile.customer_industries.append(e)

    # Enterprise
    profile.enterprise_customers = find_all(
        pages, r"\b(trusted by|used by|customers (include|like)|loved by|teams at|powering)\b[^.\n]{3,160}",
        "enterprise_customer", "Customer reference: {match}", 0.55, "inferred", limit=3, exclude={"careers", "news"})
    profile.enterprise_customers += [Evidence(finding=f"Customer stories page exists: {p.title or p.url}", source_url=p.url,
                                              excerpt=(p.text.splitlines() or [p.title])[0][:200], confidence=0.6,
                                              category="enterprise_customer")
                                     for p in pages if p.category == "customers"][:1]
    comp.enterprise_security_signals = find_all(pages, ENTERPRISE, "enterprise_orientation", "Enterprise orientation: {match}", 0.65,
                                                limit=3, exclude={"customers", "news", "careers"})
    comp.enterprise_security_signals += find_all(pages, REVIEW_PRESSURE, "security_review_pressure",
                                                 "Security review / procurement process: {match}", 0.7, limit=3,
                                                 exclude={"customers", "news", "careers"})
    # Marketing pages render product mock-ups (e.g. a CRM deal stage "Security review underway"). Outside
    # security/trust/legal pages, only full sentences count as evidence of the company's own process.
    comp.enterprise_security_signals = [e for e in comp.enterprise_security_signals
                                        if _page_category(e.source_url, rec) in ("security", "trust", "legal", "compliance", "enterprise")
                                        or len(e.excerpt.split()) >= 6]

    # Tech stack — only explicit infrastructure statements, never inferred from "integrates with AWS"
    profile.tech_stack = find_all(pages, TECH_EXPLICIT, "other", "Infrastructure: {match}", 0.8, limit=2)

    # Compliance frameworks with status detection
    for e in find_all(pages, SOC2, "compliance_mention", "Mentions {match}", 0.8, per_page=2, limit=6, exclude=ABOUT_OTHERS):
        comp.soc2_mentions.append(_classify_cert(e))
    for e in find_all(pages, ISO, "compliance_mention", "Mentions {match}", 0.8, per_page=2, limit=4, exclude=ABOUT_OTHERS):
        comp.iso27001_mentions.append(_classify_cert(e))
    # Blog/news posts often discuss SOC 2 in general: keep them, but only as weak, unclassified mentions.
    comp.soc2_mentions += [e.model_copy(update={"confidence": 0.35, "evidence_type": "inferred",
                                                "finding": e.finding + " (in a blog/news post — may not describe the company itself)"})
                           for e in find_all(pages, SOC2, "compliance_mention", "Mentions {match}", 0.8, limit=1,
                                             categories={"news"})]
    comp.gdpr_mentions = find_all(pages, r"\bGDPR\b", "compliance_mention", "Mentions GDPR", 0.6, limit=2)
    other += find_all(pages, r"\bHIPAA\b|\bPCI[- ]DSS\b|\bFedRAMP\b|\bISO ?42001\b|\bISO ?27701\b",
                      "compliance_mention", "Mentions additional framework {match}", 0.7, limit=3)
    sts = {e.category for e in comp.soc2_mentions + comp.iso27001_mentions}
    if "certification_in_progress" in sts and "certification_held" in sts:
        contradictions.append("Site describes a certification as both held and in progress (could be Type I held, Type II in progress).")

    # Security pages & trust centre
    comp.security_pages = find_all(pages, SECURITY_PAGE_TERMS, "security_page", "Security control described: {match}", 0.6,
                                   per_page=2, categories={"security", "trust", "compliance", "legal", "enterprise", "pricing"}, limit=4)
    trust_pages = [p for p in pages if p.category == "trust"]
    comp.trust_centre_evidence = [Evidence(finding="Trust centre page is live", source_url=p.url,
                                           excerpt=(p.title or p.text[:150])[:200], confidence=0.85, category="trust_centre")
                                  for p in trust_pages][:1]
    comp.trust_centre_evidence += find_all(pages, r"\bTrust (Center|Centre|Portal|Hub)\b", "trust_centre", "References a {match}", 0.7, limit=1)
    for link in rec.discovered_links.get("trust", [])[:1]:
        if not trust_pages:
            comp.trust_centre_evidence.append(Evidence(finding="Website links to a trust centre", source_url=rec.homepage_url,
                                                       excerpt=f"Link to {link}", confidence=0.6, evidence_type="explicit",
                                                       category="trust_centre"))
    comp.trust_centre = bool(comp.trust_centre_evidence)

    # Incumbent compliance tooling
    for key, name in COMPETITORS.items():
        links = [u for urls in rec.discovered_links.values() for u in urls if key in u.lower()]
        hits = find_all(pages, rf"\b(powered by|managed (with|by)|via|using) {name}\b|{key}\.com", "competitor_platform",
                        f"Compliance platform detected: {name}", 0.8, limit=1)
        if links and not hits:
            hits = [Evidence(finding=f"Compliance platform detected: {name}", source_url=rec.homepage_url,
                             excerpt=f"Link to {links[0]}", confidence=0.8, category="competitor_platform")]
        other += hits

    # Hiring
    for page, title, jds in _job_lines(pages):
        if SECURITY_ROLE.search(title):
            comp.compliance_hiring.append(Evidence(finding=f"Open security/compliance role: {title}", source_url=page.url,
                                                   excerpt=f"JOB: {title}", confidence=0.85, category="compliance_hiring"))
        elif ENG_ROLE.search(title):
            growth.append(Evidence(finding=f"Open engineering role: {title}", source_url=page.url, excerpt=f"JOB: {title}",
                                   confidence=0.75, category="engineering_hiring"))
        for jd in jds:
            if re.search(SOC2 + "|" + ISO, jd, re.I):
                comp.compliance_hiring.append(Evidence(finding=f"Job description for '{title}' references a compliance framework",
                                                       source_url=page.url, excerpt=jd[:300], confidence=0.9,
                                                       category="certification_in_progress"))
    eng_jobs = [g for g in growth if g.category == "engineering_hiring"]
    growth = [g for g in growth if g.category != "engineering_hiring"] + eng_jobs[:6]
    if len(eng_jobs) > 6:
        growth.append(Evidence(finding=f"{len(eng_jobs)} open engineering roles", source_url=eng_jobs[0].source_url,
                               excerpt=f"{len(eng_jobs)} engineering job titles listed", confidence=0.8,
                               category="engineering_hiring"))
    growth += find_all(pages, EXPANSION, "expansion", "Expansion signal: {match}", 0.6, limit=2, exclude=ABOUT_OTHERS)

    result = ExtractionResult(company_profile=profile, compliance_signals=comp, growth_signals=_dedupe(growth),
                              other_signals=_dedupe(other), contradictory_information=contradictions,
                              provenance="deterministic_fallback")
    result.missing_information = missing_information(result)
    result.potential_buying_moments = derive_buying_moments(result, rec)
    return result


def _classify_cert(e: Evidence) -> Evidence:
    ex = e.excerpt
    type1_only = re.search(r"Type (I|1)\b(?! ?I)", ex) and not re.search(r"Type (II|2)\b|\b(I|1) (&|and|/) ?(II|2)\b", ex)
    if re.search(IN_PROGRESS, ex, re.I) or type1_only:
        return e.model_copy(update={"category": "certification_in_progress",
                                    "finding": e.finding + " — appears to be in progress / first stage"})
    if re.search(HELD, ex, re.I):
        return e.model_copy(update={"category": "certification_held", "finding": e.finding + " — appears to be held"})
    return e


# ------------------------------------------------------------------ shared post-processing

MISSING_KEYS = {
    "saas_model": "Whether the company is a SaaS business",
    "growth_stage": "Funding stage or headcount",
    "enterprise_customers": "Evidence of enterprise customers or an enterprise motion",
    "compliance_status": "Any SOC 2 / ISO 27001 / GDPR status",
    "security_hiring": "Security, compliance or engineering hiring activity",
    "security_page": "A security or trust page describing controls",
}


def missing_information(r: ExtractionResult) -> list[str]:
    p, c = r.company_profile, r.compliance_signals
    miss = []
    if p.is_saas is None:
        miss.append("saas_model")
    if not p.funding_stage.value and not p.employee_range.value:
        miss.append("growth_stage")
    if not p.enterprise_customers and not any(e.category == "enterprise_orientation" for e in c.enterprise_security_signals):
        miss.append("enterprise_customers")
    if not (c.soc2_mentions or c.iso27001_mentions or c.gdpr_mentions):
        miss.append("compliance_status")
    if not c.compliance_hiring and not any(g.category == "engineering_hiring" for g in r.growth_signals):
        miss.append("security_hiring")
    if not c.security_pages and not c.trust_centre:
        miss.append("security_page")
    return [f"{k}: {MISSING_KEYS[k]}" for k in miss]


WHY = {
    "certification_in_progress": "A certification that is in progress (or a Type I awaiting Type II) means an audit window is open now — the moment when evidence collection and control monitoring are most painful.",
    "certification_held": "An existing certification must be renewed every year and usually expands to further frameworks as the customer base grows; continuous compliance becomes the ongoing cost.",
    "compliance_hiring": "Hiring for security or compliance shows the company is building the function now; new owners typically choose tooling in their first months.",
    "trust_centre": "A trust centre signals that customers are actively asking for security documentation during deals.",
    "security_review_pressure": "References to security questionnaires, DPAs or procurement suggest deals already pass through vendor security review.",
    "enterprise_orientation": "Selling to enterprises almost always triggers SOC 2 / ISO 27001 requests in procurement.",
    "enterprise_customer": "Named larger customers suggest the company is already exposed to enterprise security requirements.",
    "regulated_industry": "Customers in regulated industries (finance, healthcare, public sector) routinely require formal attestations from vendors.",
    "funding": "A new round usually funds go-to-market expansion into larger accounts, which brings security reviews with it.",
    "expansion": "Expansion into new markets or segments often adds frameworks (e.g. GDPR, ISO 27001 for EU buyers).",
    "engineering_hiring": "A growing engineering team multiplies the systems, access and change-management evidence an auditor will ask for.",
}
HOOK = {
    "certification_in_progress": "{label} mentions {term} work in progress",
    "certification_held": "{label} lists {term}",
    "compliance_hiring": "you're hiring for {role}",
    "trust_centre": "you've published a trust centre",
    "security_review_pressure": "{label} talks about {term}",
    "enterprise_orientation": "{label} highlights {term}",
    "enterprise_customer": "{label} features customer work with larger teams",
    "regulated_industry": "you work with customers in {industry}",
    "funding": "your recent {term} announcement",
    "expansion": "{label} mentions {term}",
    "engineering_hiring": "you're hiring engineers",
}


QUOTABLE = {"security_review_pressure", "enterprise_orientation", "certification_held", "certification_in_progress"}


def _page_category(url: str, rec: ScrapeRecord) -> str:
    for p in rec.pages_scraped:
        if p.url == url:
            if re.search(r"trust (center|centre|portal)", p.title + " " + p.text[:200], re.I):
                return "trust"
            return p.category
    return "homepage"


def derive_buying_moments(r: ExtractionResult, rec: ScrapeRecord) -> list[BuyingMoment]:
    """Turn evidence into Buying Moment hypotheses. One moment per category (the strongest evidence)."""
    c = r.compliance_signals
    pool = (c.soc2_mentions + c.iso27001_mentions + c.compliance_hiring + c.trust_centre_evidence
            + c.enterprise_security_signals + r.company_profile.enterprise_customers + r.company_profile.customer_industries
            + r.growth_signals)
    best: dict[str, Evidence] = {}
    for e in pool:
        if e.category in WHY and (e.category not in best or e.confidence > best[e.category].confidence):
            best[e.category] = e
    moments = []
    for cat, e in best.items():
        label = PAGE_LABEL.get(_page_category(e.source_url, rec), "your website")
        term_m = re.search(SOC2 + "|" + ISO + "|" + REVIEW_PRESSURE + "|" + ENTERPRISE + "|Series [A-F]|Seed|" + EXPANSION, e.excerpt, re.I)
        term = term_m.group(0) if term_m else ""
        role = e.excerpt.replace("JOB: ", "") if cat == "compliance_hiring" else ""
        industry = e.finding.replace("Serves or targets ", "") if cat == "regulated_industry" else ""
        hook = HOOK[cat].format(label=label, term=term or "this", role=f"a {role}" if role else "a security role",
                                industry=industry)
        short = e.excerpt.strip().rstrip(".")
        if cat in QUOTABLE and 3 <= len(short.split()) <= 12:
            hook = f'{label} says "{short}"'  # a short verbatim quote is the most natural and most grounded hook
        weak = e.evidence_type != "explicit" or e.confidence < 0.6
        moments.append(BuyingMoment(signal=e.finding, category=cat, source_url=e.source_url, evidence=e.excerpt,
                                    why_it_matters=WHY[cat], confidence=e.confidence, requires_further_research=weak,
                                    hook_phrase=hook))
    moments.sort(key=lambda m: m.confidence, reverse=True)
    return moments


def ground_evidence(r: ExtractionResult, rec: ScrapeRecord) -> tuple[ExtractionResult, int]:
    """Drop any evidence whose excerpt is not actually present on the cited page. Returns (result, dropped)."""
    texts = {p.url: _norm(p.text) for p in rec.pages_scraped}
    texts_any = " ".join(texts.values())
    dropped = 0

    def ok(e: Evidence) -> bool:
        ex = _norm(e.excerpt)
        if ex.startswith("link to ") or ex.startswith("job: ") or re.match(r"^\d+ engineering job titles", ex):
            return True  # synthesised from structured data we fetched ourselves
        probe = ex[:80]
        page = texts.get(e.source_url)
        return bool(probe) and ((page is not None and probe in page) or (page is None and probe in texts_any))

    def keep(items: list[Evidence]) -> list[Evidence]:
        nonlocal dropped
        out = [e for e in items if ok(e)]
        dropped += len(items) - len(out)
        return out

    p, c = r.company_profile, r.compliance_signals
    if p.business_description and not ok(p.business_description):
        p.business_description, dropped = None, dropped + 1
    for v in (p.employee_range, p.funding_stage):
        if v.evidence and not ok(v.evidence):
            v.value, v.evidence, dropped = None, None, dropped + 1
    p.is_saas_evidence = keep(p.is_saas_evidence)
    p.enterprise_customers = keep(p.enterprise_customers)
    p.customer_industries = keep(p.customer_industries)
    p.tech_stack = keep(p.tech_stack)
    for f in ("soc2_mentions", "iso27001_mentions", "gdpr_mentions", "security_pages", "trust_centre_evidence",
              "compliance_hiring", "enterprise_security_signals"):
        setattr(c, f, keep(getattr(c, f)))
    r.growth_signals = keep(r.growth_signals)
    r.other_signals = keep(r.other_signals)
    grounded_urls = {e.source_url for e in r.all_evidence()}
    before = len(r.potential_buying_moments)
    r.potential_buying_moments = [m for m in r.potential_buying_moments
                                  if _norm(m.evidence)[:80] in texts.get(m.source_url, texts_any) or m.source_url in grounded_urls]
    dropped += before - len(r.potential_buying_moments)
    if dropped:
        r.contradictory_information.append(f"{dropped} extracted claim(s) were discarded because their quoted excerpt "
                                           "could not be found on the cited page.")
    return r, dropped


# ------------------------------------------------------------------ Claude extractor

def build_extraction_prompt(rec: ScrapeRecord, prompts_dir, max_chars_per_page: int = 12000) -> tuple[str, str]:
    system = load_prompt(prompts_dir, "extraction_prompt.txt")
    parts = []
    for p in rec.ok_pages():
        body = p.text[:max_chars_per_page]
        note = " (truncated)" if len(p.text) > max_chars_per_page else ""
        parts.append(f"<page url=\"{p.url}\" category=\"{p.category}\"{note}>\n{body}\n</page>")
    schema = json.dumps(ExtractionResult.model_json_schema(), separators=(",", ":"))
    user = (f"Company: {rec.company}\nDomain: {rec.domain}\n\nScraped pages:\n" + "\n\n".join(parts)
            + f"\n\nReturn ONE JSON object valid against this JSON schema (set provenance to \"claude\"):\n{schema}")
    return system, user


def extract_with_claude(rec: ScrapeRecord, llm: ClaudeJSON, prompts_dir) -> ExtractionResult:
    system, user = build_extraction_prompt(rec, prompts_dir)
    result = llm.call(system, user, ExtractionResult)
    result.provenance = "claude"
    result.company_profile.domain = rec.domain
    return result


def extract_signals(rec: ScrapeRecord, llm: Optional[ClaudeJSON], prompts_dir) -> tuple[ExtractionResult, list[str]]:
    """Run Claude extraction when available, else the deterministic extractor. Always grounded."""
    notes: list[str] = []
    result: Optional[ExtractionResult] = None
    if llm is not None:
        try:
            result = extract_with_claude(rec, llm, prompts_dir)
        except LLMUnavailable as exc:
            notes.append(f"Claude extraction unavailable ({exc}); used deterministic fallback.")
            log.warning("Claude extraction failed for %s: %s", rec.domain, exc)
    if result is None:
        result = extract_deterministic(rec)
        if llm is None:
            notes.append("Claude not configured — deterministic fallback extraction (not AI-verified).")
    result, dropped = ground_evidence(result, rec)
    if dropped:
        notes.append(f"Grounding check discarded {dropped} unsupported claim(s).")
    if not result.missing_information or result.provenance == "claude":
        result.missing_information = sorted(set(missing_information(result)) |
                                            {m for m in result.missing_information if ":" not in m})
    return result, notes
