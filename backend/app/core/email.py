"""Outbound email (master-prompt integration, Phase 42) - the vendor
decision deferred since Phase 3's `foundation.notifications.
EmailNotificationSender` was first stubbed ("not wired to a real SMTP/
API provider - no tenant credentials exist yet"). Resolved directly
with the user: SendGrid, no A/B decision needed the way the RAG
embeddings choice was.

No live SendGrid API key exists in this dev/CI environment - `send_email`
no-ops with a clear log line when `sendgrid_api_key` is unset, the same
fail-open-but-honest treatment this platform gives every other missing-
credential path (see `knowledge/embeddings.py`'s `EmbeddingUnavailable`),
rather than crashing every caller in every environment that doesn't have
a real key. A caller who needs to know whether a send actually happened
gets that from `send_email`'s return value, not an exception - a failed
or skipped notification email should never roll back the business
operation that triggered it.
"""
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailSendError(Exception):
    """Raised only for a genuine SendGrid-side failure (bad key rejected,
    malformed payload, etc.) - never for "no key configured", which is
    not an error, just an unconfigured environment."""


def send_email(*, to: str, subject: str, body: str) -> bool:
    """Returns True if a send was actually attempted and accepted by
    SendGrid, False if skipped because no API key is configured. Raises
    `EmailSendError` only if a key IS configured but SendGrid rejects
    the request - a real, actionable failure the caller should know
    about, as opposed to the expected no-op in dev/CI."""
    if not settings.sendgrid_api_key:
        logger.warning("SENDGRID_API_KEY not configured; skipping email to %s: %s", to, subject)
        return False

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.email_from_address},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    try:
        response = httpx.post(
            SENDGRID_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailSendError(str(exc)) from exc
    return True
