"""Credential preflight: prove each integration actually works BEFORE a live run, without side effects.

Run with `python main.py --check`. Every check uses a free, read-only call and sends no email:
  * Claude   — GET /v1/models/{model} (authenticates the key and confirms model access; no tokens billed)
  * Hunter   — GET /v2/account (authenticates the key; does not consume search quota)
  * Gmail    — loads the OAuth token, confirms the gmail.send scope, refreshes it if expired
  * SMTP     — connect + STARTTLS + login, then quit (no message is submitted)
  * Recipient guard — TEST_TO_EMAIL passes `assert_allowed_recipient`
Results never contain key values; failures report only the HTTP status or exception class.
"""

from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass
from typing import Callable, Literal, Optional

import requests

from src.email_dispatcher import GMAIL_SCOPES, RecipientNotAllowed, assert_allowed_recipient

Status = Literal["ok", "fail", "skipped"]


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str


def check_recipient(s) -> CheckResult:
    try:
        assert_allowed_recipient(s.test_to_email, s.test_to_email)
        return CheckResult("Recipient guard", "ok", "TEST_TO_EMAIL is a valid single address; all sends are pinned to it")
    except RecipientNotAllowed as exc:
        return CheckResult("Recipient guard", "fail", str(exc))


def check_claude(s, client=None) -> CheckResult:
    if not s.anthropic_api_key:
        return CheckResult("Claude API", "skipped", "ANTHROPIC_API_KEY not set → pipeline uses the labelled deterministic fallback")
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=1)
        info = client.models.retrieve(s.anthropic_model)
        return CheckResult("Claude API", "ok", f"Key accepted; model {getattr(info, 'id', s.anthropic_model)} available")
    except Exception as exc:
        code = getattr(exc, "status_code", None)
        hint = {401: "key rejected", 403: "key lacks permission", 404: f"model {s.anthropic_model} not available to this key"}
        return CheckResult("Claude API", "fail", f"{exc.__class__.__name__}" + (f" (HTTP {code}: {hint.get(code, 'error')})" if code else ""))


def check_hunter(s, session=None) -> CheckResult:
    if "hunter" not in s.contact_providers:
        return CheckResult("Hunter.io", "skipped", "Hunter not in CONTACT_PROVIDERS")
    if not s.hunter_api_key:
        return CheckResult("Hunter.io", "skipped", "HUNTER_API_KEY not set → contacts come from the manual CSV and team pages only")
    session = session or requests.Session()
    try:
        r = session.get("https://api.hunter.io/v2/account", params={"api_key": s.hunter_api_key}, timeout=15)
    except Exception as exc:  # the request URL contains the key, so never echo the exception text
        return CheckResult("Hunter.io", "fail", f"Request failed ({exc.__class__.__name__})")
    if r.status_code != 200:
        return CheckResult("Hunter.io", "fail", f"HTTP {r.status_code}" + (" (key rejected)" if r.status_code in (401, 403) else ""))
    try:
        searches = r.json().get("data", {}).get("requests", {}).get("searches", {})
        left = searches.get("available", 0) - searches.get("used", 0)
        return CheckResult("Hunter.io", "ok", f"Key accepted; {left} domain searches left this period "
                                              f"(this run uses at most {s.hunter_max_calls})")
    except (ValueError, AttributeError, TypeError):
        return CheckResult("Hunter.io", "ok", "Key accepted (quota not reported)")


def check_gmail(s, creds_loader: Optional[Callable] = None) -> CheckResult:
    if s.email_backend != "gmail":
        return CheckResult("Gmail OAuth", "skipped", f"EMAIL_BACKEND={s.email_backend}")
    if not s.gmail_token_path.exists():
        if s.gmail_client_id and s.gmail_client_secret:
            return CheckResult("Gmail OAuth", "fail", "Client configured but no token: run `python main.py --gmail-auth`")
        return CheckResult("Gmail OAuth", "skipped", "Not configured (set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET, then --gmail-auth)")
    try:
        granted = set(json.loads(s.gmail_token_path.read_text()).get("scopes") or [])
        if granted and not set(GMAIL_SCOPES) <= granted:
            return CheckResult("Gmail OAuth", "fail", "Token lacks the gmail.send scope: re-run --gmail-auth")
        if creds_loader is None:
            from google.oauth2.credentials import Credentials
            creds_loader = lambda path: Credentials.from_authorized_user_file(path, GMAIL_SCOPES)  # noqa: E731
        creds = creds_loader(str(s.gmail_token_path))
        if not creds.valid:
            if not (creds.expired and creds.refresh_token):
                return CheckResult("Gmail OAuth", "fail", "Token invalid and not refreshable: re-run --gmail-auth")
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            s.gmail_token_path.write_text(creds.to_json())
        return CheckResult("Gmail OAuth", "ok", "Token valid with gmail.send scope (no message sent)")
    except Exception as exc:
        return CheckResult("Gmail OAuth", "fail", f"Token could not be used ({exc.__class__.__name__}): re-run --gmail-auth")


def check_smtp(s, smtp_factory: Optional[Callable] = None) -> CheckResult:
    if s.email_backend != "smtp":
        return CheckResult("SMTP", "skipped", f"EMAIL_BACKEND={s.email_backend}")
    if not (s.smtp_user and s.smtp_app_password):
        return CheckResult("SMTP", "fail", "SMTP_USER / SMTP_APP_PASSWORD not set")
    factory = smtp_factory or (lambda: smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20))
    try:
        with factory() as smtp:
            smtp.starttls()
            smtp.login(s.smtp_user, s.smtp_app_password)
        return CheckResult("SMTP", "ok", f"Logged in to {s.smtp_host}:{s.smtp_port} (no message sent)")
    except smtplib.SMTPAuthenticationError:
        return CheckResult("SMTP", "fail", "Login rejected: use a Google app password, not your account password")
    except Exception as exc:
        return CheckResult("SMTP", "fail", f"Connection failed ({exc.__class__.__name__})")


def check_search(s) -> CheckResult:
    if not s.search_provider:
        return CheckResult("Search provider", "skipped", "None configured; research agent reads company pages only")
    if not s.serper_api_key:
        return CheckResult("Search provider", "fail", f"SEARCH_PROVIDER={s.search_provider} but SERPER_API_KEY is empty")
    return CheckResult("Search provider", "skipped", "Key present but not tested (a test query would spend a credit)")


def run_checks(s) -> list[CheckResult]:
    return [check_recipient(s), check_claude(s), check_hunter(s), check_gmail(s), check_smtp(s), check_search(s)]


def ready_to_send(results: list[CheckResult], s) -> bool:
    by = {r.name: r.status for r in results}
    backend = "Gmail OAuth" if s.email_backend == "gmail" else "SMTP"
    return by.get("Recipient guard") == "ok" and by.get(backend) == "ok"
