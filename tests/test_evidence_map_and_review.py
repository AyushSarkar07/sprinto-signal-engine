"""Evidence Map gate, external evidence sources, and the human review gate."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from src import evidence_map as em
from src import review_gate as rg
from src.external_sources import add_external_pages, enrichment_page, news_pages, read_enrichment
from src.qualification_engine import qualify
from src.signal_extractor import extract_deterministic
from tests.conftest import FakeResp, SAAS_HOME, SECURITY_PAGE
from tests.test_qualification import LONG_FILLER, record, text_page

SEC_CAREERS = ("careers", text_page("<p>JOB: Head of Security | Team: Security</p>"))


def gate(pages):
    rec = record(pages)
    q = qualify(extract_deterministic(rec), rec)
    return q, {a["key"]: a["answer"] for a in q.evidence_map}


def test_all_three_core_yes_qualifies():
    q, ans = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE),
                   "https://acme.example/careers": SEC_CAREERS,
                   "https://acme.example/about": ("about", text_page("<p>Acme raised a $30M Series B funding round in 2026.</p>"))})
    assert ans["saas"] == ans["growth_stage"] == ans["audit_intent"] == "yes"
    assert q.gate_decision == "QUALIFY" and q.qualified and not q.review_flags


def test_two_yes_one_unknown_is_qualify_and_flag_with_a_review_flag():
    """'Two of three answered, one unknown' → qualify-and-flag (growth stage unknown)."""
    q, ans = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE),
                   "https://acme.example/careers": SEC_CAREERS})
    assert ans["growth_stage"] == "unknown"
    assert q.gate_decision == "QUALIFY_AND_FLAG" and q.qualified
    assert q.review_flags and "Series A–C" in q.review_flags[0]


def test_unknown_audit_intent_follows_its_if_unanswered_rule_nurture():
    q, _ = gate({"https://acme.example/": ("homepage", SAAS_HOME),
                 "https://acme.example/about": ("about", text_page("<p>We are 120 employees. " + LONG_FILLER + "</p>"))})
    assert q.gate_decision == "NURTURE" and not q.qualified and q.recommended_action == "nurture"


def test_non_saas_short_circuits_to_drop():
    q, ans = gate({"https://cafe.example/": ("homepage", text_page(
        "<h1>Fresh salads</h1><p>Visit our restaurant locations and order food for pickup. Our menu changes seasonally. "
        + LONG_FILLER + "</p>"))})
    if ans["saas"] == "no":
        assert q.gate_decision == "DROP" and any("Short-circuit" in r for r in q.qualification_reasoning)
    else:  # extractor could not decide → never an automatic drop
        assert q.gate_decision in ("HAND_TO_HUMAN", "NURTURE")


def test_growth_band_is_code_checkable():
    ctx = lambda emp, stage: em.Ctx(NS(company_profile=NS(funding_stage=NS(value=stage, evidence=None),
                                                         employee_range=NS(value=emp, evidence=None))), None, 0)
    assert em._growth(ctx("150 employees", None))[0] == "yes"
    assert em._growth(ctx(None, "Series B"))[0] == "yes"
    assert em._growth(ctx("2,500 employees", "Series E"))[0] == "no"
    assert em._growth(ctx("2,500 employees", "Series B"))[0] == "yes"   # either answer settles it
    assert em._growth(ctx(None, None))[0] == "unknown"


def test_unreadable_site_is_handed_to_a_human_never_dropped():
    rec = record({"https://x.example/": ("homepage", text_page("<p>Loading…</p>"))})
    q = qualify(extract_deterministic(rec), rec)
    assert q.gate_decision == "HAND_TO_HUMAN" and q.decision_status == "insufficient_data"


def test_evidence_map_table_has_every_column():
    for row in em.map_table():
        assert len(row) == 8 and all(row[:6])


# ---------------------------------------------------------------- external sources

def test_enrichment_rows_become_a_citable_page_and_feed_the_gate(tmp_path):
    csv_path = tmp_path / "enrich.csv"
    csv_path.write_text("domain,field,value,source,source_url,retrieved\n"
                        "acme.example,employee_count,140,Apollo.io,,2026-11-03\n"
                        "acme.example,technologies,Amazon AWS; Slack,Apollo.io,,2026-11-03\n"
                        "acme.example,funding_stage,Series B,,,\n")  # no source → ignored
    rows = read_enrichment(csv_path)["acme.example"]
    assert [r["field"] for r in rows] == ["employee_count", "technologies"]
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE),
                  "https://acme.example/careers": SEC_CAREERS})
    s = NS(enrichment_csv=csv_path, search_provider="", serper_api_key="", request_timeout=2)
    notes = add_external_pages(rec, "Acme", s)
    assert any("Apollo.io company record" in n for n in notes) and any("robots" in n for n in notes)
    q = qualify(extract_deterministic(rec), rec)
    ans = {a["key"]: a for a in q.evidence_map}
    assert ans["growth_stage"]["answer"] == "yes" and ans["cloud_stack"]["answer"] == "yes"
    assert q.gate_decision == "QUALIFY"
    assert "Apollo.io" in enrichment_page("acme.example", rows).text


def test_news_keeps_only_headlines_naming_the_company_and_hides_key():
    body = {"news": [
        {"title": "Acme raises $40M Series B to automate finance", "link": "https://news.example/a", "snippet": "", "source": "TC"},
        {"title": "Acmeville council approves budget", "link": "https://news.example/b", "snippet": "funding", "source": "X"},
        {"title": "Why plain language matters; startup raises seed", "link": "https://news.example/c", "snippet": "", "source": "Y"},
    ]}
    calls = []

    class S:
        def post(self, url, json=None, headers=None, timeout=None):
            calls.append((url, headers))
            return FakeResp(200, __import__("json").dumps(body), url)

    pages = news_pages("Acme", "acme.example", "KEY", session=S())
    assert [p.url for p in pages] == ["https://news.example/a"] and pages[0].category == "news"
    assert calls[0][0].endswith("/news") and "news.google.com" not in calls[0][0]
    assert news_pages("Plain", "plain.com", "KEY", session=S()) == []   # common-word name needs a tight match
    assert news_pages("Acme", "acme.example", "") == []                 # no key → no call


# ---------------------------------------------------------------- review gate

EMAIL = NS(subject="security reviews at Acme", email_body="Hi Jo,\n\nNoticed your trust centre.\n\nBest,\nSprinto",
           hook_source_url="https://acme.example/trust")


def test_review_gate_blocks_until_approved_and_measures_edits(tmp_path):
    rec = rg.submit("acme", "Acme", EMAIL, ["Unknown: growth stage"], "questionnaires", tmp_path)
    assert rec["status"] == "pending"
    draft = tmp_path / "review" / "acme.txt"
    assert "! Unknown: growth stage" in draft.read_text()
    approved = rg.approve("acme", tmp_path)
    assert approved["change_ratio"] == 0 and not approved["heavy_edit"]
    # submitting again never overwrites a human decision
    assert rg.submit("acme", "Acme", EMAIL, [], "questionnaires", tmp_path)["status"] == "approved"


def test_heavy_edit_over_50_percent_is_counted(tmp_path):
    rg.submit("acme", "Acme", EMAIL, [], "questionnaires", tmp_path)
    draft = tmp_path / "review" / "acme.txt"
    head = draft.read_text().split(rg.MARK)[0]
    draft.write_text(head + rg.MARK + "\nSubject: quick question for Jo\n\nHello Jo, saw your new SOC 2 hire on the careers page "
                     "and wondered how evidence collection is going so far this quarter.\n\nThanks,\nAyush\n")
    rec = rg.approve("acme", tmp_path)
    assert rec["change_ratio"] > 0.5 and rec["heavy_edit"]
    st = rg.stats(tmp_path)
    assert st["heavy_edit_rate"] == 1.0 and st["heavy_edit_by_family"]["questionnaires"]["heavy"] == 1


def test_reject_and_missing_subject(tmp_path):
    rg.submit("acme", "Acme", EMAIL, [], "other", tmp_path)
    draft = tmp_path / "review" / "acme.txt"
    draft.write_text(draft.read_text().replace("Subject: ", "Subj "))
    with pytest.raises(ValueError):
        rg.approve("acme", tmp_path)
    assert rg.reject("acme", tmp_path, "hook too weak")["status"] == "rejected"
    assert rg.stats(tmp_path)["approval_rate"] == 0


def test_pipeline_never_dispatches_before_review_then_sends_the_edited_version(settings):
    """End to end: a qualified company's draft waits at the gate; after approval the EDITED text is what goes out."""
    from src.pipeline import Pipeline
    from src.scraper import Scraper
    from tests.conftest import FakeSession
    careers = text_page("<p>JOB: Head of Security | Team: Security</p>")
    routes = {"https://acme.example": (200, SAAS_HOME), "https://acme.example/security": (200, SECURITY_PAGE),
              "https://acme.example/careers": (200, careers)}
    settings.contacts_csv.write_text("company,domain,first_name,last_name,job_title,email,verification_status,linkedin_url,source,source_url\n"
                                     "Acme,acme.example,Jo,Doe,CTO,,,,test fixture,\n")
    sc = Scraper(settings.cache_dir, timeout=1, delay=0, session=FakeSession(routes))
    pipe = Pipeline(settings, None, scraper=sc)
    sent = []
    real = pipe.dispatcher.dispatch
    pipe.dispatcher.dispatch = lambda email, *a, **k: (sent.append(email), real(email, *a, **k))[1]
    run = pipe.run([("Acme", "acme.example")])[0][0]
    assert run.qualification.qualified and run.email is not None
    assert run.dispatch.status == "pending_review" and not sent
    draft = settings.output_dir / "review" / f"{run.slug}.txt"
    draft.write_text(draft.read_text().replace("Hi Jo,", "Hi Jo — quick one,"))
    rg.approve(run.slug, settings.output_dir)
    res = pipe.send_reviewed(run)
    assert res.status == "dry_run_preview" and "Hi Jo — quick one," in sent[0].email_body
