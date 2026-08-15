"""Unit tests for SMTP feedback delivery."""

from __future__ import annotations

from email.message import EmailMessage

from pkm.web import feedback_mail


def test_feedback_email_is_not_attempted_without_smtp_configuration(
    monkeypatch,
) -> None:
    for name in (
        "PKM_FEEDBACK_SMTP_HOST",
        "PKM_FEEDBACK_SMTP_USERNAME",
        "PKM_FEEDBACK_SMTP_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    result = feedback_mail.send_feedback_email(
        vault_name="main",
        title="Keep feedback local",
        description="Record it in the vault too.",
        feedback_type="requirement",
        created_at="2026-08-15T09:30:00Z",
    )

    assert result.status == "not_configured"


def test_feedback_email_uses_starttls_and_default_recipient(monkeypatch) -> None:
    sent: list[EmailMessage] = []
    started_tls: list[bool] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 10)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self, *, context):
            assert context is not None
            started_tls.append(True)

        def login(self, username, password):
            assert (username, password) == ("sender@example.test", "secret")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setenv("PKM_FEEDBACK_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("PKM_FEEDBACK_SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("PKM_FEEDBACK_SMTP_PASSWORD", "secret")
    monkeypatch.delenv("PKM_FEEDBACK_EMAIL_TO", raising=False)
    monkeypatch.delenv("PKM_FEEDBACK_SMTP_USE_SSL", raising=False)
    monkeypatch.setattr(feedback_mail.smtplib, "SMTP", FakeSMTP)

    result = feedback_mail.send_feedback_email(
        vault_name="main",
        title="Keep feedback local",
        description="Record it in the vault too.",
        feedback_type="requirement",
        created_at="2026-08-15T09:30:00Z",
    )

    assert result.status == "sent"
    assert result.recipient == "ksm07091@gmail.com"
    assert started_tls == [True]
    assert sent[0]["To"] == "ksm07091@gmail.com"
    assert sent[0]["Subject"] == "[PKM feedback] Keep feedback local"
    assert "Vault: main" in sent[0].get_content()
