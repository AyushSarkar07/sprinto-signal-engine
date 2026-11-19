"""The pipeline must never crash because one stage fails for one company; resume reuses completed work."""
import src.pipeline as pl
from src.pipeline import Pipeline
from src.scraper import Scraper
from tests.conftest import SAAS_HOME, SECURITY_PAGE, FakeSession


def test_one_failing_company_does_not_stop_others(settings, monkeypatch, conn_error):
    routes = {"https://acme.example": (200, SAAS_HOME), "https://acme.example/security": (200, SECURITY_PAGE),
              "https://boom.example": (200, SAAS_HOME)}
    routes.update({u: conn_error for u in ("https://down.example", "https://www.down.example", "http://down.example")})
    sc = Scraper(settings.cache_dir, timeout=1, delay=0, session=FakeSession(routes))
    real = pl.extract_signals

    def flaky(rec, llm, prompts):
        if rec.domain == "boom.example":
            raise RuntimeError("simulated extractor crash")
        return real(rec, llm, prompts)

    monkeypatch.setattr(pl, "extract_signals", flaky)
    p = Pipeline(settings, None, scraper=sc)
    runs, paths = p.run([("Acme", "acme.example"), ("Boom", "boom.example"), ("Down", "down.example")])
    assert len(runs) == 3
    assert "extract" in runs[1].errors and runs[0].qualification is not None
    assert runs[2].qualification.decision_status == "insufficient_data"
    assert paths["ledger"].exists() and (settings.output_dir / "company_reports" / "acme-example.md").exists()

    # resume: the crashed company is retried from the failed stage; completed stages are not redone
    monkeypatch.setattr(pl, "extract_signals", real)
    runs2, _ = Pipeline(settings, None, scraper=sc).run([("Boom", "boom.example")], resume=True)
    assert runs2[0].qualification is not None and not runs2[0].errors
