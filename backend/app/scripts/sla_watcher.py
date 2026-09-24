"""SLA breach watcher (master-prompt integration, Phase 33): periodically
flags support tickets whose `sla_due_at` has passed - the "scheduler this
repo doesn't have" `iot_models.Alert`'s own docstring names as the reason
SLA/escalation timing was never modeled. This is the simplest real one:
a polling loop, same shape as `mqtt_ingestion_worker.py`'s own
`_offline_check_loop`, just for support tickets rather than IoT devices,
and with no per-tenant RLS loop needed since `SupportTicket` is
platform-global (Phase 20).

Runs as the `sla-watcher` docker-compose service.

Usage: python -m app.scripts.sla_watcher
"""
import logging
import time

from ..config import settings
from ..crm import models as crm_models  # noqa: F401 - registers table in metadata
from ..crm.service import check_sla_breaches
from ..database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sla-watcher")


def main() -> None:
    log.info("sla-watcher started, checking every %ds", settings.sla_watch_interval_seconds)
    while True:
        db = SessionLocal()
        try:
            breached = check_sla_breaches(db)
            if breached:
                log.info("%d ticket(s) newly flagged as SLA-breached: %s", len(breached), [t.id for t in breached])
        except Exception:
            log.exception("error in SLA-watch loop")
        finally:
            db.close()
        time.sleep(settings.sla_watch_interval_seconds)


if __name__ == "__main__":
    main()
