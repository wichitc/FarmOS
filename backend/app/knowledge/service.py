"""Chunking and full-text search - see `models.py`'s module docstring for
why this is keyword search (Postgres `to_tsvector`), not vector
similarity, and why that's a deliberate, documented interim choice
rather than a shortcut nobody decided on.
"""
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models as kb_models


def chunk_text(content: str, max_chars: int = 800) -> list[str]:
    """Splits on paragraph boundaries (blank lines), merging consecutive
    short paragraphs up to `max_chars` so a chunk is neither one giant
    document nor one sentence - a reasonable middle ground for both
    search relevance and citation readability without a real tokenizer."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = paragraphs[0]
    for paragraph in paragraphs[1:]:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            current = paragraph
    chunks.append(current)
    return chunks


def index_document(db: Session, document: kb_models.KnowledgeDocument) -> list[kb_models.KnowledgeChunk]:
    """Replaces any existing chunks for this document with freshly
    computed ones - called on create and on content update, so a chunk
    never silently drifts out of sync with its document's current text."""
    db.query(kb_models.KnowledgeChunk).filter(kb_models.KnowledgeChunk.document_id == document.id).delete()

    chunks = []
    for index, text in enumerate(chunk_text(document.content)):
        chunk = kb_models.KnowledgeChunk(
            tenant_id=document.tenant_id, document_id=document.id, chunk_index=index, content=text,
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()
    return chunks


@dataclass
class SearchHit:
    chunk: kb_models.KnowledgeChunk
    document: kb_models.KnowledgeDocument
    rank: float


def search_chunks(db: Session, *, tenant_id: str, query: str, limit: int = 5) -> list[SearchHit]:
    tsquery = func.plainto_tsquery("english", query)
    tsvector = func.to_tsvector("english", kb_models.KnowledgeChunk.content)
    rank = func.ts_rank(tsvector, tsquery)

    rows = (
        db.query(kb_models.KnowledgeChunk, kb_models.KnowledgeDocument, rank.label("rank"))
        .join(kb_models.KnowledgeDocument, kb_models.KnowledgeDocument.id == kb_models.KnowledgeChunk.document_id)
        .filter(kb_models.KnowledgeDocument.is_active.is_(True))
        .filter(tsvector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
        .all()
    )
    return [SearchHit(chunk=chunk, document=document, rank=float(r)) for chunk, document, r in rows]
