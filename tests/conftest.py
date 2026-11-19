"""Shared fixtures: an offline fake HTTP session and isolated settings (no network, no real credentials)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Settings  # noqa: E402


class FakeResp:
    def __init__(self, status_code: int, text: str = "", url: str = "", ctype: str = "text/html; charset=utf-8"):
        self.status_code, self.text, self.url = status_code, text, url
        self.headers = {"Content-Type": ctype}
        self.encoding = "utf-8"

    def json(self):
        import json
        return json.loads(self.text)


class FakeSession:
    """Maps exact URLs to (status, body) or an exception instance. Unknown URLs → 404. Records every call."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []
        self.headers: dict = {}

    def get(self, url, timeout=None, allow_redirects=True, params=None):
        self.calls.append(url)
        r = self.routes.get(url, self.routes.get(url.rstrip("/")))
        if isinstance(r, Exception):
            raise r
        if r is None:
            return FakeResp(404, "", url)
        status, body = r[0], r[1]
        ctype = r[2] if len(r) > 2 else "text/html; charset=utf-8"
        return FakeResp(status, body, url, ctype)


def page(body: str, title: str = "Page", links: str = "") -> str:
    return f"<html><head><title>{title}</title></head><body><nav>Menu Home Pricing</nav>{links}<main>{body}</main>" \
           f"<div id='cookie-banner'>We use cookies. Accept all</div><script>var x=1;</script></body></html>"


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(output_dir=tmp_path / "output", prompts_dir=ROOT / "prompts", contacts_csv=tmp_path / "contacts.csv",
                 outcomes_csv=tmp_path / "outcomes.csv", revenue_assumptions=tmp_path / "assumptions.json",
                 request_delay=0.0, request_timeout=2, test_to_email="me@example.com", dry_run=True,
                 contact_providers=["hunter", "manual", "website"])
    s.output_dir.mkdir(parents=True)
    return s


@pytest.fixture
def conn_error():
    return requests.exceptions.ConnectionError("dns failure")


SAAS_HOME = page(
    "<h1>Acme is the workflow automation platform for finance teams</h1>"
    "<p>Acme is a B2B SaaS platform that automates approvals for finance teams at banks and insurers.</p>"
    "<p>Start your free trial today or book a demo with our team.</p>"
    "<p>Pricing is per user per month, billed annually.</p><p>Log in</p>"
    "<p>Integrations with your ERP and a full REST API.</p>"
    "<p>Trusted by finance teams at Fortune 500 companies including Globex and Initech.</p>",
    "Acme — finance workflow automation",
    links="<a href='/security'>Security</a><a href='/careers'>Careers</a><a href='/about'>About us</a>",
)
SECURITY_PAGE = page(
    "<h1>Security at Acme</h1><p>We are currently working towards SOC 2 Type II and expect our report in Q2.</p>"
    "<p>All data is encrypted at rest with AES-256 and in transit with TLS 1.2.</p>"
    "<p>Customers can request our security questionnaire responses and DPA from the trust team.</p>",
    "Security | Acme")
