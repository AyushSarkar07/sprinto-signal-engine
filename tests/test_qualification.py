import json
from types import SimpleNamespace

import pytest

from src.llm import ClaudeJSON, LLMUnavailable
from src.models import Evidence, ExtractionResult, PageRecord, ScrapeRecord
from src.qualification_engine import FALLBACK_CONFIDENCE_CAP, qualify, score_timing
from src.scraper import finalise
from src.signal_extractor import extract_deterministic, extract_signals, ground_evidence, staleness_factor
from tests.conftest import SAAS_HOME, SECURITY_PAGE
from src.scraper import clean_html


def record(pages: dict[str, tuple[str, str]], company="Acme", domain="acme.example") -> ScrapeRecord:
    rec = ScrapeRecord(company=company, domain=domain, homepage_url=f"https://{domain}/")
    for url, (cat, html) in pages.items():
        rec.pages_scraped.append(PageRecord(url=url, category=cat, text=clean_html(html)[1]))
    return finalise(rec)


def text_page(body: str) -> str:
    return f"<html><body><main>{body}</main></body></html>"


LONG_FILLER = " ".join(["We help our community every single day with care."] * 8)


def test_non_saas_is_not_qualified_even_with_security_words():
    """Scenario 4: company is not a SaaS business."""
    rec = record({"https://cafe.example/": ("homepage", text_page(
        "<p>Visit our restaurants and see our menu.</p><p>Add to cart. Free shipping on coffee beans we roast daily.</p>"
        "<p>Shop now for gift cards.</p><p>Our stores use secure payment and we are GDPR compliant.</p>" + LONG_FILLER))},
        "Cafe", "cafe.example")
    ex = extract_deterministic(rec)
    q = qualify(ex, rec)
    assert ex.company_profile.is_saas is False
    assert q.decision_status == "not_qualified" and q.recommended_action == "disqualify"


def test_saas_without_buying_signals_is_nurture_not_outreach():
    """Scenario 5: SaaS business with no observable buying signals."""
    rec = record({
        "https://acme.example/": ("homepage", text_page(
            "<p>Acme is a B2B SaaS platform for finance teams.</p><p>Start your free trial or book a demo.</p>"
            "<p>Pricing per user per month.</p><p>Log in</p><p>Integrations and API.</p>"
            "<p>Trusted by finance teams at Fortune 500 companies including Globex.</p>")),
        "https://acme.example/about": ("about", text_page("<p>We raised a $40M Series B round in 2026 to grow the team. We are 150 employees.</p>")),
        "https://acme.example/pricing": ("pricing", text_page("<p>Enterprise plan with SSO and SAML and a dedicated account manager.</p>")),
    })
    ex = extract_deterministic(rec)
    q = qualify(ex, rec)
    assert q.icp_fit_score >= 55
    assert q.buying_timing_score < 35
    assert q.qualified is False and q.recommended_action == "nurture"
    assert any("wrong time" in r for r in q.qualification_reasoning)


def test_qualified_company_has_separate_scores_and_reasoning():
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE),
                  "https://acme.example/careers": ("careers", text_page("<p>JOB: Head of Security | Team: Security</p>")),
                  "https://acme.example/about": ("about", text_page("<p>Acme raised a $30M Series B funding round in 2026.</p>"))})
    ex = extract_deterministic(rec)
    q = qualify(ex, rec)
    assert q.decision_status == "qualified" and q.qualified
    assert len(q.icp_breakdown) == 6 and len(q.timing_breakdown) == 5
    assert sum(c.max_points for c in q.icp_breakdown) == 100 and sum(c.max_points for c in q.timing_breakdown) == 100
    assert q.evidence_confidence <= FALLBACK_CONFIDENCE_CAP  # fallback is never presented as AI-verified
    assert any("deterministic fallback" in r for r in q.qualification_reasoning)


def test_same_evidence_is_not_rewarded_twice_within_a_score():
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME), "https://acme.example/security": ("security", SECURITY_PAGE)})
    ex = extract_deterministic(rec)
    for breakdown in (qualify(ex, rec).icp_breakdown, score_timing(ex)[0]):
        ids = [i for c in breakdown for i in set(c.evidence_ids)]
        assert len(ids) == len(set(ids)), "an evidence ID was counted by two criteria"


def test_missing_information_is_not_negative_evidence():
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME)})
    ex = extract_deterministic(rec)
    q = qualify(ex, rec)
    stage = next(c for c in q.icp_breakdown if c.criterion.startswith("Relevant growth"))
    assert stage.points == 0 and "missing, not negative" in stage.rationale
    assert q.decision_status != "not_qualified" or q.recommended_action == "nurture"


def test_stale_evidence_is_down_weighted_and_competitor_penalised():
    assert staleness_factor("We raised our Series A in 2019")[0] == 0.5
    assert staleness_factor("Raised Series B in 2026")[0] == 1.0
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME),
                  "https://acme.example/security": ("security", text_page("<p>Our trust center is powered by Vanta. We are SOC 2 Type II certified.</p>"))})
    ex = extract_deterministic(rec)
    _, penalties = score_timing(ex)
    assert any("Vanta" in p for p in penalties)


def test_grounding_discards_fabricated_evidence():
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME)})
    ex = extract_deterministic(rec)
    fake = Evidence(finding="SOC 2 audit due next month", source_url="https://acme.example/",
                    excerpt="Our SOC 2 audit is due next month", confidence=0.9, category="certification_in_progress")
    ex.compliance_signals.soc2_mentions.append(fake)
    ex, dropped = ground_evidence(ex, rec)
    assert dropped >= 1 and fake.id not in {e.id for e in ex.all_evidence()}


# ---------- Claude JSON handling (scenarios 9 & 10)

class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def create(self, **kw):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=r)])


def fake_llm(tmp_path, replies):
    msgs = FakeMessages(replies)
    return ClaudeJSON("k", "claude-opus-5-5", tmp_path, client=SimpleNamespace(messages=msgs)), msgs


def _valid_extraction_json(url="https://acme.example/"):
    return json.dumps({"company_profile": {"company_name": "Acme", "domain": "acme.example", "is_saas": True,
                                           "is_saas_evidence": [{"finding": "SaaS", "source_url": url, "excerpt": "Acme is a B2B SaaS platform",
                                                                 "evidence_type": "explicit", "confidence": 0.9, "category": "saas_indicator"}]},
                       "provenance": "claude"})


def test_invalid_json_from_claude_is_repaired(tmp_path):
    """Scenario 9: Claude returns invalid JSON → controlled repair, never silently accepted."""
    llm, msgs = fake_llm(tmp_path, ["Sure! here is the data: {not json", _valid_extraction_json()])
    out = llm.call("sys", "user", ExtractionResult)
    assert msgs.calls == 2 and out.company_profile.is_saas is True


def test_persistently_invalid_json_raises_and_pipeline_falls_back(tmp_path, settings):
    llm, msgs = fake_llm(tmp_path, ["{}", '{"company_profile": 5}', "nope"])
    with pytest.raises(LLMUnavailable):
        llm.call("sys", "user2", ExtractionResult)
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME)})
    llm2, _ = fake_llm(tmp_path / "b", ["bad", "bad", "bad"])
    ex, notes = extract_signals(rec, llm2, settings.prompts_dir)
    assert ex.provenance == "deterministic_fallback"


def test_api_request_failure_falls_back_cleanly(tmp_path, settings):
    """Scenario 10: an API request fails → labelled deterministic fallback, no crash."""
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME)})
    llm, _ = fake_llm(tmp_path, [RuntimeError("503 upstream")])
    ex, notes = extract_signals(rec, llm, settings.prompts_dir)
    assert ex.provenance == "deterministic_fallback"
    assert any("unavailable" in n for n in notes)


def test_claude_evidence_is_grounded(tmp_path, settings):
    rec = record({"https://acme.example/": ("homepage", SAAS_HOME)})
    bad = json.loads(_valid_extraction_json())
    bad["company_profile"]["is_saas_evidence"].append({"finding": "x", "source_url": "https://acme.example/", "excerpt": "We are ISO 27001 certified",
                                                       "confidence": 0.9, "category": "certification_held"})
    llm, _ = fake_llm(tmp_path, [json.dumps(bad)])
    ex, notes = extract_signals(rec, llm, settings.prompts_dir)
    assert ex.provenance == "claude"
    assert len(ex.company_profile.is_saas_evidence) == 1  # the invented ISO claim was dropped
