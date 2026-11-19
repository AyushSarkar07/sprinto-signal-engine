"""Step 4 — Point-of-contact discovery and role-relevance ranking.

Providers (configurable order via CONTACT_PROVIDERS):
  hunter  — Hunter.io Domain Search API (quota-limited, cached, retried with backoff)
  manual  — data/contacts_override.csv (e.g. contacts researched in Apollo's web UI)
  website — named leaders published on the company's own team/about pages (no email; source URL kept)
Nothing is ever invented: if no provider yields a relevant person, the company is flagged for review.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.models import Contact, ContactSelection, ExtractionResult, RankedContact, ScrapeRecord

log = logging.getLogger(__name__)

# role family → (title regex, base relevance, owns-the-problem explanation)
ROLE_FAMILIES: list[tuple[str, str, int, str]] = [
    ("CISO", r"\b(CISO|chief (information )?security officer)\b", 100, "owns security and compliance outright"),
    ("Head of Security", r"\b(head|vp|vice president|director)\b.{0,25}\b(security|infosec|trust)\b|\bsecurity (lead|manager)\b", 95,
     "runs the security programme day to day, including audits"),
    ("Head of Compliance / GRC", r"\b(head|vp|director|manager|lead)\b.{0,25}\b(compliance|GRC|governance|risk)\b|\bcompliance (officer|lead)\b", 92,
     "owns audit readiness and certification projects"),
    ("VP of Engineering", r"\b(vp|vice president|head|director|svp)\b.{0,15}\b(engineering|platform|infrastructure)\b", 78,
     "owns the engineering team that ends up collecting audit evidence"),
    ("CTO", r"\b(CTO|chief technology officer|co-?founder\s*(&|and|,)?\s*CTO)\b", 80,
     "accountable for technical controls and usually sponsors the first SOC 2"),
    ("DevOps / Infrastructure lead", r"\b(devops|sre|site reliability|infrastructure|cloud)\b.{0,15}\b(lead|manager|head|director)\b", 60,
     "implements many technical controls but rarely owns the buying decision"),
    ("CEO / Founder", r"\b(CEO|chief executive|founder)\b", 45, "final sponsor in small companies, but far from the evidence work"),
    ("COO / Operations", r"\b(COO|chief operating officer|head of operations)\b", 50, "sometimes owns compliance in early-stage firms"),
]
MIN_RELEVANCE = 55


def classify_role(title: str) -> tuple[str, int, str]:
    for family, rx, base, why in ROLE_FAMILIES:
        if re.search(rx, title or "", re.I):
            return family, base, why
    return "Other", 10, "role not connected to security or compliance"


def rank_contacts(contacts: list[Contact], domain: str, extraction: Optional[ExtractionResult]) -> list[RankedContact]:
    """Score each candidate on role relevance, problem ownership in THIS company, domain match and email quality."""
    has_security_function = False
    small_company = True
    if extraction:
        c = extraction.compliance_signals
        has_security_function = bool(c.compliance_hiring) or any(e.category == "certification_held" for e in c.soc2_mentions)
        stage = (extraction.company_profile.funding_stage.value or "").lower()
        small_company = not re.search(r"series [c-f]", stage)
    ranked = []
    for ct in contacts:
        family, score, why = classify_role(ct.job_title)
        reasons = [f"{family}: {why}."]
        if family in ("CISO", "Head of Security", "Head of Compliance / GRC") and has_security_function:
            score += 5
            reasons.append("Company shows a dedicated security/compliance function, so the specialist owns the problem.")
        if family == "CTO" and not has_security_function:
            score += 8
            reasons.append("No dedicated security leader observed — the CTO most likely carries compliance today.")
        if family == "CTO" and has_security_function:
            score -= 8
            reasons.append("A security function exists, so the CTO is one step removed from day-to-day compliance.")
        if family == "CEO / Founder" and small_company and not any(classify_role(o.job_title)[1] >= 78 for o in contacts):
            score += 10
            reasons.append("Small company with no technical leader listed — founder may own security decisions.")
        if ct.email:
            if not ct.email.lower().endswith("@" + domain) and not ct.email.lower().endswith("." + domain):
                score -= 60
                reasons.append(f"Email domain does not match {domain} — unreliable association.")
            if ct.verification_status in ("valid", "verified"):
                score += 4
                reasons.append("Email verified by provider.")
            elif ct.verification_status in ("invalid", "disposable"):
                score -= 30
                reasons.append("Provider marks the email invalid.")
            if ct.email_confidence is not None:
                score += (ct.email_confidence - 70) / 10
        else:
            score -= 5
            reasons.append("No email address available — reachable only after manual verification.")
        ranked.append(RankedContact(contact=ct, relevance_score=round(score, 1), role_family=family, reasons=reasons))
    ranked.sort(key=lambda r: r.relevance_score, reverse=True)
    return ranked


# ------------------------------------------------------------------ providers

class HunterProvider:
    name = "Hunter.io"
    URL = "https://api.hunter.io/v2/domain-search"

    def __init__(self, api_key: str, cache_dir: Path, max_calls: int = 10, session=None, timeout: float = 15):
        self.api_key, self.max_calls, self.timeout = api_key, max_calls, timeout
        self.cache_dir = cache_dir / "hunter"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.calls = 0
        self._last = 0.0

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20),
           retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout, RuntimeError)))
    def _get(self, params: dict) -> dict:
        wait = 1.0 - (time.monotonic() - self._last)  # Hunter allows ~15 req/s; stay far below
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        r = self.session.get(self.URL, params=params, timeout=self.timeout)
        if r.status_code == 429 or r.status_code >= 500:
            raise RuntimeError(f"Hunter transient HTTP {r.status_code}")
        if r.status_code in (401, 403):
            raise PermissionError("Hunter rejected the API key or plan does not allow this request")
        if r.status_code >= 400:
            raise ValueError(f"Hunter HTTP {r.status_code}")
        return r.json()

    def find(self, domain: str) -> tuple[list[Contact], str]:
        cache = self.cache_dir / (hashlib.sha1(domain.encode()).hexdigest()[:16] + ".json")
        if cache.exists():
            data = json.loads(cache.read_text())
        else:
            if self.calls >= self.max_calls:
                return [], f"Hunter quota for this run reached ({self.max_calls} calls)"
            self.calls += 1
            try:
                data = self._get({"domain": domain, "limit": 25, "type": "personal", "api_key": self.api_key})
            except PermissionError as exc:
                return [], str(exc)
            except Exception as exc:
                # Only the exception class: request errors can embed the URL, which carries the API key.
                return [], f"Hunter request failed: {exc.__class__.__name__}"
            cache.write_text(json.dumps(data))
        out = []
        for e in (data.get("data") or {}).get("emails", []) or []:
            if not e.get("first_name") or not e.get("position"):
                continue  # unnamed / role-less mailboxes cannot be personalised
            out.append(Contact(first_name=e["first_name"], last_name=e.get("last_name") or "",
                               full_name=f"{e['first_name']} {e.get('last_name') or ''}".strip(), job_title=e["position"],
                               email=e.get("value"), email_confidence=e.get("confidence"),
                               verification_status=(e.get("verification") or {}).get("status"),
                               department=e.get("department"), seniority=e.get("seniority"),
                               linkedin_url=e.get("linkedin"), source=self.name,
                               source_url=((e.get("sources") or [{}])[0] or {}).get("uri")))
        return out, f"Hunter returned {len(out)} named contact(s)"


class ManualProvider:
    name = "Manual mapping (Apollo / research)"

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path

    def find(self, domain: str, company: str = "") -> tuple[list[Contact], str]:
        if not self.csv_path.exists():
            return [], f"{self.csv_path.name} not found"
        out, incomplete = [], 0
        with self.csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(r for r in f if not r.lstrip().startswith("#")):
                d = (row.get("domain") or "").strip().lower().removeprefix("www.")
                if d != domain and (row.get("company") or "").strip().lower() != company.lower():
                    continue
                first, title = (row.get("first_name") or "").strip(), (row.get("job_title") or "").strip()
                if not first or not title:
                    incomplete += 1
                    continue
                last = (row.get("last_name") or "").strip()
                out.append(Contact(first_name=first, last_name=last, full_name=f"{first} {last}".strip(), job_title=title,
                                   email=(row.get("email") or "").strip() or None,
                                   verification_status=(row.get("verification_status") or "").strip() or None,
                                   linkedin_url=(row.get("linkedin_url") or "").strip() or None,
                                   source=(row.get("source") or "Manual mapping").strip(),
                                   source_url=(row.get("source_url") or "").strip() or None))
        note = f"Manual mapping returned {len(out)} contact(s)"
        if incomplete:
            note += f"; skipped {incomplete} incomplete row(s) (need first_name and job_title)"
        return out, note


NAME = r"([A-Z][a-zA-Z'’\-]+(?: [A-Z][a-zA-Z'’\-]+){1,2})"
TITLE_KW = r"((?:CISO|CTO|CEO|COO|Chief [A-Z][a-z]+ (?:[A-Z][a-z]+ )?Officer)(?:,? (?:and|&) Co-?founder)?|(?:Co-?founder|Founder)(?: ?(?:&|and|,) ?(?:CTO|CEO))?|(?:VP|Vice President|Head|Director) of [A-Z][A-Za-z ]{3,30})"


class WebsiteTeamProvider:
    """Names + titles that the company publishes itself (team / about / leadership pages). No emails are guessed."""

    name = "Company website (team page)"

    @staticmethod
    def _looks_like_testimonial(lines: list[str], i: int) -> bool:
        """Homepage/customer pages quote CUSTOMERS ("...great product." — Jane Doe, CTO). Never treat those as staff."""
        prev = " ".join(lines[max(0, i - 2):i])
        return bool(re.search(r"[\"“”]", prev))

    def find(self, rec: ScrapeRecord) -> tuple[list[Contact], str]:
        out: dict[str, Contact] = {}
        company = rec.company.lower()
        for p in rec.ok_pages():
            # Only the company's own about/team/leadership pages: homepages and case studies are full of customer quotes.
            if p.category != "about" or not re.search(r"about|team|leadership|company|people", p.url, re.I):
                continue
            lines = [l.strip() for l in p.text.splitlines() if l.strip()]
            for i, line in enumerate(lines):
                if self._looks_like_testimonial(lines, i):
                    continue
                at = re.search(r"\b(?:at|@)\s+([A-Z][\w.&\- ]+)$", line)
                if at and company not in at.group(1).lower():
                    continue  # title belongs to another company
                pairs = []
                m = re.fullmatch(NAME + r"\s*[,–\-|]\s*" + TITLE_KW, line)
                if m:
                    pairs.append((m.group(1), m.group(2)))
                elif re.fullmatch(NAME, line) and i + 1 < len(lines) and re.fullmatch(TITLE_KW + r"\.?", lines[i + 1]):
                    pairs.append((line, lines[i + 1].rstrip(".")))
                for name, title in pairs:
                    if any(w in name for w in ("Our", "The", "Team", "Meet", "About")):
                        continue
                    first, *rest = name.split()
                    out.setdefault(name, Contact(first_name=first, last_name=" ".join(rest), full_name=name, job_title=title,
                                                 source=self.name, source_url=p.url))
        return list(out.values()), f"Company website listed {len(out)} named leader(s)"


def discover_contact(rec: ScrapeRecord, extraction: Optional[ExtractionResult], settings,
                     hunter: Optional[HunterProvider] = None, manual: Optional[ManualProvider] = None) -> ContactSelection:
    sel = ContactSelection(status="needs_review")
    candidates: list[Contact] = []
    for prov in settings.contact_providers:
        if prov == "hunter":
            if hunter is None and settings.hunter_api_key:
                hunter = HunterProvider(settings.hunter_api_key, settings.cache_dir, settings.hunter_max_calls,
                                        timeout=settings.request_timeout)
            if hunter is None:
                sel.provider_notes.append("Hunter.io skipped: HUNTER_API_KEY not set.")
                continue
            found, note = hunter.find(rec.domain)
            sel.providers_tried.append(hunter.name)
        elif prov == "manual":
            manual = manual or ManualProvider(settings.contacts_csv)
            found, note = manual.find(rec.domain, rec.company)
            sel.providers_tried.append(manual.name)
        elif prov == "website":
            found, note = WebsiteTeamProvider().find(rec)
            sel.providers_tried.append(WebsiteTeamProvider.name)
        else:
            continue
        sel.provider_notes.append(note)
        candidates += found
        ranked = rank_contacts(candidates, rec.domain, extraction)
        if ranked and ranked[0].relevance_score >= MIN_RELEVANCE and ranked[0].contact.email:
            break  # good, reachable contact — no need to spend further provider calls

    ranked = rank_contacts(candidates, rec.domain, extraction)
    if not ranked or ranked[0].relevance_score < MIN_RELEVANCE:
        sel.selection_reasoning = ("No sufficiently relevant decision-maker found "
                                   f"({len(ranked)} candidate(s); best: {ranked[0].contact.job_title + ' ' + str(ranked[0].relevance_score) if ranked else 'none'}). "
                                   "Flagged for manual research — no contact was invented.")
        sel.alternative_contacts = ranked[:5]
        return sel
    best = ranked[0]
    sel.status, sel.contact, sel.role_family = "selected", best.contact, best.role_family
    alt = ranked[1:5]
    why = " ".join(best.reasons)
    if alt:
        why += " Preferred over " + "; ".join(f"{a.contact.full_name} ({a.contact.job_title}, score {a.relevance_score})" for a in alt[:3]) + "."
    if not best.contact.email:
        why += " Email not yet verified — the test preview will show the prospect address as unavailable."
    sel.selection_reasoning = f"{best.contact.full_name}, {best.contact.job_title} (relevance {best.relevance_score}): {why}"
    sel.alternative_contacts = alt
    return sel
