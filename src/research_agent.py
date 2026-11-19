"""Step 3b — The research agent: targeted secondary investigation before a decision is final.

Loop (max `max_rounds`, default 2):
  1. Look at what is missing (from extraction) and whether timing evidence is weak.
  2. Decide which page types could answer each gap (careers → hiring, trust/security → certifications, ...).
  3. Fetch only unseen pages within a page budget (discovered links first, then common paths,
     then public job-board APIs, then an optional search provider).
  4. Re-extract, re-score, and record what changed and why.
Stops early when the decision is already well supported or there is nothing new to read.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from src.llm import ClaudeJSON
from src.models import ExtractionResult, Qualification, ResearchRound, ScrapeRecord
from src.qualification_engine import THRESHOLDS, qualify
from src.scraper import Scraper, canonical_url, fetch_ats_jobs, finalise, priority_targets, same_site
from src.signal_extractor import extract_signals

log = logging.getLogger(__name__)

GAP_TO_PAGES: dict[str, list[str]] = {
    "saas_model": ["pricing", "product", "about"],
    "growth_stage": ["about", "news", "careers"],
    "enterprise_customers": ["customers", "enterprise", "pricing"],
    "compliance_status": ["security", "trust", "compliance", "legal"],
    "security_hiring": ["careers"],
    "security_page": ["security", "trust", "legal"],
    "weak_timing": ["careers", "trust", "security", "customers", "news"],
}
GAP_QUESTION = {
    "saas_model": "Is this a subscription software business?",
    "growth_stage": "What stage / size is the company?",
    "enterprise_customers": "Does it sell to enterprises?",
    "compliance_status": "What is its SOC 2 / ISO 27001 / GDPR status?",
    "security_hiring": "Is it hiring for security, compliance or engineering?",
    "security_page": "Does it publish security controls or a trust centre?",
    "weak_timing": "Is there any evidence compliance matters right now?",
}


class SearchProvider:
    """Pluggable external discovery. The core pipeline never requires one."""

    name = "none"

    def search(self, query: str, num: int = 5) -> list[str]:
        return []


class SerperSearch(SearchProvider):
    name = "serper"

    def __init__(self, api_key: str, timeout: float = 15):
        self.api_key, self.timeout = api_key, timeout

    def search(self, query: str, num: int = 5) -> list[str]:
        try:
            r = requests.post("https://google.serper.dev/search", json={"q": query, "num": num},
                              headers={"X-API-KEY": self.api_key}, timeout=self.timeout)
            r.raise_for_status()
            return [o.get("link") for o in r.json().get("organic", []) if o.get("link")]
        except Exception as exc:
            log.warning("Search provider failed: %s", exc.__class__.__name__)
            return []


def make_search_provider(settings) -> SearchProvider:
    if settings.search_provider == "serper" and settings.serper_api_key:
        return SerperSearch(settings.serper_api_key, settings.request_timeout)
    return SearchProvider()


def gaps_for(r: ExtractionResult, q: Qualification) -> list[str]:
    gaps = [m.split(":")[0] for m in r.missing_information if ":" in m]
    if q.buying_timing_score < THRESHOLDS["timing_qualify"]:
        gaps.append("weak_timing")
    return list(dict.fromkeys(gaps))


def sufficient(q: Qualification) -> tuple[bool, str]:
    if q.decision_status == "qualified" and q.evidence_confidence >= 0.7:
        return True, "Decision already well supported."
    if q.recommended_action == "disqualify" and q.evidence_confidence >= 0.4:
        return True, "Clear disqualification — further research would not change the outcome."
    return False, ""


def investigate(rec: ScrapeRecord, extraction: ExtractionResult, q: Qualification, scraper: Scraper,
                llm: Optional[ClaudeJSON], prompts_dir, max_rounds: int = 2, page_budget: int = 4,
                search: Optional[SearchProvider] = None) -> tuple[ScrapeRecord, ExtractionResult, Qualification, list[ResearchRound], list[str]]:
    rounds: list[ResearchRound] = []
    notes: list[str] = []
    search = search or SearchProvider()
    if rec.scraping_status == "failed":
        notes.append("Secondary research skipped: homepage unreachable, nothing to follow.")
        return rec, extraction, q, rounds, notes

    for n in range(1, max_rounds + 1):
        done, why = sufficient(q)
        if done:
            notes.append(f"Stopped before round {n}: {why}")
            break
        gaps = gaps_for(extraction, q)
        if not gaps:
            notes.append(f"Stopped before round {n}: no open questions.")
            break
        cats = list(dict.fromkeys(c for g in gaps for c in GAP_TO_PAGES.get(g, [])))
        targets = priority_targets(rec, cats, page_budget)
        seen = {canonical_url(u) for u in rec.page_urls()}
        extra_sources: list[str] = []
        if any(g in gaps for g in ("security_hiring", "weak_timing", "growth_stage")):
            extra_sources += [u for u in rec.discovered_links.get("ats", []) if u not in seen][:1]
        external_trust = [u for u in rec.discovered_links.get("trust", []) if not same_site(u, rec.domain) and u not in seen]
        if external_trust and any(g in gaps for g in ("compliance_status", "security_page", "weak_timing")):
            targets = targets[: max(0, page_budget - 1)] + [(external_trust[0], "trust")]
        if search.name != "none" and len(targets) < page_budget:
            for url in search.search(f"{rec.company} SOC 2 OR ISO 27001 OR security", num=5):
                cu = canonical_url(url)
                if same_site(url, rec.domain) and cu not in seen and all(cu != t for t, _ in targets):
                    targets.append((cu, "security"))
                    break
        if not targets and not extra_sources:
            notes.append(f"Stopped before round {n}: no unvisited pages could answer {', '.join(gaps)}.")
            break

        before = q
        read_ok, targeted = [], []
        for url, cat in targets:
            targeted.append(f"{url} [{cat}] — {', '.join(GAP_QUESTION[g] for g in gaps if cat in GAP_TO_PAGES.get(g, []))[:160]}")
            page, _ = scraper.scrape_page(url, cat, discovered_from="research_agent")
            rec.pages_scraped.append(page)
            if page.status == "ok":
                read_ok.append(url)
                if cat == "careers":  # a careers page often links to the real ATS board
                    res = scraper.fetch(url)
                    if res.get("body"):
                        more = Scraper.discover_links(res["body"], url, rec.domain)
                        for u in more.get("ats", []):
                            if u not in rec.discovered_links.setdefault("ats", []):
                                rec.discovered_links["ats"].append(u)
                                if u not in extra_sources:
                                    extra_sources.append(u)
        for ats in extra_sources[:1]:
            targeted.append(f"{ats} [job board API] — Is it hiring for security, compliance or engineering?")
            page = fetch_ats_jobs(scraper, ats)
            if page:
                rec.pages_scraped.append(page)
                if page.status == "ok":
                    read_ok.append(page.url)
        rec = finalise(rec)
        old_ids = {e.id for e in extraction.all_evidence()}
        extraction, ex_notes = extract_signals(rec, llm, prompts_dir)
        q = qualify(extraction, rec, research_rounds=n)
        new = [f"{e.finding} ({e.source_url})" for e in extraction.all_evidence() if e.id not in old_ids]
        changed = (f"ICP {before.icp_fit_score}→{q.icp_fit_score}, timing {before.buying_timing_score}→{q.buying_timing_score}, "
                   f"decision {before.decision_status}→{q.decision_status}.")
        changed += f" {len(new)} new evidence item(s)." if new else " No new evidence found on these pages."
        rounds.append(ResearchRound(round=n, missing_before=[GAP_QUESTION[g] for g in gaps], pages_targeted=targeted,
                                    pages_successfully_read=read_ok, new_findings=new[:15], icp_before=before.icp_fit_score,
                                    icp_after=q.icp_fit_score, timing_before=before.buying_timing_score,
                                    timing_after=q.buying_timing_score, decision_before=before.decision_status,
                                    decision_after=q.decision_status, what_changed=changed))
        if not read_ok:
            notes.append(f"Round {n}: none of the targeted pages were readable.")
    q.research_rounds = len(rounds)
    q.secondary_research_performed = bool(rounds)
    return rec, extraction, q, rounds, notes
