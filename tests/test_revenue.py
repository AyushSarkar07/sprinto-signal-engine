"""Revenue & conversion tracking: measured vs estimated separation, funnel maths, EV ranking, safe optimisation."""

from __future__ import annotations

import random
from types import SimpleNamespace as NS

import pytest

from src import revenue_tracker as rt
from src.models import PainPoint

QUESTIONNAIRE = "Security questionnaires and vendor reviews slowing enterprise deals"
AUDIT = "Audit evidence collection pulling engineers off the roadmap during the SOC 2 window"


def run(name, timing=40, qualified=True, contact=True, pain=QUESTIONNAIRE, employees=None):
    return NS(company=name, domain=f"{name.lower()}.com", slug=name.lower(),
              scrape=NS(scraping_status="success"),
              extraction=NS(company_profile=NS(employee_range=NS(value=employees))),
              qualification=NS(qualified=qualified, icp_fit_score=70, buying_timing_score=timing),
              contact_selection=NS(status="selected" if contact else "needs_review"),
              email=NS(pain_point_used=pain) if contact else None)


def outcome(company, stage, value=0.0):
    return {"company": company, "domain": "", "stage": stage, "deal_value": value, "key": company.lower()}


def test_no_outcomes_means_zero_measured_revenue_and_labelled_estimates():
    rep = rt.analyse([run("Acme"), run("Beta", qualified=False)], [], rt.Assumptions())
    assert rep["revenue"]["won_revenue"] == 0 and rep["revenue"]["deals_won"] == 0
    assert rep["revenue"]["expected_revenue"] > 0
    assert rep["conversion"]["contacted_to_reply"] == "no data"
    assert any("ESTIMATES" in r for r in rt.recommendations(rep))


def test_funnel_counts_and_won_revenue_from_logged_outcomes():
    runs = [run("Acme"), run("Beta"), run("Gamma", contact=False), run("Delta", qualified=False)]
    outs = [outcome("Acme", "contacted"), outcome("Acme", "replied"), outcome("Acme", "won", 15000),
            outcome("Beta", "contacted"), outcome("Beta", "lost")]
    rep = rt.analyse(runs, outs, rt.Assumptions())
    funnel = dict(rep["funnel"])
    assert funnel["Prospects"] == 4 and funnel["Qualified"] == 3 and funnel["Decision-maker found"] == 2
    assert funnel["Contacted"] == 2 and funnel["Replied"] == 1 and funnel["Won"] == 1
    assert rep["revenue"]["won_revenue"] == 15000 and rep["revenue"]["avg_deal_size"] == 15000
    assert rep["conversion"]["contacted_to_won_observed"] == "1/2"
    assert rep["stage_rates"]["replied"]["observed"] == "1/2"
    # closed companies (won / lost) leave the priority queue
    assert {x["company"] for x in rep["priority_queue"]} == {"Gamma"}


def test_in_progress_companies_do_not_count_as_failures():
    statuses = list(rt.company_status([outcome("A", "contacted"), outcome("B", "contacted"), outcome("B", "lost")]).values())
    assert rt.beta_counts(statuses)["replied"] == (0, 1)  # A is still waiting, only B is a decided failure


def test_posterior_moves_from_prior_toward_data():
    a = rt.Assumptions()
    prior = rt.stage_rates(a, {})["replied"]["posterior_mean"]
    learned = rt.stage_rates(a, {"replied": (8, 20)})["replied"]["posterior_mean"]
    assert prior == pytest.approx(0.05) and learned > 0.2


def test_priority_queue_ranks_by_expected_revenue_and_flags_blocked_value():
    runs = [run("Low", timing=10), run("High", timing=60, employees="900 employees"), run("NoContact", contact=False)]
    rep = rt.analyse(runs, [], rt.Assumptions())
    q = rep["priority_queue"]
    assert q[0]["company"] == "High" and q[0]["acv"] == 25000
    assert [x["expected_revenue"] for x in q] == sorted((x["expected_revenue"] for x in q), reverse=True)
    assert rep["revenue"]["blocked_no_contact"] > 0
    assert any("NoContact" in r and "blocked" in r for r in rt.recommendations(rep))


def test_recorded_deal_value_overrides_assumed_acv():
    rep = rt.analyse([run("Acme")], [outcome("Acme", "opportunity", 40000)], rt.Assumptions())
    x = rep["priority_queue"][0]
    assert x["acv"] == 40000 and x["acv_basis"] == "recorded deal value"
    assert rep["revenue"]["open_pipeline_value"] == 40000


def test_record_outcome_validates_and_appends(tmp_path):
    path = tmp_path / "outcomes.csv"
    rt.record_outcome(path, "Acme", "Replied")
    rt.record_outcome(path, "Acme", "won", 12000)
    with pytest.raises(ValueError):
        rt.record_outcome(path, "Acme", "signed-maybe")
    with pytest.raises(ValueError):
        rt.record_outcome(path, "Acme", "won", -5)
    rows = rt.read_outcomes(path)
    assert [r["stage"] for r in rows] == ["replied", "won"] and rows[1]["deal_value"] == 12000


def test_optimizer_inactive_until_enough_data_keeps_evidence_order():
    pains = [PainPoint(pain_point=AUDIT, basis="observed", reasoning="r", confidence=0.8),
             PainPoint(pain_point=QUESTIONNAIRE, basis="inferred", reasoning="r", confidence=0.7)]
    opt = rt.VariantOptimizer({"questionnaires": (3, 4)}, min_sends=10)
    assert not opt.active and opt.rank(pains) == pains


def test_optimizer_favours_winning_angle_but_only_among_supported_pains():
    strong = PainPoint(pain_point=AUDIT, basis="observed", reasoning="r", confidence=0.8)
    winner = PainPoint(pain_point=QUESTIONNAIRE, basis="inferred", reasoning="r", confidence=0.7)
    weak = PainPoint(pain_point=QUESTIONNAIRE, basis="inferred", reasoning="r", confidence=0.3)
    opt = rt.VariantOptimizer({"questionnaires": (9, 10), "audit_evidence": (0, 10)}, min_sends=10, rng=random.Random(1))
    assert sum(opt.rank([strong, winner])[0] is winner for _ in range(50)) >= 45
    # a low-confidence pain point is never promoted, however well its family converts
    assert opt.rank([strong, weak])[0] is strong


def test_family_stats_join_outcomes_to_sent_angle():
    runs = [run("A", pain=QUESTIONNAIRE), run("B", pain=QUESTIONNAIRE), run("C", pain=AUDIT)]
    st = rt.company_status([outcome("A", "replied"), outcome("B", "contacted"), outcome("C", "contacted")])
    assert rt.family_stats(runs, st) == {"questionnaires": (1, 2), "audit_evidence": (0, 1)}


def test_outputs_written(tmp_path):
    rep = rt.analyse([run("Acme")], [], rt.Assumptions())
    paths = rt.write_revenue_outputs(rep, tmp_path)
    text = paths["report"].read_text()
    assert "Measured" in text and "Estimated" in text and "Acme" in paths["queue"].read_text()


def test_open_rate_tracked_and_reply_implies_open():
    outs = [outcome("A", "contacted"), outcome("A", "opened"), outcome("B", "contacted"), outcome("C", "replied")]
    rep = rt.analyse([run("A"), run("B"), run("C")], outs, rt.Assumptions())
    assert rep["conversion"]["open_rate"] == "2/3"   # A opened, C replied (so opened), B not
    assert dict(rep["funnel"])["Opened"] == 2


def test_heavy_reviewer_edits_produce_a_recommendation():
    review = {"drafts": 4, "pending": 0, "approved": 4, "rejected": 0, "approval_rate": 1.0, "avg_change": 0.55,
              "heavy_edit_rate": 0.75, "heavy_edit_by_family": {"questionnaires": {"approved": 4, "heavy": 3, "avg_change": 0.55}}}
    rep = rt.analyse([run("A")], [], rt.Assumptions(), review)
    assert any("rewrote more than half" in r and "questionnaires" in r for r in rt.recommendations(rep))
