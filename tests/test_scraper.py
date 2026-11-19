from src.qualification_engine import qualify
from src.research_agent import investigate
from src.scraper import Scraper, classify_url, clean_html, scrape_company
from src.signal_extractor import extract_signals
from tests.conftest import SAAS_HOME, SECURITY_PAGE, FakeSession, page


def make(settings, routes):
    sess = FakeSession(routes)
    return Scraper(settings.cache_dir, timeout=1, delay=0, session=sess), sess


def test_unreachable_website_does_not_crash(settings, conn_error):
    """Scenario 1: website cannot be reached."""
    sc, _ = make(settings, {u: conn_error for u in ("https://down.example", "https://www.down.example", "http://down.example")})
    rec = scrape_company(sc, "Down Co", "down.example")
    assert rec.scraping_status == "failed"
    assert any("Could not connect" in e for e in rec.errors)
    ex, _ = extract_signals(rec, None, settings.prompts_dir)
    q = qualify(ex, rec)
    assert q.decision_status == "insufficient_data" and q.qualified is False
    assert q.recommended_action == "manual_review"  # cannot-evaluate ≠ unqualified


def test_very_little_information_is_insufficient_not_rejected(settings):
    """Scenario 2: website contains very little information."""
    sc, _ = make(settings, {"https://tiny.example": (200, page("<p>Coming soon.</p>", "Tiny"))})
    rec = scrape_company(sc, "Tiny", "tiny.example")
    ex, _ = extract_signals(rec, None, settings.prompts_dir)
    q = qualify(ex, rec)
    assert q.decision_status == "insufficient_data"
    assert not q.qualified


def test_security_page_found_by_research_agent(settings):
    """Scenario 3: homepage has no compliance info, but a security page exists — the agent must find it."""
    routes = {"https://acme.example": (200, SAAS_HOME), "https://acme.example/security": (200, SECURITY_PAGE)}
    sc, sess = make(settings, routes)
    rec = scrape_company(sc, "Acme", "acme.example", page_budget=0)  # homepage only, to force secondary research
    ex, _ = extract_signals(rec, None, settings.prompts_dir)
    assert not ex.compliance_signals.soc2_mentions
    q0 = qualify(ex, rec)
    rec, ex, q, rounds, _ = investigate(rec, ex, q0, sc, None, settings.prompts_dir, max_rounds=2, page_budget=3)
    assert rounds and q.secondary_research_performed
    assert any("/security" in t for t in rounds[0].pages_targeted)
    assert any(e.category == "certification_in_progress" for e in ex.compliance_signals.soc2_mentions)
    assert q.buying_timing_score > q0.buying_timing_score
    assert "timing" in rounds[0].what_changed
    assert len(rounds) <= 2
    assert sess.calls.count("https://acme.example/security") == 1  # never scraped twice


def test_robots_txt_is_respected(settings):
    routes = {"https://acme.example/robots.txt": (200, "User-agent: *\nDisallow: /", "text/plain"),
              "https://acme.example": (200, SAAS_HOME)}
    sc, sess = make(settings, routes)
    res = sc.fetch("https://acme.example")
    assert res["status"] == "blocked_by_robots"
    assert "https://acme.example/" not in sess.calls and "https://acme.example" not in sess.calls


def test_cleaning_removes_scripts_nav_and_cookie_banners():
    title, text = clean_html(SAAS_HOME)
    assert "cookies" not in text.lower() and "var x" not in text and "Menu Home" not in text
    assert "workflow automation platform" in text
    assert title.startswith("Acme")


def test_link_discovery_does_not_need_exact_paths():
    assert classify_url("https://x.com/company/trust-and-safety") == "trust"
    assert classify_url("https://x.com/en/customer-stories") == "customers"
    assert classify_url("https://x.com/work-with-us") == "careers"
    assert classify_url("https://x.com/blog/post-1") == "news"
    links = Scraper.discover_links("<a href='https://boards.greenhouse.io/acme'>Jobs</a><a href='https://trust.acme.example'>Trust</a>"
                                   "<a href='https://other.com/security'>x</a>", "https://acme.example", "acme.example")
    assert links.get("ats") and links.get("trust") and "security" not in links


def test_cache_prevents_refetch(settings):
    sc, sess = make(settings, {"https://acme.example": (200, SAAS_HOME)})
    sc.fetch("https://acme.example")
    sc2 = Scraper(settings.cache_dir, timeout=1, delay=0, session=sess)
    n = len(sess.calls)
    sc2.fetch("https://acme.example")
    assert len(sess.calls) == n  # served from the disk cache by a fresh scraper (as on --resume)
