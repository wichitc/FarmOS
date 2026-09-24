"""Trial expiry watcher (master-prompt integration, Phase 34): periodically
moves any subscription whose trial has run out from "trialing" to
"past_due" - `trial_ends_at` passing has had no automatic consequence
since Phase 21, flagged explicitly as a deferral at the time. Same
polling-loop shape as `sla_watcher.py`, its own dedicated script since
each watcher here does one job matching its filename (same discipline
`seed_demo.py`/`sensor_simulator.py`/`bootstrap.py` already follow).

Runs as the `trial-watcher` docker-compose service.

Usage: python -m app.scripts.trial_watcher
"""
import logging
import time

from ..config import settings
from ..database import SessionLocal
from ..subscription import models as sub_models  # noqa: F401 - registers table in metadata
from ..subscription.service import check_trial_expirations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("trial-watcher")


def main() -> None:
    log.info("trial-watcher started, checking every %ds", settings.trial_watch_interval_seconds)
    while True:
        db = SessionLocal()
        try:
            expired = check_trial_expirations(db)
            if expired:
                log.info("%d subscription(s) moved trialing -> past_due: %s", len(expired), [s.tenant_id for s in expired])
        except Exception:
            log.exception("error in trial-watch loop")
        finally:
            db.close()
        time.sleep(settings.trial_watch_interval_seconds)


if __name__ == "__main__":
    main()
