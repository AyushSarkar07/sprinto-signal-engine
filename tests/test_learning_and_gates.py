"""Hard gates, recency rules, the feedback loop, run history and the funding-news shortlist."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace as NS

from src import evidence_map as em
from src import feedback_loop as fl
from src.lead_finder import parse_headline, rank_lead, resolve_domain
from src.models import Evidence
from src.qualification_engine import qualify
from src.run_history import summarise
from src.signal_extractor import extract_deterministic
from tests.conftest import SAAS_HOME, SECURITY_PAGE
from tests.test_qualification import record, text_page

CAREERS = ("careers", text_page("<p>JOB: Head of Security | Team: Security</p>"))


def gate(pages):
    rec = record(pages)
    q = qualify(extract_deterministic(rec), rec)
    return q, {a["key"]: a for a in q.evidence_map}


# ---------------------------------------------------------------- gates

def test_holding_every_framework_drops_the_company():
    sec = text_page("<p>We are SOC 2 Type II certified and ISO 27001 certified.</p><p>We are fully GDPR compliant for EU customers.</p>")
    q, a = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", sec),
                 "https://acme.example/careers": CAREERS})
    assert a["certifications"]["answer"] == "no" and a["certifications"]["role"] == "gate"
    assert q.gate_decision == "DROP" and any("Short-circuit" in r for r in q.qualification_reasoning)


def test_competitor_trust_centre_drops_but_a_passing_mention_does_not():
    trust = text_page("<p>Our trust center is powered by Vanta. Request our SOC 2 report.</p>")
    q, a = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://trust.acme.example/": ("trust", trust),
                 "https://acme.example/careers": CAREERS})
    assert a["competitor_vendor"]["answer"] == "no" and q.gate_decision == "DROP"
    blog = text_page("<p>We compared Vanta, Drata and others in this article about compliance tools.</p>")
    q2, a2 = gate({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE),
                   "https://acme.example/blog/tools": ("news", blog), "https://acme.example/careers": CAREERS})
    assert a2["competitor_vendor"]["answer"] == "yes"


def test_old_funding_round_does_not_count_but_headcount_still_can(monkeypatch):
    monkeypatch.setattr(em, "TODAY", lambda: dt.date(2026, 11, 1))
    old = em.Ctx(NS(company_profile=NS(funding_stage=NS(value="Series A", evidence=Evidence(
        finding="f", source_url="u", excerpt="Latest funding: Series A round (2023-08).", confidence=0.8)),
        employee_range=NS(value=None, evidence=None))), None, 0)
    ans, basis, *_ = em._growth(old)
    assert ans == "unknown" and "months ago" in basis
    old.r.company_profile.employee_range = NS(value="92 employees", evidence=None)
    ans, basis, *_ = em._growth(old)
    assert ans == "yes" and "only headcount counts" in basis


def test_stale_job_posts_are_ignored_for_audit_intent(monkeypatch):
    monkeypatch.setattr(em, "TODAY", lambda: dt.date(2026, 11, 20))
    assert em.days_old("JOB: Head of Security | posted: 2026-11-16") == 4
    assert em.days_old("JOB: GRC Lead | posted: 2026-01-02") > em.AUDIT_SIGNAL_MAX_DAYS
    assert em.days_old("JOB: GRC Lead") is None


# ---------------------------------------------------------------- feedback loop

ORIG = "Hi Jo,\n\nNoticed your trust centre says \"Start your security review\". That usually means questionnaires sit in the sales cycle.\n\nIf it's relevant, would a 20-minute conversation be useful?\n\nBest,\nX"
EDIT = "Hi Jo,\n\nNoticed your trust centre says \"Start your security review\".\n\nOpen to a 15-minute call next week?\n\nBest,\nX"


def test_edit_ops_find_sentence_swaps_and_deletions():
    ops = fl.edit_ops(ORIG, EDIT)
    assert ("drop", "That usually means questionnaires sit in the sales cycle.", "") in ops
    assert ("replace", "If it's relevant, would a 20-minute conversation be useful?", "Open to a 15-minute call next week?") in ops


def test_one_edit_teaches_nothing_two_identical_edits_become_learnings(tmp_path):
    one = [{"slug": "a", "status": "approved", "original_body": ORIG, "approved_body": EDIT}]
    assert fl.learn(tmp_path, one) == []
    two = one + [{"slug": "b", "status": "approved", "original_body": ORIG.replace("Jo", "Sam"), "approved_body": EDIT.replace("Jo", "Sam")}]
    kinds = {l["kind"] for l in fl.learn(tmp_path, two)}
    assert {"replace_sentence", "drop_sentence"} <= kinds


def test_learnings_apply_but_never_touch_the_hook(tmp_path):
    reviews = [{"slug": s, "status": "approved", "original_body": ORIG, "approved_body": EDIT} for s in ("a", "b")]
    learns = fl.learn(tmp_path, reviews)
    body, applied = fl.apply_to_body(ORIG, learns, protect='Noticed your trust centre says "Start your security review".')
    assert "Open to a 15-minute call next week?" in body and "sales cycle" not in body
    assert 'Start your security review' in body and len(applied) == 2
    fl.retire(tmp_path, learns[0]["id"])
    assert len(fl.active_writer_learnings(tmp_path)) == 1


def test_ratings_and_overrides_become_signals_and_learnings(tmp_path):
    for s in ("a", "b"):
        fl.rate(tmp_path, s, s.upper(), "down", ["could be any company", "not-a-tag"])
    for s in ("c", "d"):
        fl.set_override(tmp_path, s, s.upper(), "drop", "consumer app", flagged_for="Unknown: Is it a SaaS business?")
    learns = fl.learn(tmp_path, [])
    assert any(l["kind"] == "writer_note" and "only this account" in l["lesson"] for l in learns)
    assert any(l["kind"] == "gate_pattern" for l in learns)
    assert all("not-a-tag" not in str(s["data"]) for s in fl.signals(tmp_path))


def test_override_needs_a_reason_and_forces_the_decision(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        fl.set_override(tmp_path, "a", "A", "qualify", "  ")
    q = NS(qualified=False, decision_status="insufficient_data", recommended_action="manual_review", gate_decision="HAND_TO_HUMAN",
           qualification_reasoning=["rules"], review_flags=["x"])
    fl.apply_override(q, {"decision": "QUALIFY", "reason": "checked LinkedIn: 120 staff"})
    assert q.qualified and q.gate_decision == "QUALIFY" and q.qualification_reasoning[0].startswith("Human override")


# ---------------------------------------------------------------- run history + funding news

def test_run_summary_counts_hits_flags_and_drop_reasons():
    def run(gate_, qualified, contact=True, sc=None):
        q = NS(qualified=qualified, gate_decision=gate_, qualification_reasoning=["x"],
               evidence_map=[{"question": "Is it a SaaS business?", "short_circuit_hit": sc, "core": True, "answer": "no" if sc else "yes"}])
        return NS(company="C", qualification=q, scrape=NS(scraping_status="success", ok_pages=lambda: [1, 2, 3]),
                  contact_selection=NS(status="selected" if contact else "needs_review"), email=None)
    s = summarise([run("QUALIFY", True), run("QUALIFY", True, contact=False), run("DROP", False, sc="Not SaaS")], budget=8)
    assert s["qualified"] == 2 and s["dropped"] == 1 and s["needs_human"] == 1
    assert s["drop_reasons"] == {"Is it a SaaS business?": 1} and s["human_reasons"] == {"No decision-maker found": 1}
    assert s["pages_per_company"] == 3


def test_funding_headlines_are_parsed_ranked_and_resolved():
    assert parse_headline("Fintech Startup Rillet Lands $70M Series B From a16z") == ("Rillet", "Series B")
    assert parse_headline("Why markets fell today") is None
    assert rank_lead("Series A", "B2B SaaS platform raises", 20) > rank_lead("Seed", "consumer app raises", 400)
    pages = {"https://rillet.com": (True, "Rillet | AI-native ERP")}
    assert resolve_domain("Rillet", lambda u: pages.get(u, (False, "")))[0] == "rillet.com"
    dom, note = resolve_domain("Nomad", lambda u: (True, "Parked domain"))
    assert dom == "" and "unresolved" in note


def test_account_specific_rewrites_never_become_lessons(tmp_path):
    """A reviewer's sentence with one company's facts must not be copied into other companies' emails."""
    assert fl.is_generic("Open to a 15-minute call next week?")
    assert not fl.is_generic("Congrats on the $70M Series B in August.")
    assert not fl.is_generic("Saw that Rillet just hired a GRC analyst.")
    specific = "Congrats on the $70M round in August."
    reviews = [{"slug": s, "status": "approved", "original_body": ORIG,
                "approved_body": ORIG.replace("If it's relevant, would a 20-minute conversation be useful?", specific)} for s in ("a", "b")]
    assert not any(l["kind"] == "replace_sentence" for l in fl.learn(tmp_path, reviews))
