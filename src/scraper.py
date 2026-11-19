"""Step 1 — Website intelligence.

Polite, cached scraping with requests + BeautifulSoup (Playwright only as an opt-in fallback
for JavaScript-rendered pages). Respects robots.txt, applies per-host delays and timeouts,
never retries a URL already fetched, and never lets one bad website crash the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

from src.models import PageRecord, ScrapeRecord

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; SprintoSignalEngine/1.0; academic prospect research)"

# Page categories the system cares about, with the URL/anchor keywords that identify them.
PAGE_CATEGORIES: dict[str, list[str]] = {
    "security": ["security", "secure", "infosec", "data-protection", "responsible-disclosure"],
    "trust": ["trust", "trust-center", "trust-centre", "trustcenter"],
    "compliance": ["compliance", "soc-2", "soc2", "iso-27001", "iso27001", "gdpr", "hipaa", "certification"],
    "customers": ["customers", "customer-stories", "case-studies", "case-study", "success-stories", "testimonials"],
    "careers": ["careers", "jobs", "join-us", "work-with-us", "hiring", "open-positions", "join"],
    "enterprise": ["enterprise"],
    "about": ["about", "company", "team", "our-story", "who-we-are", "leadership"],
    "news": ["news", "press", "blog", "announcements", "newsroom", "funding"],
    "pricing": ["pricing", "plans"],
    "legal": ["legal", "privacy", "terms", "dpa", "subprocessors"],
    "product": ["product", "platform", "features", "solutions", "integrations"],
}
# Guessed paths used only when a category was not discovered from links.
FALLBACK_PATHS: dict[str, list[str]] = {
    "about": ["/about", "/company"], "customers": ["/customers", "/case-studies"],
    "security": ["/security"], "trust": ["/trust"], "compliance": ["/compliance"],
    "careers": ["/careers", "/jobs"], "enterprise": ["/enterprise"], "legal": ["/legal"],
    "pricing": ["/pricing"],
}
# External hosts that are legitimate extensions of a company site.
ATS_PATTERNS = {
    "greenhouse": re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
}
TRUST_HOST_HINTS = ("trust.", "security.", "trust.page", "safebase.io", "vanta.com", "drata.com",
                    "secureframe.com", "conveyor.com", "whistic.com", "sprinto.com")
JUNK_SELECTORS = ["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "form", "button"]
BANNER_RE = re.compile(r"cookie|consent|gdpr-banner|onetrust|cc-banner|truste|osano|newsletter|modal|popup", re.I)
SKIP_EXT = re.compile(r"\.(pdf|png|jpe?g|gif|svg|webp|zip|mp4|mov|css|js|xml|ico)(\?|$)", re.I)


def normalise_domain(domain: str) -> str:
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    return d.split("/")[0].removeprefix("www.")


def canonical_url(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/+$", "", p.path) or "/"
    return urlunparse((p.scheme or "https", p.netloc.lower(), path, "", "", ""))


def same_site(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host == domain or host.endswith("." + domain)


def classify_url(url: str, anchor: str = "") -> Optional[str]:
    """Return the page category for a link, based on path and anchor text (not exact paths)."""
    path = urlparse(url).path.lower()
    host = urlparse(url).netloc.lower()
    text = anchor.lower().strip()
    if any(h in host for h in ("trust.", "trust.page", "safebase.io")) or "/trust" in path:
        return "trust"
    segments = [s for s in re.split(r"[/_]", path) if s]
    for cat, kws in PAGE_CATEGORIES.items():
        for kw in kws:
            if any(seg == kw or seg.startswith(kw + "-") or seg.endswith("-" + kw) for seg in segments):
                return cat
            if text and (text == kw.replace("-", " ") or text.startswith(kw.replace("-", " "))):
                return cat
    if host.startswith("careers.") or host.startswith("jobs."):
        return "careers"
    return None


# Platforms that host trust centres. Matched only on specific signatures (loader names, "Powered by" lines,
# platform hosts), never on a bare vendor name: a SafeBase page, for example, lists Drata hosts in its own
# configuration, and that must not be read as the company's choice.
TRUST_PLATFORM_SIGNATURES = [
    ("Vanta", r"vanta-entry-loader|powered by vanta|trust\.vanta\.com"),
    ("Drata", r"powered by drata|trust\.drata\.com|drata-trust-center"),
    ("Secureframe", r"powered by secureframe|trust\.secureframe\.com"),
    ("Sprinto", r"powered by sprinto|trust\.sprinto\.com|sprinto-trust"),
    ("Thoropass", r"powered by thoropass"), ("Scrut", r"powered by scrut"), ("Oneleet", r"powered by oneleet|trust\.oneleet\.com"),
    ("Delve", r"powered by delve"), ("TrustCloud", r"powered by trustcloud|trustcloud\.ai/trust"),
    ("SafeBase", r"powered by safebase|app\.safebase\.io|cdn\.safebase\.io"),
    ("Conveyor", r"powered by conveyor|conveyor\.com/trust"), ("Whistic", r"powered by whistic|whistic\.com/profile"),
]


def detect_trust_platform(html: str, title: str = "", url: str = "") -> Optional[tuple[str, str]]:
    """Name the platform a trust/security page runs on, with the exact signature found. Only trust-like pages."""
    host = urlparse(url).netloc.lower()
    trustlike = re.search(r"trust|security", host + " " + (title or ""), re.I) or "/trust" in url.lower()
    if not trustlike:
        return None
    for name, pat in TRUST_PLATFORM_SIGNATURES:
        m = re.search(pat, html[:400_000], re.I)
        if m:
            return name, m.group(0)[:60]
    return None


def clean_html(html: str) -> tuple[str, str]:
    """Strip scripts, navigation, cookie banners and repeated lines; return (title, text)."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")[:200]
    for sel in JUNK_SELECTORS:
        for tag in soup.find_all(sel):
            tag.decompose()
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        ident = " ".join([tag.get("id") or "", " ".join(tag.get("class") or []), tag.get("aria-label") or ""])
        if ident.strip() and BANNER_RE.search(ident):
            tag.decompose()
    # Meta description is often the clearest one-line business description.
    lines: list[str] = []
    seen: set[str] = set()
    for raw in soup.get_text("\n").splitlines():
        line = " ".join(raw.split())
        if len(line) < 3 or line.lower() in seen:
            continue
        seen.add(line.lower())
        lines.append(line)
    return title, "\n".join(lines)


def meta_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return " ".join(tag["content"].split())
    return ""


class Scraper:
    """Polite HTTP fetcher with robots.txt, disk cache, per-host delay and a URL de-dup set."""

    def __init__(self, cache_dir: Path, timeout: float = 15.0, delay: float = 1.0,
                 use_playwright: bool = False, session: Any = None):
        self.cache_dir = cache_dir / "pages"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.delay = delay
        self.use_playwright = use_playwright
        self.session = session or requests.Session()
        if hasattr(self.session, "headers"):
            self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                                         "Accept-Language": "en"})
        self._robots: dict[str, Optional[robotparser.RobotFileParser]] = {}
        self._last_hit: dict[str, float] = {}
        self._fetched: dict[str, dict] = {}

    # ---------- low level ----------
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def _throttle(self, host: str) -> None:
        wait = self.delay - (time.monotonic() - self._last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                self._throttle(p.netloc)
                r = self.session.get(base + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
                else:
                    self._robots[base] = None  # no robots.txt => allowed
            except Exception as exc:  # network errors: treat as no robots, fetch will fail anyway
                log.debug("robots.txt fetch failed for %s: %s", base, exc)
                self._robots[base] = None
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def fetch(self, url: str, want_json: bool = False) -> dict:
        """Fetch one URL once. Returns {url, status, http_status, body, final_url, error}."""
        url = url if want_json else canonical_url(url)
        if url in self._fetched:
            return self._fetched[url]
        cp = self._cache_path(url)
        if cp.exists():
            res = json.loads(cp.read_text())
            self._fetched[url] = res
            return res
        res: dict = {"url": url, "status": "error", "http_status": None, "body": "", "final_url": url, "error": ""}
        if not self.allowed(url):
            res.update(status="blocked_by_robots", error="Disallowed by robots.txt")
        else:
            try:
                self._throttle(urlparse(url).netloc)
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                res["http_status"] = r.status_code
                res["final_url"] = getattr(r, "url", url) or url
                ctype = (getattr(r, "headers", {}) or {}).get("Content-Type", "text/html")
                if r.status_code == 404:
                    res.update(status="not_found", error="HTTP 404")
                elif r.status_code in (401, 403, 429):
                    res.update(status="access_restricted", error=f"HTTP {r.status_code} (not bypassed)")
                elif r.status_code >= 400:
                    res.update(status="error", error=f"HTTP {r.status_code}")
                elif not want_json and "html" not in ctype and "text" not in ctype:
                    res.update(status="error", error=f"Unsupported content type {ctype}")
                else:
                    # requests defaults to ISO-8859-1 when no charset is declared, which garbles UTF-8 pages.
                    if hasattr(r, "encoding") and (r.encoding is None or r.encoding.lower() == "iso-8859-1") \
                            and "charset" not in ctype.lower():
                        r.encoding = "utf-8"
                    res.update(status="ok", body=r.text[:1_500_000])
            except requests.exceptions.Timeout:
                res.update(error="Timed out")
            except requests.exceptions.SSLError as exc:
                res.update(error=f"SSL error: {exc.__class__.__name__}")
            except requests.exceptions.ConnectionError:
                res.update(error="Could not connect (DNS failure or host unreachable)")
            except Exception as exc:
                res.update(error=f"{exc.__class__.__name__}: {exc}")
        self._fetched[url] = res
        if res["status"] in ("ok", "not_found", "blocked_by_robots"):
            cp.write_text(json.dumps(res))
        return res

    def _render_with_playwright(self, url: str) -> Optional[str]:
        if not self.use_playwright:
            return None
        try:
            from playwright.sync_api import sync_playwright  # optional dependency
        except ImportError:
            log.info("Playwright not installed; skipping JS render for %s", url)
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, timeout=int(self.timeout * 1000), wait_until="networkidle")
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            log.warning("Playwright render failed for %s: %s", url, exc)
            return None

    # ---------- page level ----------
    def scrape_page(self, url: str, category: str = "other", discovered_from: str = "") -> tuple[PageRecord, str]:
        rec, html = self._scrape_page(url, category, discovered_from)
        if html and rec.status in ("ok", "empty"):
            found = detect_trust_platform(html, rec.title, rec.url)
            if found:
                name, sig = found
                # Many trust centres are drawn by JavaScript, so the platform never appears in visible text.
                # Record it as a plainly labelled line taken from the page source, so it can be cited and checked.
                rec.text = f"Trust centre platform: {name} (found '{sig}' in the page source)\n{rec.text}"
                rec.status = "ok"
        return rec, html

    def _scrape_page(self, url: str, category: str = "other", discovered_from: str = "") -> tuple[PageRecord, str]:
        """Fetch and clean one page. Returns (PageRecord, raw_html)."""
        res = self.fetch(url)
        if res["status"] != "ok":
            return PageRecord(url=res["url"], category=category, status=res["status"], http_status=res["http_status"],
                              discovered_from=discovered_from, text="", title=res.get("error", "")), ""
        html = res["body"]
        title, text = clean_html(html)
        desc = meta_description(html)
        rendered = "requests"
        if len(text) < 300:
            js_html = self._render_with_playwright(res["url"])
            if js_html:
                html, rendered = js_html, "playwright"
                title, text = clean_html(js_html)
        if desc and desc.lower() not in text.lower():
            text = f"{desc}\n{text}"
        status = "ok" if text.strip() else "empty"
        return PageRecord(url=res["url"], category=category, title=title, text=text[:60_000], status=status,
                          http_status=res["http_status"], rendered_with=rendered, discovered_from=discovered_from), html

    @staticmethod
    def discover_links(html: str, base_url: str, domain: str) -> dict[str, list[str]]:
        """Categorise internal links (and known external ATS / trust-centre hosts)."""
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, list[str]] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            url = urljoin(base_url, href)
            if SKIP_EXT.search(url):
                continue
            host = urlparse(url).netloc.lower()
            anchor = a.get_text(" ", strip=True)[:60]
            if any(pat.search(url) for pat in ATS_PATTERNS.values()):
                found.setdefault("ats", []).append(url)
                continue
            external_trust = (not same_site(url, domain)) and any(h in host for h in TRUST_HOST_HINTS[2:])
            if not same_site(url, domain) and not external_trust:
                continue
            cat = "trust" if external_trust else classify_url(url, anchor)
            if not cat:
                continue
            cu = canonical_url(url)
            if cu not in found.setdefault(cat, []):
                found[cat].append(cu)
        for cat in found:  # prefer short, top-level URLs (e.g. /security over /blog/security-post-17)
            found[cat].sort(key=lambda u: (urlparse(u).path.count("/"), len(u)))
            found[cat] = found[cat][:8]
        return found

    def scrape_homepage(self, company: str, domain: str) -> tuple[ScrapeRecord, str]:
        domain = normalise_domain(domain)
        rec = ScrapeRecord(company=company, domain=domain)
        html = ""
        for candidate in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            page, html = self.scrape_page(candidate, "homepage")
            if page.status == "ok":
                rec.homepage_url = page.url
                rec.pages_scraped.append(page)
                break
            rec.errors.append(f"{candidate}: {page.status} {page.title}".strip())
        if not rec.homepage_url:
            rec.scraping_status = "failed"
            return rec, ""
        rec.discovered_links = self.discover_links(html, rec.homepage_url, domain)
        return rec, html


def priority_targets(rec: ScrapeRecord, categories: list[str], budget: int) -> list[tuple[str, str]]:
    """Pick up to `budget` unscraped (url, category) pairs: discovered links first, then guessed paths."""
    done = {canonical_url(u) for u in rec.page_urls()}
    base = rec.homepage_url or f"https://{rec.domain}"
    out: list[tuple[str, str]] = []
    for cat in categories:
        if len(out) >= budget:
            break
        candidates = list(rec.discovered_links.get(cat, []))
        if not candidates:
            candidates = [canonical_url(urljoin(base, p)) for p in FALLBACK_PATHS.get(cat, [])]
        for url in candidates:
            if url not in done and all(url != u for u, _ in out):
                out.append((url, cat))
                break
    return out[:budget]


INITIAL_CATEGORIES = ["about", "security", "trust", "customers", "careers", "enterprise", "compliance", "pricing"]


def scrape_company(scraper: Scraper, company: str, domain: str, page_budget: int = 4) -> ScrapeRecord:
    """Homepage + the highest-priority discovered pages. Never raises."""
    try:
        rec, _ = scraper.scrape_homepage(company, domain)
        if rec.scraping_status == "failed":
            return finalise(rec)
        for url, cat in priority_targets(rec, INITIAL_CATEGORIES, page_budget):
            page, _ = scraper.scrape_page(url, cat, discovered_from=rec.homepage_url)
            rec.pages_scraped.append(page)
            if page.status != "ok":
                rec.errors.append(f"{url}: {page.status}")
        return finalise(rec)
    except Exception as exc:  # absolute last line of defence
        log.exception("Scrape crashed for %s", domain)
        return ScrapeRecord(company=company, domain=domain, scraping_status="failed", errors=[f"crash: {exc}"])


def finalise(rec: ScrapeRecord) -> ScrapeRecord:
    ok = rec.ok_pages()
    rec.raw_text = "\n\n".join(f"### SOURCE: {p.url}\n{p.text}" for p in ok)
    if not ok:
        rec.scraping_status = "failed"
    elif any(p.status != "ok" for p in rec.pages_scraped):
        rec.scraping_status = "partial"
    else:
        rec.scraping_status = "success"
    return rec


def _posted_date(job: dict) -> str:
    """Posting date from Greenhouse (first_published / updated_at), Lever (createdAt, ms) or Ashby (publishedAt)."""
    import datetime as _dt
    raw = job.get("first_published") or job.get("publishedAt") or job.get("updated_at") or job.get("createdAt")
    if isinstance(raw, (int, float)) and raw > 1e11:
        return _dt.datetime.fromtimestamp(raw / 1000, _dt.timezone.utc).date().isoformat()
    m = re.match(r"\d{4}-\d{2}-\d{2}", str(raw or ""))
    return m.group(0) if m else ""


def fetch_ats_jobs(scraper: Scraper, ats_url: str) -> Optional[PageRecord]:
    """Read public job-board APIs (Greenhouse / Lever / Ashby) linked from the company site."""
    for name, pat in ATS_PATTERNS.items():
        m = pat.search(ats_url)
        if not m:
            continue
        token = m.group(1)
        api = {
            "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
            "lever": f"https://api.lever.co/v0/postings/{token}?mode=json",
            "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{token}",
        }[name]
        res = scraper.fetch(api, want_json=True)
        if res["status"] != "ok":
            return PageRecord(url=api, category="careers", status=res["status"], title=res.get("error", ""))
        try:
            data = json.loads(res["body"])
        except json.JSONDecodeError:
            return PageRecord(url=api, category="careers", status="error", title="invalid JSON")
        jobs = data.get("jobs") if isinstance(data, dict) else data
        lines = []
        for j in (jobs or [])[:80]:
            title = j.get("title") or j.get("text") or ""
            dept = ""
            if isinstance(j.get("departments"), list) and j["departments"]:
                dept = j["departments"][0].get("name", "")
            elif isinstance(j.get("categories"), dict):
                dept = j["categories"].get("team", "")
            elif j.get("department"):
                dept = j["department"]
            body = j.get("content") or j.get("descriptionPlain") or j.get("description") or ""
            body_text = BeautifulSoup(BeautifulSoup(body, "html.parser").get_text(" "), "html.parser").get_text(" ")
            # Keep only sentences in the JD that mention compliance terms — that is the signal we need.
            hits = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body_text)
                    if re.search(r"SOC ?2|ISO ?27001|GDPR|HIPAA|compliance|audit|security review", s, re.I)][:3]
            posted = _posted_date(j)
            lines.append(f"JOB: {title}" + (f" | Team: {dept}" if dept else "") + (f" | posted: {posted}" if posted else "")
                         + ("".join(f"\n  JD: {h[:300]}" for h in hits)))
        text = f"Open roles listed on {name} job board ({len(jobs or [])} total)\n" + "\n".join(lines)
        return PageRecord(url=api, category="careers", title=f"{name} job board", text=text, status="ok",
                          rendered_with=f"{name}-api", discovered_from=ats_url)
    return None
