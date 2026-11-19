import json

from src.contact_discovery import HunterProvider, ManualProvider, WebsiteTeamProvider, discover_contact, rank_contacts
from src.models import Contact, PageRecord, ScrapeRecord
from src.signal_extractor import extract_deterministic
from tests.conftest import FakeSession


def rec(pages=None) -> ScrapeRecord:
    r = ScrapeRecord(company="Acme", domain="acme.example", homepage_url="https://acme.example/", scraping_status="success")
    r.pages_scraped = pages or [PageRecord(url="https://acme.example/", category="homepage", text="Acme is a SaaS platform.")]
    return r


def hunter_payload(emails):
    return json.dumps({"data": {"domain": "acme.example", "emails": emails}})


def h(first, last, pos, email, conf=90, status="valid"):
    return {"value": email, "first_name": first, "last_name": last, "position": pos, "confidence": conf,
            "verification": {"status": status}, "department": "it", "sources": [{"uri": "https://acme.example/team"}]}


def hunter_with(settings, emails):
    sess = FakeSession({})
    sess.get = lambda url, params=None, timeout=None: type("R", (), {"status_code": 200, "json": lambda self: json.loads(hunter_payload(emails))})()
    return HunterProvider("key", settings.cache_dir, max_calls=5, session=sess)


def test_no_decision_maker_flags_for_review(settings):
    """Scenario 6: company qualifies but no decision-maker can be found → flagged, nothing invented."""
    settings.hunter_api_key = ""
    sel = discover_contact(rec(), None, settings)
    assert sel.status == "needs_review" and sel.contact is None
    assert "no contact was invented" in sel.selection_reasoning
    assert any("HUNTER_API_KEY not set" in n for n in sel.provider_notes)


def test_hunter_multiple_contacts_ranked_by_relevance_not_seniority(settings):
    """Scenario 7: Hunter returns several contacts; the security owner beats the CEO."""
    emails = [h("Ada", "Ceo", "Chief Executive Officer", "ada@acme.example"),
              h("Bo", "Sec", "Head of Security", "bo@acme.example"),
              h("Cy", "Tech", "CTO", "cy@acme.example"),
              h("Di", "Mkt", "VP Marketing", "di@acme.example"),
              h("Ed", "Wrong", "CISO", "ed@other-company.com")]
    sel = discover_contact(rec(), None, settings, hunter=hunter_with(settings, emails))
    assert sel.status == "selected"
    assert sel.contact.full_name == "Bo Sec"
    assert "Ed Wrong" not in sel.contact.full_name  # wrong-domain CISO is penalised
    assert len(sel.alternative_contacts) >= 3
    assert "Preferred over" in sel.selection_reasoning


def test_cto_preferred_when_no_security_function():
    contacts = [Contact(first_name="Cy", full_name="Cy T", job_title="CTO", email="cy@acme.example", source="t"),
                Contact(first_name="Vi", full_name="Vi E", job_title="VP of Engineering", email="vi@acme.example", source="t")]
    ranked = rank_contacts(contacts, "acme.example", None)
    assert ranked[0].contact.job_title == "CTO"
    assert any("No dedicated security leader" in r for r in ranked[0].reasons)


def test_incomplete_manual_mapping_rows_are_skipped(settings):
    """Scenario 8: contact mapping is incomplete."""
    settings.contacts_csv.write_text(
        "company,domain,first_name,last_name,job_title,email,verification_status,linkedin_url,source,source_url\n"
        "Acme,acme.example,,Nobody,CTO,,,,Apollo,\n"            # no first name
        "Acme,acme.example,Fay,,,,,,Apollo,\n"                  # no title
        "Acme,acme.example,Gus,Lee,VP Engineering,gus@acme.example,verified,,Apollo,\n")
    contacts, note = ManualProvider(settings.contacts_csv).find("acme.example", "Acme")
    assert [c.full_name for c in contacts] == ["Gus Lee"]
    assert "skipped 2 incomplete" in note
    settings.contact_providers = ["manual"]
    sel = discover_contact(rec(), None, settings)
    assert sel.status == "selected" and sel.contact.email == "gus@acme.example"


def test_hunter_quota_and_errors_handled(settings):
    hp = hunter_with(settings, [])
    hp.max_calls = 0
    contacts, note = hp.find("acme.example")
    assert contacts == [] and "quota" in note


def test_website_provider_ignores_customer_testimonials():
    pages = [PageRecord(url="https://acme.example/", category="homepage",
                        text="“Acme cut our incident time in half.”\nJane Roe, CTO"),
             PageRecord(url="https://acme.example/about", category="about",
                        text="Our team\nSam Park\nCTO and Co-founder\nBuilds the platform.")]
    found, _ = WebsiteTeamProvider().find(rec(pages))
    assert [c.full_name for c in found] == ["Sam Park"]
    assert found[0].email is None  # never guessed
