"""Control panel: forged requests blocked, input validated, review edits saved; lead finder never guesses."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from src import review_gate as rg
from src.lead_finder import find_leads
from tests.conftest import FakeResp


@pytest.fixture
def client(settings, monkeypatch):
    import app as panel
    monkeypatch.setattr(panel, "settings", lambda: settings)
    monkeypatch.setattr(panel, "start_job", lambda title, prospects, resume=False: panel.FLASH.append(f"started {prospects}") or True)
    monkeypatch.setattr(panel, "add_to_prospects", lambda c, d: True)
    panel.app.config["TESTING"] = True
    return panel, panel.app.test_client()


def test_posts_without_the_session_token_are_rejected(client):
    panel, c = client
    for path in ("/research", "/rerun", "/leads", "/review", "/outcome", "/publish", "/find", "/override", "/rate", "/retire"):
        assert c.post(path, data={"domain": "acme.com"}).status_code == 403


def test_research_validates_the_domain_and_starts_a_run(client):
    panel, c = client
    c.post("/research", data={"token": panel.TOKEN, "company": "Acme", "domain": "javascript:alert(1)"})
    assert any("not a valid website" in m for m in panel.FLASH) and not any(m.startswith("started") for m in panel.FLASH)
    panel.FLASH.clear()
    c.post("/research", data={"token": panel.TOKEN, "company": "Acme", "domain": "https://www.Acme.com/pricing"})
    assert any("started [('Acme', 'acme.com')]" in m for m in panel.FLASH)


def test_every_page_renders_without_any_runs(client):
    panel, c = client
    assert "Signal Engine overview" in c.get("/app").get_data(as_text=True)
    run = c.get("/run").get_data(as_text=True)
    assert "Research these websites" in run and "Scan funding news" in run and panel.TOKEN in run
    for path in ("/companies", "/review", "/drafts", "/loop"):
        assert c.get(path).status_code == 200


def test_research_accepts_up_to_three_domains(client):
    panel, c = client
    c.post("/research", data={"token": panel.TOKEN, "domains": "acme.com, beta.io\ngamma.ai delta.dev"})
    started = [m for m in panel.FLASH if m.startswith("started")]
    assert started and "delta.dev" not in started[0] and "gamma.ai" in started[0]


def test_review_edits_are_saved_in_the_reviewer_file(tmp_path):
    email = NS(subject="s", email_body="Hi Jo,\n\nBody.\n\nBest,\nX", hook_source_url="https://acme.example/")
    rg.submit("acme", "Acme", email, [], "other", tmp_path)
    rg.write_edited("acme", tmp_path, "New subject\r\n", "Hi Jo,\r\n\r\nShorter.\r\n")
    assert rg.read_edited("acme", tmp_path) == ("New subject", "Hi Jo,\n\nShorter.")
    assert rg.approve("acme", tmp_path)["change_ratio"] > 0


def test_lead_finder_needs_a_key_and_filters_noise_and_known_domains():
    items, notes = find_leads("", set())
    assert items == [] and "SERPER_API_KEY" in notes[0]
    body = {"organic": [
        {"title": "Security | Acme", "link": "https://trust.acme.io/", "snippet": "We are working towards SOC 2"},
        {"title": "Acme on LinkedIn", "link": "https://www.linkedin.com/company/acme", "snippet": ""},
        {"title": "Vanta trust", "link": "https://www.vanta.com/x", "snippet": ""},
        {"title": "Known | Rootly", "link": "https://rootly.com/security", "snippet": ""},
    ]}

    class S:
        def post(self, url, json=None, headers=None, timeout=None):
            return FakeResp(200, __import__("json").dumps(body), url)

    items, _ = find_leads("KEY", {"rootly.com"}, queries={"q": "x"}, session=S())
    assert [(c.domain, c.name) for c in items] == [("acme.io", "Acme")]


def test_one_site_serves_landing_dashboard_and_panel(client):
    panel, c = client
    home = c.get("/").get_data(as_text=True)
    assert "Signal Engine" in home and 'href="/dashboard"' in home and 'href="/app"' in home
    assert c.get("/dashboard").status_code == 200 and c.get("/favicon.svg").status_code == 200
    assert c.get("/assets/system.css").status_code == 200
    page = c.get("/app").get_data(as_text=True)
    assert 'class="sitebar"' in page and 'aria-current=page>Control panel' in page
