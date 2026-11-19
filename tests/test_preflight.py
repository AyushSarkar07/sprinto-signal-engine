"""Credential preflight: correct verdicts, no secrets in output, no email ever sent."""

from __future__ import annotations

import json
import smtplib

from src import preflight
from tests.conftest import FakeResp

SECRET = "sk-test-SECRET-123"


class FakeModels:
    def __init__(self, exc=None):
        self.exc = exc

    def retrieve(self, model_id):
        if self.exc:
            raise self.exc
        return type("Info", (), {"id": model_id})()


class FakeClient:
    def __init__(self, exc=None):
        self.models = FakeModels(exc)


class StatusError(Exception):
    def __init__(self, code):
        super().__init__(f"error with key {SECRET}")
        self.status_code = code


def test_recipient_guard_requires_test_address(settings):
    assert preflight.check_recipient(settings).status == "ok"
    settings.test_to_email = ""
    assert preflight.check_recipient(settings).status == "fail"


def test_claude_skipped_without_key_and_ok_with_valid_key(settings):
    assert preflight.check_claude(settings).status == "skipped"
    settings.anthropic_api_key = SECRET
    assert preflight.check_claude(settings, client=FakeClient()).status == "ok"


def test_claude_failure_reports_status_not_secret(settings):
    settings.anthropic_api_key = SECRET
    r = preflight.check_claude(settings, client=FakeClient(StatusError(401)))
    assert r.status == "fail" and "401" in r.detail and SECRET not in r.detail


def test_hunter_account_check_reports_quota_without_key(settings):
    settings.hunter_api_key = SECRET
    body = json.dumps({"data": {"requests": {"searches": {"available": 25, "used": 5}}}})

    class S:
        def get(self, url, params=None, timeout=None):
            assert url.endswith("/v2/account")  # free endpoint, never domain-search
            return FakeResp(200, body, url)

    r = preflight.check_hunter(settings, session=S())
    assert r.status == "ok" and "20 domain searches" in r.detail and SECRET not in r.detail


def test_hunter_rejected_key_and_network_error_hide_key(settings):
    settings.hunter_api_key = SECRET

    class Bad:
        def get(self, url, params=None, timeout=None):
            return FakeResp(401, "", url)

    class Boom:
        def get(self, url, params=None, timeout=None):
            raise ConnectionError(f"https://api.hunter.io/v2/account?api_key={SECRET}")

    assert preflight.check_hunter(settings, session=Bad()).status == "fail"
    r = preflight.check_hunter(settings, session=Boom())
    assert r.status == "fail" and SECRET not in r.detail


def test_gmail_token_scope_and_validity(settings, tmp_path):
    settings.gmail_token_path = tmp_path / "token.json"
    assert preflight.check_gmail(settings).status == "skipped"
    settings.gmail_token_path.write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}))
    assert "scope" in preflight.check_gmail(settings).detail
    settings.gmail_token_path.write_text(json.dumps({"scopes": preflight.GMAIL_SCOPES}))
    valid = type("C", (), {"valid": True})()
    assert preflight.check_gmail(settings, creds_loader=lambda p: valid).status == "ok"


def test_smtp_logs_in_but_never_sends(settings):
    settings.email_backend, settings.smtp_user, settings.smtp_app_password = "smtp", "me@example.com", SECRET
    events = []

    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): events.append("quit")
        def starttls(self): events.append("tls")
        def login(self, u, p): events.append("login")
        def send_message(self, *a, **k): raise AssertionError("preflight must never send")
        def sendmail(self, *a, **k): raise AssertionError("preflight must never send")

    assert preflight.check_smtp(settings, smtp_factory=FakeSMTP).status == "ok"
    assert events == ["tls", "login", "quit"]

    class Rejecting(FakeSMTP):
        def login(self, u, p): raise smtplib.SMTPAuthenticationError(535, b"bad")

    r = preflight.check_smtp(settings, smtp_factory=Rejecting)
    assert r.status == "fail" and SECRET not in r.detail


def test_ready_to_send_needs_guard_and_backend(settings):
    ok = preflight.CheckResult
    assert preflight.ready_to_send([ok("Recipient guard", "ok", ""), ok("Gmail OAuth", "ok", "")], settings)
    assert not preflight.ready_to_send([ok("Recipient guard", "fail", ""), ok("Gmail OAuth", "ok", "")], settings)
    assert not preflight.ready_to_send([ok("Recipient guard", "ok", ""), ok("Gmail OAuth", "skipped", "")], settings)
