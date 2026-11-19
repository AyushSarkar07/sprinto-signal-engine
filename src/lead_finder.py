"""Find new candidate companies to research ("search for more leads").

Candidates come only from a real search API (Serper, Google results via a licensed API). Each query targets
a public trace of the ICP, such as a SaaS company's own SOC 2 / trust-centre page or a security job posting.
A candidate is just a domain plus the page that surfaced it: it is NOT qualified until the full pipeline has
researched it. Nothing is guessed; without a search key the finder returns nothing and says why.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

# Each query looks for a footprint of "SaaS + preparing for an audit". Edit freely.
QUERIES = {
    "working_towards_soc2": '"working towards SOC 2" SaaS',
    "soc2_in_progress": '"SOC 2 Type I" "Type II" "in progress" SaaS trust',
    "trust_centre": '"trust center" "SOC 2" B2B SaaS "Series A"',
    "security_hire": '"first security engineer" SaaS "Series A" SOC 2',
    "grc_hire": '"GRC" OR "compliance manager" job "SOC 2" startup "Series B"',
}

# Hosts that are never a prospect's own site (directories, media, job boards, vendors).
NOISE = re.compile(r"(linkedin|twitter|x\.com|facebook|youtube|medium|reddit|g2|capterra|crunchbase|wikipedia|github|"
                   r"techcrunch|forbes|news|blog\.|greenhouse|lever\.co|ashbyhq|workable|indeed|glassdoor|wellfound|ycombinator|"
                   r"vanta|drata|secureframe|sprinto|thoropass|aicpa|iso\.org|google|amazon|microsoft|safebase|trustarc)", re.I)


@dataclass
class Candidate:
    domain: str
    name: str
    found_on: str
    snippet: str
    query: str


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = re.sub(r"^(www|trust|security|app|docs|help|support)\.", "", host)
    return host


def _name(title: str, domain: str) -> str:
    base = domain.split(".")[0]
    for part in re.split(r"\s[|\-–—:·]\s", title):
        if base.replace("-", "") in part.lower().replace(" ", ""):
            return part.strip()[:60]
    return base.replace("-", " ").title()


def find_leads(api_key: str, exclude: set[str], queries: dict[str, str] | None = None, per_query: int = 10,
               session=None, timeout: float = 15) -> tuple[list[Candidate], list[str]]:
    """Return (candidates, notes). `exclude` = domains already in the prospect list."""
    if not api_key:
        return [], ["Lead search needs SERPER_API_KEY in .env (free tier at serper.dev). Nothing was searched."]
    session = session or requests
    seen, out, notes = set(exclude), [], []
    for key, q in (queries or QUERIES).items():
        try:
            r = session.post("https://google.serper.dev/search", json={"q": q, "num": per_query},
                             headers={"X-API-KEY": api_key}, timeout=timeout)
            if r.status_code != 200:
                notes.append(f"Query '{key}': HTTP {r.status_code}")
                continue
            results = r.json().get("organic", [])
        except Exception as exc:  # the header carries the key, so only the class name is reported
            notes.append(f"Query '{key}' failed ({exc.__class__.__name__})")
            continue
        for it in results:
            link = it.get("link", "")
            dom = _domain(link)
            if not dom or "." not in dom or NOISE.search(dom) or dom in seen:
                continue
            seen.add(dom)
            out.append(Candidate(domain=dom, name=_name(it.get("title", ""), dom), found_on=link,
                                 snippet=(it.get("snippet") or "")[:220], query=key))
    notes.append(f"{len(out)} new candidate domain(s) from {len(queries or QUERIES)} searches. Candidates are unverified until researched.")
    return out, notes
