"""SCHEDULE execution engine (master-prompt integration, Phase 35, §25) -
Phase 26's own checklist named this gap explicitly: "a `scheduled_for`
timestamp is accepted and stored in the `AgentAction.input_context`, but
nothing watches for it and fires the command later." `fire_scheduled_commands`
is that watcher's per-tenant check; `mqtt_ingestion_worker.py`'s existing
periodic loop calls it the same way it already calls
`check_offline_devices` - one more thing that loop does, not a new service.

A schedule command's `AgentAction` is created in `routers/v1/iot.py::
send_actuator_command` but deliberately left `status="proposed"` rather
than executed immediately - this module is what actually calls
`agent_gateway.execute_action` and updates the twin, once `scheduled_for`
has arrived. `confirmed=True` here is not re-asking for confirmation -
the human already confirmed in the original request; this only replays
that already-granted confirmation at execution time.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ai import agent_gateway
from ..ai import models as ai_models
from ..twins import models as twin_models
from . import models as iot_models


def fire_scheduled_commands(db: Session, tenant_id: str) -> list[ai_models.AgentAction]:
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(ai_models.AgentAction)
        .filter(
            ai_models.AgentAction.tenant_id == tenant_id,
            ai_models.AgentAction.action_type == "actuator_start",
            ai_models.AgentAction.status == "proposed",
        )
        .all()
    )

    fired = []
    for action in candidates:
        if action.input_context.get("command") != "schedule":
            continue
        scheduled_for_raw = action.input_context.get("scheduled_for")
        if not scheduled_for_raw:
            continue
        scheduled_for = datetime.fromisoformat(scheduled_for_raw)
        if scheduled_for > now:
            continue

        agent_gateway.execute_action(
            db, action=action, actor=None, confirmed=True,
            result={"command": "schedule", "device_id": action.entity_id, "fired_at": now.isoformat()},
        )

        device = db.get(iot_models.IotDevice, action.entity_id)
        if device is not None:
            twin = db.get(twin_models.DigitalTwin, device.digital_twin_id)
            if twin is not None:
                twin.current_state = {**twin.current_state, "actuator_status": "schedule", "last_command_at": now.isoformat()}
        fired.append(action)

    if fired:
        db.commit()
    return fired
