"""Scenarios 11 & 12: Gmail credentials missing, and attempts to send anywhere other than TEST_TO_EMAIL."""
from email.message import EmailMessage

import pytest

from src.email_dispatcher import (Dispatcher, RecipientNotAllowed, assert_allowed_recipient, assert_message_safe,
                                  build_message, render_preview)
from src.models import GeneratedEmail

TEST = "me@example.com"


def email(prospect="cto@prospect.example"):
    return GeneratedEmail(recipient_name="Sam Park", recipient_email=prospect, subject="audit prep at Acme",
                          email_body="Hi Sam,\n\nBody.", personalisation_hook="hook", hook_source_url="https://acme.example/security",
                          pain_point_used="pain", why_this_email_was_written="why")


@pytest.mark.parametrize("bad", [
    "cto@prospect.example", "ME@example.com.evil.com", "me@example.co", "me@example.com, cto@prospect.example",
    "me@example.com;cto@prospect.example", "me@example.com\r\nBcc: cto@prospect.example", "Evil <cto@prospect.example>",
    '"me@example.com" <cto@prospect.example>', "", "not-an-email", "me@example.com\n",
])
def test_guard_rejects_everything_but_test_address(bad):
    with pytest.raises(RecipientNotAllowed):
        assert_allowed_recipient(bad, TEST)


def test_guard_accepts_only_exact_test_address():
    assert assert_allowed_recipient("me@example.com", TEST) == TEST
    assert assert_allowed_recipient("Me <ME@example.com>", TEST) == TEST


def test_guard_refuses_when_test_address_unset():
    with pytest.raises(RecipientNotAllowed):
        assert_allowed_recipient("me@example.com", "")


@pytest.mark.parametrize("header", ["Cc", "Bcc", "Resent-To"])
def test_message_with_extra_recipients_is_rejected(header):
    msg = build_message("preview", "s", "Acme", TEST, TEST)
    msg[header] = "cto@prospect.example"
    with pytest.raises(RecipientNotAllowed):
        assert_message_safe(msg, TEST)


def test_message_with_tampered_to_is_rejected():
    msg = build_message("preview", "s", "Acme", TEST, TEST)
    del msg["To"]
    msg["To"] = "cto@prospect.example"
    with pytest.raises(RecipientNotAllowed):
        assert_message_safe(msg, TEST)


def test_built_message_never_addresses_prospect():
    preview = render_preview(email(), "Acme", "Sam Park", "cto@prospect.example", ["qualified"], "CTO owns it", "reason")
    msg = build_message(preview, "s", "Acme", TEST, TEST)
    assert msg["To"] == TEST and "TEST PREVIEW" in msg.get_content()
    assert "Intended recipient: Sam Park" in preview and "Original prospect email: cto@prospect.example" in preview
    assert "WHY THIS EMAIL WAS GENERATED" in preview


def test_dry_run_never_sends(settings, monkeypatch):
    d = Dispatcher(settings, send_enabled=True)  # settings.dry_run is True
    monkeypatch.setattr(d, "_send_gmail", lambda m: pytest.fail("must not send in dry run"))
    res = d.dispatch(email(), "acme", "preview", "Acme")
    assert res.status == "dry_run_preview" and res.preview_path.endswith(".eml")


def test_missing_gmail_credentials_reported_not_faked(settings):
    settings.dry_run = False
    settings.gmail_client_id = settings.gmail_client_secret = ""
    settings.gmail_token_path = settings.output_dir / "nope.json"
    res = Dispatcher(settings, send_enabled=True).dispatch(email(), "acme", "preview", "Acme")
    assert res.status == "blocked_missing_credentials" and "GMAIL_CLIENT_ID" in res.detail


def test_send_path_delivers_only_to_test_address(settings, monkeypatch):
    settings.dry_run = False
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path = settings.output_dir / "token.json"
    settings.gmail_token_path.write_text("{}")
    d = Dispatcher(settings, send_enabled=True)
    sent = []
    monkeypatch.setattr(d, "_send_gmail", lambda m: (assert_message_safe(m, TEST), sent.append(m["To"]), "id1")[-1])
    res = d.dispatch(email(), "acme", "preview", "Acme")
    assert res.status == "sent" and sent == [TEST] and res.delivered_to == TEST


def test_unset_test_address_blocks_send(settings):
    settings.test_to_email = ""
    settings.dry_run = False
    res = Dispatcher(settings, send_enabled=True).dispatch(email(), "acme", "preview", "Acme")
    assert res.status == "blocked_by_guard"
