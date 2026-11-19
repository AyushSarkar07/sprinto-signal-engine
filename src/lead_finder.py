"""Find new candidate companies to research ("search for more leads").

Candidates come only from a real search API (Serper, Google results via a licensed API). Each query targets
a public trace of the ICP, such as a SaaS company's own SOC 2 / trust-centre page or a security job posting.
A candidate is just a domain plus the page that surfaced it: it is NOT qualified until the full pipeline has
researched it. Without a search key the finder returns nothing and says why.
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


# ---------------------------------------------------------------- funding-news shortlist

FUNDING_QUERIES = [
    "B2B SaaS raises Series A", "SaaS startup raises Series B", "software company secures Series A funding",
    "fintech SaaS raises Series B", "healthtech platform raises Series A", "AI SaaS raises Series C",
]
HEADLINE = re.compile(r"^(?:[\w\s,'&-]{0,40}?\b(?i:startup|firm|platform|company|fintech|healthtech|saas)\s+)?"
                      r"(?P<name>[A-Z][\w.&'-]*(?:\s[A-Z][\w.&'-]*){0,2}?)\s+"
                      r"(?i:raises|raised|secures|lands|bags|closes|announces|nabs|gets)\b(?P<rest>.*)$")
DESCRIPTORS = {"startup", "fintech", "healthtech", "firm", "platform", "company", "saas", "ai", "insurtech", "proptech", "edtech"}
STAGE = re.compile(r"\b(Seed|Series [A-F])\b", re.I)
SAAS_WORDS = re.compile(r"\b(SaaS|software|platform|API|cloud|AI|automation|infrastructure|B2B|enterprise)\b", re.I)
CONSUMER_WORDS = re.compile(r"\b(consumer|app for|restaurant|clinic|bank account for|wallet|lender|insurance provider|brand)\b", re.I)


@dataclass
class FundingLead:
    name: str
    stage: str
    headline: str
    url: str
    date: str
    rank: float
    domain: str = ""
    domain_note: str = ""


def parse_headline(title: str) -> tuple[str, str] | None:
    m = HEADLINE.search(title.strip())
    if not m:
        return None
    stage = STAGE.search(m.group("rest") or "")
    words = m.group("name").split()
    while len(words) > 1 and words[0].lower() in DESCRIPTORS:  # "Startup Rillet" → "Rillet"
        words = words[1:]
    return " ".join(words), (stage.group(1).title() if stage else "")


def rank_lead(stage: str, headline: str, age_days: int | None) -> float:
    """Shortlist score 0 to 1 from the headline alone: stage fit, SaaS words, freshness. Stage 2 (research) decides."""
    s = {"Series A": 0.45, "Series B": 0.45, "Series C": 0.35, "Seed": 0.15}.get(stage, 0.05)
    s += 0.2 if SAAS_WORDS.search(headline) else 0
    s -= 0.25 if CONSUMER_WORDS.search(headline) else 0
    if age_days is not None:
        s += 0.35 if age_days <= 90 else 0.2 if age_days <= 365 else 0
    return round(max(0.0, min(1.0, s)), 3)


def resolve_domain(name: str, fetch) -> tuple[str, str]:
    """Try name.com/.io/.ai/.co; accept only if the homepage title mentions the name. `fetch(url) -> (ok, title)`."""
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    tried = []
    for tld in ("com", "io", "ai", "co", "app"):
        dom = f"{base}.{tld}"
        tried.append(dom)
        ok, title = fetch(f"https://{dom}")
        if ok and base[:5] in re.sub(r"[^a-z0-9]", "", (title or "").lower()):
            return dom, f"matched homepage title on {dom}"
    return "", f"domain unresolved (tried {', '.join(tried)})"


def funding_leads(api_key: str, exclude_names: set[str], fetch=None, session=None, timeout: float = 15,
                  per_query: int = 10) -> tuple[list[FundingLead], list[str]]:
    """Recently funded companies from news headlines (Serper news API), ranked, with domains resolved when possible."""
    if not api_key:
        return [], ["Funding-news search needs SERPER_API_KEY in .env (free tier at serper.dev). Nothing was searched."]
    session = session or requests
    import datetime as _dt
    seen, out, notes = {n.lower() for n in exclude_names}, [], []
    for q in FUNDING_QUERIES:
        try:
            r = session.post("https://google.serper.dev/news", json={"q": q, "num": per_query, "tbs": "qdr:y"},
                             headers={"X-API-KEY": api_key}, timeout=timeout)
            items = r.json().get("news", []) if r.status_code == 200 else []
            if r.status_code != 200:
                notes.append(f"News query HTTP {r.status_code}")
        except Exception as exc:
            notes.append(f"News query failed ({exc.__class__.__name__})")
            continue
        for it in items:
            parsed = parse_headline(it.get("title", ""))
            if not parsed or parsed[0].lower() in seen:
                continue
            name, stage = parsed
            seen.add(name.lower())
            age = None
            date = it.get("date", "")
            m = re.match(r"(\d+)\s+(day|week|month|hour)s?\s+ago", date)
            if m:
                age = int(m.group(1)) * {"hour": 0, "day": 1, "week": 7, "month": 30}[m.group(2)]
            out.append(FundingLead(name=name, stage=stage, headline=it.get("title", "")[:200], url=it.get("link", ""),
                                   date=date, rank=rank_lead(stage, it.get("title", ""), age)))
    out.sort(key=lambda l: l.rank, reverse=True)
    if fetch:
        for l in out[:20]:
            l.domain, l.domain_note = resolve_domain(l.name, fetch)
    notes.append(f"{len(out)} funded companies found in news; ranked by stage, SaaS words and freshness. Unverified until researched.")
    return out, notes
