"""Knowledge Base (master-prompt integration §29, Phase 25) - the RAG
pipeline's *storage and retrieval* half, without the vendor decision its
*embedding* half needs (Qdrant vs. pgvector, which embeddings provider -
same class of decision already deferred for the LLM provider itself,
ADR-011). Retrieval here uses PostgreSQL's built-in full-text search
(`to_tsvector`/`plainto_tsquery`/`ts_rank`), not vector similarity - a
real, working, keyword-grounded retrieval mechanism today, with the
contract (`search_chunks` returns ranked chunks with citations) shaped so
swapping the *implementation* for embedding-based similarity later
doesn't need to change any caller, including `ai/copilot.py`.

Unlike the vendor-CRM modules (`app.crm`), this data is a *tenant's own*
farm knowledge (SOPs, crop/soil reference material, internal notes) -
squarely tenant business data, so it's `TenantScopedMixin`/RLS-protected
like every other domain module, not platform-global.
"""
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid
from .embeddings import EMBEDDING_DIM

DOCUMENT_CATEGORIES = ("sop", "crop_knowledge", "soil_knowledge", "internal", "other")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class KnowledgeDocument(TenantScopedMixin, Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = _uuid_pk()
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(30), default="other")
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeChunk(TenantScopedMixin, Base):
    """Paragraph-sized slices of a document's `content` - what search
    actually matches against and what a citation points at, so a long
    document doesn't come back as one giant, hard-to-cite blob."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = _uuid_pk()
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # Nullable: rows indexed while Ollama was unreachable stay keyword-only
    # searchable rather than blocking indexing (see service.py's fail-open
    # embedding logic) - `search_chunks` filters these out of the vector
    # path and relies on full-text search to still surface them.
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
