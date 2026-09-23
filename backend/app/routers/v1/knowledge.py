from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.deps import require_permission
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...knowledge import models as kb_models
from ...knowledge import schemas as kb_schemas
from ...knowledge import service as kb_service
from ...database import get_db

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


@router.post("/documents", response_model=kb_schemas.DocumentOut, status_code=201)
def create_document(
    payload: kb_schemas.DocumentCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("knowledge.document.manage")),
):
    if payload.category not in kb_models.DOCUMENT_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{payload.category}'")

    document = kb_models.KnowledgeDocument(
        tenant_id=current_user.tenant_id, title=payload.title, category=payload.category,
        content=payload.content, created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(document)
    db.flush()
    kb_service.index_document(db, document)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="knowledge_document.create", entity_type="knowledge_document", entity_id=document.id,
        new_values={"title": document.title, "category": document.category},
    )
    db.commit()
    return document


@router.get("/documents", response_model=list[kb_schemas.DocumentSummaryOut])
def list_documents(
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("knowledge.document.view")),
):
    query = db.query(kb_models.KnowledgeDocument)
    if category:
        query = query.filter(kb_models.KnowledgeDocument.category == category)
    return query.order_by(kb_models.KnowledgeDocument.created_at.desc()).all()


@router.get("/documents/{document_id}", response_model=kb_schemas.DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("knowledge.document.view")),
):
    return _get_or_404(db, kb_models.KnowledgeDocument, document_id, "Knowledge document")


@router.patch("/documents/{document_id}", response_model=kb_schemas.DocumentOut)
def update_document(
    document_id: str,
    payload: kb_schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("knowledge.document.manage")),
):
    document = _get_or_404(db, kb_models.KnowledgeDocument, document_id, "Knowledge document")
    if payload.category is not None and payload.category not in kb_models.DOCUMENT_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{payload.category}'")

    changes = payload.model_dump(exclude_unset=True)
    content_changed = "content" in changes
    for field, value in changes.items():
        setattr(document, field, value)
    document.updated_by = current_user.id
    db.flush()

    if content_changed:
        kb_service.index_document(db, document)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="knowledge_document.update", entity_type="knowledge_document", entity_id=document.id,
        new_values={k: v for k, v in changes.items() if k != "content"} | ({"content": "(updated)"} if content_changed else {}),
    )
    db.commit()
    return document


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("knowledge.document.manage")),
):
    document = _get_or_404(db, kb_models.KnowledgeDocument, document_id, "Knowledge document")
    db.delete(document)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="knowledge_document.delete", entity_type="knowledge_document", entity_id=document_id,
    )
    db.commit()


@router.get("/search", response_model=list[kb_schemas.SearchHitOut])
def search(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("knowledge.document.view")),
):
    hits = kb_service.search_chunks(db, tenant_id=current_user.tenant_id, query=q)
    return [
        kb_schemas.SearchHitOut(
            document_id=hit.document.id, document_title=hit.document.title,
            chunk_id=hit.chunk.id, chunk_index=hit.chunk.chunk_index, content=hit.chunk.content, rank=hit.rank,
        )
        for hit in hits
    ]
