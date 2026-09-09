from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy.orm import Session

from . import models as fm


class NotificationSender(ABC):
    @abstractmethod
    def send(
        self,
        db: Session,
        *,
        tenant_id: str,
        user_id: str,
        title: str,
        body: str,
        severity: str = "info",
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
    ) -> fm.Notification:
        ...


class InAppNotificationSender(NotificationSender):
    """Writes to the `notifications` table, read by the web/mobile clients.
    The always-available default channel (FR-PLT-008); Email/LINE/SMS are
    integration-ready per the platform brief but not wired to real credentials
    in this phase - see EmailNotificationSender/LineNotificationSender below.
    """

    def send(
        self,
        db: Session,
        *,
        tenant_id: str,
        user_id: str,
        title: str,
        body: str,
        severity: str = "info",
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
    ) -> fm.Notification:
        notif = fm.Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            channel="web",
            severity=severity,
            title=title,
            body=body,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        db.add(notif)
        db.flush()
        return notif


class EmailNotificationSender(NotificationSender):
    """Integration point for SEC/INT-003's provider-abstracted channels.
    Not wired to a real SMTP/API provider in Phase 3 - no tenant credentials
    exist yet to send through. Implement `send` against a chosen provider
    when Phase 8+ needs outbound email; the interface is intentionally
    provider-agnostic so that choice doesn't touch call sites."""

    def send(self, db: Session, **kwargs):  # pragma: no cover - not wired yet
        raise NotImplementedError("Email channel is not configured for this deployment")


class LineNotificationSender(NotificationSender):
    """Integration point for the LINE channel referenced in FR-PLT-008. Not
    wired to the LINE Messaging API in Phase 3, for the same reason as
    EmailNotificationSender."""

    def send(self, db: Session, **kwargs):  # pragma: no cover - not wired yet
        raise NotImplementedError("LINE channel is not configured for this deployment")


default_sender: NotificationSender = InAppNotificationSender()
