"""Farm Manager orchestration (master-prompt integration, Phase 40, §28) -
the master prompt's diagram puts Farm Manager at the root, coordinating
the domain agents below it. Phase 24 cataloged it with an empty
`allowed_action_types` and left it "a documented placeholder for that
future role rather than a callable agent" because no cross-domain
synthesis engine existed yet.

This is that engine, scoped honestly: Farm Manager doesn't execute
anything or override a domain agent's own decisions (the five wired
agents - Irrigation, Fertilizer, Disease, Yield, Weather - keep doing
their own work exactly as before). What it adds is real cross-domain
*observation* - pulling together signals that already exist in separate
places (the farm score, Phase 27; recent domain-agent activity; open
alerts) into one synthesized, prioritized briefing. That's genuinely new
information (nothing today shows "everything relevant to this farm right
now" in one place), not a fabricated capability layered on top of
numbers this platform doesn't actually have.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..iot import models as iot_models
from ..twins import models as twin_models
from . import models as ai_models
from .farm_score import FarmScoreResult, compute_farm_score

RECENT_ACTION_WINDOW_HOURS = 72
RECENT_ACTION_LIMIT = 10


@dataclass
class AgentActionSummary:
    agent_code: str
    action_type: str
    status: str
    rationale: str
    created_at: datetime


@dataclass
class FarmManagerBriefing:
    farm_score: FarmScoreResult
    recent_agent_actions: list[AgentActionSummary] = field(default_factory=list)
    open_alert_count: int = 0
    priorities: list[str] = field(default_factory=list)


def _recent_agent_actions(db: Session, tenant_id: str, farm_id: str) -> list[AgentActionSummary]:
    since = datetime.now(timezone.utc) - timedelta(hours=RECENT_ACTION_WINDOW_HOURS)
    rows = (
        db.query(ai_models.AgentAction)
        .filter(
            ai_models.AgentAction.tenant_id == tenant_id,
            ai_models.AgentAction.farm_id == farm_id,
            ai_models.AgentAction.created_at >= since,
        )
        .order_by(ai_models.AgentAction.created_at.desc())
        .limit(RECENT_ACTION_LIMIT)
        .all()
    )
    return [
        AgentActionSummary(agent_code=a.agent_code, action_type=a.action_type, status=a.status, rationale=a.rationale, created_at=a.created_at)
        for a in rows
    ]


def _open_alert_count(db: Session, tenant_id: str, farm_id: str) -> int:
    """Alerts don't carry `farm_id` directly (`entity_type`/`entity_id`
    is generic, see `iot_models.Alert`'s docstring) - resolved here via
    the two entity types alerts are actually raised against today
    (`iot_device` for offline detection, `digital_twin` for rule
    breaches), both of which do carry `farm_id`."""
    device_ids = [row[0] for row in db.query(iot_models.IotDevice.id).filter(iot_models.IotDevice.tenant_id == tenant_id, iot_models.IotDevice.farm_id == farm_id).all()]
    twin_ids = [row[0] for row in db.query(twin_models.DigitalTwin.id).filter(twin_models.DigitalTwin.tenant_id == tenant_id, twin_models.DigitalTwin.farm_id == farm_id).all()]

    conditions = []
    if device_ids:
        conditions.append(and_(iot_models.Alert.entity_type == "iot_device", iot_models.Alert.entity_id.in_(device_ids)))
    if twin_ids:
        conditions.append(and_(iot_models.Alert.entity_type == "digital_twin", iot_models.Alert.entity_id.in_(twin_ids)))
    if not conditions:
        return 0

    return (
        db.query(iot_models.Alert)
        .filter(iot_models.Alert.tenant_id == tenant_id, iot_models.Alert.status == "open", or_(*conditions))
        .count()
    )


def _priorities(score_result: FarmScoreResult, open_alert_count: int) -> list[str]:
    """The actual synthesis step - turning raw signals into a short,
    plain-language, worst-first list. Never invents an issue: a good
    score and zero alerts produces exactly one reassuring line, not a
    padded list."""
    priorities = []
    if score_result.band in ("risk", "critical"):
        worst = score_result.factors[0]  # compute_farm_score already sorts worst-first
        priorities.append(f"Farm score is {score_result.band} ({score_result.score}/100) - {worst.explanation}")
    elif score_result.band == "warning":
        worst = score_result.factors[0]
        priorities.append(f"Farm score is in warning range ({score_result.score}/100) - {worst.explanation}")
    if open_alert_count > 0:
        priorities.append(f"{open_alert_count} open alert(s) need attention")
    if not priorities:
        priorities.append("No urgent issues detected across the farm's monitored signals.")
    return priorities


def compile_briefing(db: Session, *, tenant_id: str, farm_id: str) -> FarmManagerBriefing:
    score_result = compute_farm_score(db, tenant_id=tenant_id, farm_id=farm_id)
    recent_actions = _recent_agent_actions(db, tenant_id, farm_id)
    open_alert_count = _open_alert_count(db, tenant_id, farm_id)
    priorities = _priorities(score_result, open_alert_count)
    return FarmManagerBriefing(
        farm_score=score_result, recent_agent_actions=recent_actions, open_alert_count=open_alert_count, priorities=priorities,
    )
