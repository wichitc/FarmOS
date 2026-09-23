"""Copilot answer engine (FR-COPILOT-001, AI-003/ADR-011).

No LLM endpoint is wired yet (ADR-011 defers the Ollama/OpenAI-compatible
decision to deployment time - ai/llm_provider.py's `StubLLMProvider` is
the seam). Rather than fake a free-text answer, this module keeps the
"answers only from real platform data, cites source/timestamp/confidence"
contract honest by construction: each supported question category runs a
real query against this tenant's own rows and builds its answer text from
what it actually finds, and every fact stated carries a citation pointing
at the row it came from. A question outside the supported categories gets
an explicit "I can't answer that yet" rather than an invented answer -
never a hallucinated fact dressed up as one.
"""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from ..crophealth import models as crophealth_models
from ..inventory import models as inventory_models
from ..iot import models as iot_models
from ..knowledge import service as kb_service


@dataclass
class CopilotAnswer:
    content: str
    citations: list[dict] = field(default_factory=list)


def _citation(source_type: str, source_id: str, timestamp, confidence: Optional[float] = None) -> dict:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "confidence": confidence,
    }


def _answer_open_alerts(db: Session, tenant_id: str, farm_id: Optional[str]) -> CopilotAnswer:
    alerts = (
        db.query(iot_models.Alert)
        .filter(iot_models.Alert.status == "open")
        .order_by(iot_models.Alert.raised_at.desc())
        .limit(5)
        .all()
    )
    if not alerts:
        return CopilotAnswer(content="There are no open alerts right now.")
    lines = [f"There are {len(alerts)} open alert(s) (showing up to 5):"]
    citations = []
    for a in alerts:
        lines.append(f"- [{a.severity}] {a.message}")
        citations.append(_citation("iot_alert", a.id, a.raised_at))
    return CopilotAnswer(content="\n".join(lines), citations=citations)


def _answer_disease_incidents(db: Session, tenant_id: str, farm_id: Optional[str]) -> CopilotAnswer:
    query = db.query(crophealth_models.DiseaseIncident).filter(
        crophealth_models.DiseaseIncident.status.notin_(("resolved", "false_positive"))
    )
    if farm_id:
        query = query.filter(crophealth_models.DiseaseIncident.farm_id == farm_id)
    incidents = query.order_by(crophealth_models.DiseaseIncident.created_at.desc()).limit(5).all()
    if not incidents:
        return CopilotAnswer(content="No open disease incidents.")
    lines = [f"There are {len(incidents)} open disease incident(s) (showing up to 5):"]
    citations = []
    for inc in incidents:
        risk = f"risk {inc.risk_score:.0f}" if inc.risk_score is not None else "risk unscored"
        lines.append(f"- Incident {inc.id[:8]} ({inc.status}, {risk})")
        citations.append(_citation("disease_incident", inc.id, inc.created_at, inc.confidence))
    return CopilotAnswer(content="\n".join(lines), citations=citations)


def _answer_low_stock(db: Session, tenant_id: str, farm_id: Optional[str]) -> CopilotAnswer:
    rows = (
        db.query(inventory_models.StockLot, inventory_models.Item)
        .join(inventory_models.Item, inventory_models.Item.id == inventory_models.StockLot.item_id)
        .filter(inventory_models.Item.min_qty.isnot(None))
        .all()
    )
    totals: dict[str, float] = {}
    for lot, item in rows:
        totals[item.id] = totals.get(item.id, 0.0) + lot.quantity
    items_by_id = {item.id: item for _, item in rows}
    low = [(items_by_id[iid], qty) for iid, qty in totals.items() if qty < items_by_id[iid].min_qty]
    if not low:
        return CopilotAnswer(content="No items are currently below their reorder point.")
    lines = [f"{len(low)} item(s) are below their reorder point:"]
    citations = []
    for item, qty in low[:5]:
        lines.append(f"- {item.name} ({item.code}): {qty} {item.uom} on hand, min {item.min_qty}")
        citations.append(_citation("inventory_item", item.id, None))
    return CopilotAnswer(content="\n".join(lines), citations=citations)


def _answer_from_knowledge_base(db: Session, tenant_id: str, farm_id: Optional[str], question: str) -> Optional[CopilotAnswer]:
    """The RAG groundwork's answer path (master-prompt integration §29,
    Phase 25) - full-text search over this tenant's own knowledge
    documents, not vector similarity (see `knowledge/models.py`'s module
    docstring for why). Returns `None` on no match so the caller can fall
    through to the final "I can't answer that" message, same as every
    other route here never fabricating an answer."""
    hits = kb_service.search_chunks(db, tenant_id=tenant_id, query=question, limit=3)
    if not hits:
        return None
    lines = [f"From the knowledge base ({len(hits)} relevant passage(s)):"]
    citations = []
    for hit in hits:
        lines.append(f"- [{hit.document.title}] {hit.chunk.content[:280]}")
        citations.append(_citation("knowledge_chunk", hit.chunk.id, hit.document.created_at, hit.rank))
    return CopilotAnswer(content="\n".join(lines), citations=citations)


_ROUTES: list[tuple[tuple[str, ...], callable]] = [
    (("alert", "alarm"), _answer_open_alerts),
    (("disease", "incident", "pest"), _answer_disease_incidents),
    (("stock", "inventory", "reorder", "low"), _answer_low_stock),
]


def answer_question(db: Session, *, tenant_id: str, farm_id: Optional[str], question: str) -> CopilotAnswer:
    lowered = question.lower()
    for keywords, handler in _ROUTES:
        if any(kw in lowered for kw in keywords):
            return handler(db, tenant_id, farm_id)

    kb_answer = _answer_from_knowledge_base(db, tenant_id, farm_id, question)
    if kb_answer is not None:
        return kb_answer

    return CopilotAnswer(
        content=(
            "I can currently only answer questions grounded in platform data about: "
            "open alerts, open disease incidents, low/reorder-point stock items, "
            "and anything covered in your knowledge base documents. "
            "Try asking about one of those."
        )
    )
