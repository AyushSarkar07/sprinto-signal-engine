"""Guardrails against false buying signals (found reviewing Rootly, Plain and Attio by hand)."""

from __future__ import annotations

from src.qualification_engine import qualify
from src.scraper import detect_trust_platform
from src.signal_extractor import extract_deterministic
from tests.conftest import SAAS_HOME
from tests.test_qualification import record, text_page


def gate(pages):
    rec = record(pages)
    q = qualify(extract_deterministic(rec), rec)
    return q, {a["key"]: a for a in q.evidence_map}


def test_trust_platform_read_from_page_source_not_from_vendor_config():
    vanta = "<html><head><title>Plain Trust Center</title><script src='https://x/vanta-entry-loader.js'></script></head><body></body></html>"
    assert detect_trust_platform(vanta, "Plain Trust Center", "https://trust.plain.com/") == ("Vanta", "vanta-entry-loader")
    # A SafeBase page carries Drata hosts in its own configuration; that is SafeBase's code, not the company's choice.
    safebase = ('<title>Rootly Trust Center | Powered by SafeBase</title><script>{"NEXT_PUBLIC_DRATA_APP_DOMAIN_WHITELIST":'
                '"app.drata.com","NEXT_PUBLIC_SITE":"https://app.safebase.io"}</script>')
    assert detect_trust_platform(safebase, "Rootly Trust Center | Powered by SafeBase", "https://security.rootly.com/")[0] == "SafeBase"
    # Only trust-like pages are checked: a marketing page that mentions Vanta is not a platform.
    assert detect_trust_platform("<p>powered by vanta</p>", "Blog", "https://acme.example/blog") is None


def test_trust_centre_buttons_and_offered_dpa_are_not_buying_signals():
    trust = ("Trust centre platform: SafeBase (found 'powered by safebase' in the page source)\n" +
             "Start your security review. Get access. We are SOC 2 Type II certified and GDPR compliant.")
    sec = text_page("<p>We are SOC 2 Type II certified.</p><p>Customers can sign our Data Processing Agreement (DPA) and review subprocessors.</p>")
    q, a = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", sec),
                 "https://trust.acme.example/": ("trust", f"<html><body><main><p>{trust}</p></main></body></html>"),
                 "https://acme.example/about": ("about", text_page("<p>We are 120 employees building finance software.</p>"))})
    assert a["audit_intent"]["answer"] == "no" and "Mature programme" in a["audit_intent"]["basis"]
    assert q.gate_decision == "NURTURE" and not q.qualified


def test_vanta_trust_centre_drops_the_account():
    trust = "Trust centre platform: Vanta (found 'vanta-entry-loader' in the page source)"
    q, a = gate({"https://acme.example/": ("homepage", SAAS_HOME),
                 "https://trust.acme.example/": ("trust", f"<html><body><main><p>{trust}</p></main></body></html>"),
                 "https://acme.example/careers": ("careers", text_page("<p>JOB: Head of Security | Team: Security</p>"))})
    assert a["competitor_vendor"]["answer"] == "no" and q.gate_decision == "DROP"
    assert a["certifications"]["answer"] == "unknown"  # a JavaScript trust centre hides its certifications


def test_a_real_forward_signal_still_qualifies():
    sec = text_page("<p>We are currently working towards SOC 2 Type II and expect our report in Q2.</p>")
    q, a = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", sec),
                 "https://acme.example/about": ("about", text_page("<p>We are 120 employees.</p>"))})
    assert a["audit_intent"]["answer"] == "yes" and "Forward-looking" in a["audit_intent"]["basis"]
    assert q.gate_decision == "QUALIFY"


def test_testimonials_and_fortune_500_are_not_customer_counts_and_hipaa_is_not_an_industry():
    home = text_page("<h1>Acme is a SaaS platform for incident response</h1><p>Start for free. Book a demo. Log in.</p>"
                     "<p>Loved by fast-growing startups and the Fortune 500.</p><p>“We love Acme, our team moved fast.”</p>")
    sec = text_page("<p>SOC2, HIPAA, GDPR compliant.</p><p>Cyber Insurance</p>")
    q, a = gate({"https://acme.example/": ("homepage", home), "https://acme.example/security": ("security", sec)})
    assert a["clients"]["answer"] == "yes" and "Fortune" in a["clients"]["basis"]
    assert a["industry"]["answer"] == "unknown"
