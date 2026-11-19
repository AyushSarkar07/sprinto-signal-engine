from src.email_generator import BANNED, generate_email, word_count
from src.models import Contact, PageRecord, ScrapeRecord
from src.pain_point_engine import deterministic_pain_points
from src.scraper import clean_html, finalise
from src.signal_extractor import extract_deterministic
from tests.conftest import SAAS_HOME, SECURITY_PAGE


def setup():
    rec = ScrapeRecord(company="Acme", domain="acme.example", homepage_url="https://acme.example/")
    for url, cat, html in [("https://acme.example/", "homepage", SAAS_HOME), ("https://acme.example/security", "security", SECURITY_PAGE)]:
        rec.pages_scraped.append(PageRecord(url=url, category=cat, text=clean_html(html)[1]))
    rec = finalise(rec)
    ex = extract_deterministic(rec)
    contact = Contact(first_name="Sam", last_name="Park", full_name="Sam Park", job_title="CTO", email="sam@acme.example", source="test")
    return ex, contact


def test_pain_points_are_role_specific_and_evidenced():
    ex, contact = setup()
    pains = deterministic_pain_points(ex, contact, "CTO").pain_points
    assert 1 <= len(pains) <= 2
    for p in pains:
        assert p.supporting_evidence and p.basis in ("observed", "inferred") and 0 < p.confidence <= 1
        assert "CTO" in p.reasoning or "Sam" in p.reasoning or "Acme" in p.reasoning
    assert pains[0].basis == "observed"  # SOC 2 work in progress is directly observed


def test_email_obeys_writing_rules_and_traces_evidence(settings):
    ex, contact = setup()
    pains = deterministic_pain_points(ex, contact, "CTO").pain_points
    email = generate_email(ex, contact, "CTO", pains, None, settings.prompts_dir, "Test Sender")
    assert email is not None
    assert all(email.quality_checks.values()), email.quality_checks
    assert 60 <= word_count(email.email_body) <= 110
    assert email.email_body.startswith("Hi Sam,")
    assert email.hook_source_url.startswith("https://acme.example")
    assert not any(b in email.email_body.lower() for b in BANNED)
    assert len(email.subject_candidates) == 3 and email.subject in email.subject_candidates
    assert email.evidence_to_email_trace[0].source_url == email.hook_source_url
    assert email.provenance == "deterministic_fallback"


def test_no_hook_means_no_email(settings):
    ex, contact = setup()
    ex.potential_buying_moments = []
    pains = deterministic_pain_points(ex, contact, "CTO").pain_points
    assert generate_email(ex, contact, "CTO", pains, None, settings.prompts_dir) is None


def test_email_never_implies_a_security_hire_that_was_not_observed():
    from src.email_generator import compose_deterministic
    from src.models import BuyingMoment, CompanyProfile, Contact, ExtractionResult, PainPoint
    ex = ExtractionResult(company_profile=CompanyProfile(company_name="Acme", domain="acme.example"))
    hook = BuyingMoment(signal="Funding", category="funding", source_url="https://acme.example/", evidence="Raised $40M Series B",
                        why_it_matters="x", confidence=0.8, hook_phrase="your recent Series B announcement")
    pain = PainPoint(pain_point="Standing up a compliance programme before a dedicated security team exists", basis="inferred",
                     reasoning="r", confidence=0.6)
    c = Contact(first_name="Jo", full_name="Jo Doe", job_title="CTO", source="test")
    body = compose_deterministic(ex, c, "CTO", pain, hook, "").email_body
    assert "hire" not in body.lower() and "Who owns compliance at Acme" in body
