from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SendOutcome:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class EmailProvider(Protocol):
    """Provider-specific sending behind one interface (architecture §13.3)."""

    def configured(self) -> bool: ...

    async def send(
        self, *, from_address: str, to_address: str, subject: str, body: str
    ) -> SendOutcome: ...


class SmtpProvider:
    """stdlib SMTP sender, configured from environment only.

    Deliberately synchronous at the transport level; `send` runs it in a thread
    so the event loop is not blocked by a slow relay.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configured(self) -> bool:
        if self._settings.app_env == "development" or self._settings.smtp_host in (
            "mock",
            "sandbox",
        ):
            return True
        return bool(self._settings.smtp_host)

    def _deliver(self, from_address: str, to_address: str, subject: str, body: str) -> SendOutcome:
        settings = self._settings
        if not settings.smtp_host or settings.smtp_host in ("mock", "sandbox"):
            import time

            logger.info(
                "smtp_mock_delivery",
                from_address=from_address,
                to_address=to_address,
                subject=subject,
            )
            return SendOutcome(ok=True, provider_message_id=f"dev-mock-{int(time.time() * 1000)}")
        message = EmailMessage()
        message["From"] = from_address
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)
        try:
            if settings.smtp_use_ssl:
                client: smtplib.SMTP = smtplib.SMTP_SSL(
                    settings.smtp_host, settings.smtp_port, timeout=30
                )
            else:
                client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
                if settings.smtp_use_tls:
                    client.starttls()
            try:
                if settings.smtp_username:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(message)
            finally:
                client.quit()
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("smtp_send_failed", error_type=type(exc).__name__)
            return SendOutcome(ok=False, error=f"{type(exc).__name__}: {exc}")
        # SMTP has no per-message id without a relay response; report the accepted
        # delivery as sent without inventing a provider id.
        return SendOutcome(ok=True)

    async def send(
        self, *, from_address: str, to_address: str, subject: str, body: str
    ) -> SendOutcome:
        if not self.configured():
            return SendOutcome(ok=False, error="No SMTP host configured")
        return await asyncio.to_thread(
            self._deliver, from_address, to_address, subject, body
        )


class GmailOAuthProvider:
    """Gmail OAuth sender. Requires OAuth tokens this deployment does not hold.

    `configured()` is false until credentials are supplied, so a send attempt
    fails loudly instead of pretending to use an API it cannot reach.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configured(self) -> bool:
        return bool(self._settings.gmail_client_id and self._settings.gmail_refresh_token)

    async def send(
        self, *, from_address: str, to_address: str, subject: str, body: str
    ) -> SendOutcome:
        del from_address, to_address, subject, body
        return SendOutcome(
            ok=False,
            error="Gmail OAuth is not configured. Provide client credentials or use SMTP.",
        )


def build_provider(settings: Settings, provider: str) -> EmailProvider:
    if provider == "smtp":
        return SmtpProvider(settings)
    if provider == "gmail_oauth":
        return GmailOAuthProvider(settings)
    raise ValueError(f"Unknown email provider '{provider}'")
