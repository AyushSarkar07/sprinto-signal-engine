"""External evidence for questions a company website rarely answers (funding round, headcount, cloud stack).

Both sources become ordinary PageRecords, so their text goes through the same extractor and grounding
check as website pages, and every fact keeps a citable source:

  * News via the Serper news API (Google News results through a licensed API). The Google News RSS feed
    itself is NOT used: news.google.com/robots.txt disallows /rss and its terms restrict it to personal
    feed readers, and this project does not bypass access restrictions.
  * Company enrichment (e.g. Apollo.io) from data/company_enrichment.csv: one row per field, each with its
    source and retrieval date. Rows are filled from a real lookup (never typed in from memory); website
    evidence always takes precedence because the extractor reads site pages first.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

import requests

from src.models import PageRecord, ScrapeRecord

log = logging.getLogger(__name__)
ENRICHMENT_FIELDS = {"employee_count", "funding_stage", "technologies", "industry"}
COMMON_WORD_NAMES = {"plain", "linear", "notion", "front", "census", "rippling", "attention", "loom", "pilot", "ramp", "brex"}
FUNDING_WORDS = re.compile(r"\b(raises?|raised|funding|series [a-f]|seed round|investment|valuation)\b", re.I)


def news_pages(company: str, domain: str, api_key: str, session=None, timeout: float = 15, num: int = 10) -> list[PageRecord]:
    """Funding headlines that name the company exactly. Ambiguous names (e.g. 'Plain') are only kept when the
    headline or snippet also mentions the domain or a funding phrase right after the name."""
    if not api_key:
        return []
    session = session or requests
    try:
        r = session.post("https://google.serper.dev/news", json={"q": f'"{company}" funding OR raises OR "Series"', "num": num},
                         headers={"X-API-KEY": api_key}, timeout=timeout)
        if r.status_code != 200:
            log.warning("News API HTTP %s", r.status_code)
            return []
        items = r.json().get("news", [])
    except Exception as exc:  # never echo request details (header carries the key)
        log.warning("News API failed: %s", exc.__class__.__name__)
        return []
    name = re.compile(rf"(?<![\w-]){re.escape(company)}(?![\w-])")
    tight = re.compile(rf"{re.escape(company)}\W{{0,3}}(raises|raised|secures|closes|lands|announces)", re.I)
    pages = []
    for it in items:
        title, snippet, link = it.get("title", ""), it.get("snippet", ""), it.get("link", "")
        text = f"{title}. {snippet}".strip()
        if not (link and name.search(title) and FUNDING_WORDS.search(text)):
            continue
        if company.lower() in COMMON_WORD_NAMES and not (domain in text.lower() or tight.search(text)):
            continue  # "Plain" or "Front" in a headline is usually the English word, not the company
        date = it.get("date", "")
        pages.append(PageRecord(url=link, category="news", title=title[:200],
                                text=f"{text} ({it.get('source', 'news')}{', ' + date if date else ''})",
                                discovered_from="news search (Serper)"))
    return pages[:3]


def read_enrichment(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    out: dict[str, list[dict]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(r for r in f if r.strip() and not r.lstrip().startswith("#")):
            dom, field, value = (row.get("domain") or "").strip().lower(), (row.get("field") or "").strip(), (row.get("value") or "").strip()
            if dom and field in ENRICHMENT_FIELDS and value and (row.get("source") or "").strip():
                out.setdefault(dom, []).append(row)
    return out


def enrichment_page(domain: str, rows: list[dict]) -> PageRecord | None:
    """Render enrichment rows as one plainly labelled record the extractor can read and cite."""
    if not rows:
        return None
    source = rows[0]["source"].strip()
    parts = []
    for row in rows:
        v = row["value"].strip()
        if row["field"] == "employee_count":
            parts.append(f"Headcount: {v} employees.")
        elif row["field"] == "funding_stage":
            m = re.match(r"(.+?)\s*\((.+)\)$", v)  # "Series A (2023-08)" → keep the date so staleness is visible
            parts.append(f"Latest funding: {m.group(1)} round ({m.group(2)})." if m else f"Latest funding: {v} round.")
        elif row["field"] == "technologies":
            parts.append(f"Technologies detected: {v}.")
        elif row["field"] == "industry":
            parts.append(f"Industry: {v}.")
    retrieved = rows[0].get("retrieved", "").strip()
    url = rows[0].get("source_url", "").strip() or f"enrichment://{source.lower().replace(' ', '-')}/{domain}"
    return PageRecord(url=url, category="enrichment", title=f"{source} company record for {domain}",
                      text=f"{source} company record for {domain}{' (retrieved ' + retrieved + ')' if retrieved else ''}. " + " ".join(parts),
                      discovered_from=source)


def add_external_pages(rec: ScrapeRecord, company: str, settings, session=None) -> list[str]:
    """Append news + enrichment pages to a scrape record; returns human-readable notes."""
    notes = []
    if rec.scraping_status == "failed":
        return notes
    have = rec.page_urls()
    enr = enrichment_page(rec.domain, read_enrichment(settings.enrichment_csv).get(rec.domain.lower(), []))
    if enr and enr.url not in have:
        rec.pages_scraped.append(enr)
        notes.append(f"Added {enr.title}.")
    if settings.search_provider == "serper" and settings.serper_api_key:
        news = [p for p in news_pages(company, rec.domain, settings.serper_api_key, session, settings.request_timeout)
                if p.url not in have]
        rec.pages_scraped += news
        notes.append(f"News search: {len(news)} funding headline(s) naming {company}.")
    else:
        notes.append("News search not configured (SERPER_API_KEY); Google News RSS is robots-disallowed, so not scraped.")
    rec.raw_text = "\n\n".join(p.text for p in rec.ok_pages())
    return notes
