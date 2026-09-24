"""Chunking + retrieval for the Knowledge Base (Phase 28: real semantic
search). `index_document` computes a real embedding per chunk via
`embeddings.default_provider` (Ollama/nomic-embed-text); `search_chunks`
does pgvector cosine-similarity search as the primary retrieval path.

Both fail open, not closed, when Ollama is unreachable
(`EmbeddingUnavailable`): indexing still stores the chunk with
`embedding=None` rather than rejecting the whole document, and search
falls back to the pre-Phase-28 full-text (`to_tsvector`) path rather than
returning an error - a chunk without an embedding is still findable by
keyword, just not by semantic similarity, until the provider comes back
and the document is re-indexed.
"""
import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models as kb_models
from .embeddings import EmbeddingUnavailable, default_provider

logger = logging.getLogger(__name__)


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
        embedding = None
        try:
            embedding = default_provider.embed(text)
        except EmbeddingUnavailable:
            logger.warning("Embeddings provider unavailable; indexing chunk %s of document %s keyword-only", index, document.id)

        chunk = kb_models.KnowledgeChunk(
            tenant_id=document.tenant_id, document_id=document.id, chunk_index=index, content=text, embedding=embedding,
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


# nomic-embed-text cosine distances measured against this project's own
# fixtures: genuinely relevant pairs (paraphrased query vs. its chunk,
# or near-identical vocabulary) landed at 0.18-0.22; genuinely unrelated
# pairs landed at 0.60-0.72 - a wide, clean gap. 0.45 sits in the middle
# of that gap. Indicative, not a calibrated precision figure - same
# "shape now, real tuning later" caveat every other threshold table in
# this platform already carries (health.py, farm_score.py).
MAX_SEMANTIC_DISTANCE = 0.45


def _search_chunks_semantic(db: Session, *, query: str, limit: int) -> list[SearchHit]:
    query_embedding = default_provider.embed(query)
    distance = kb_models.KnowledgeChunk.embedding.cosine_distance(query_embedding)

    rows = (
        db.query(kb_models.KnowledgeChunk, kb_models.KnowledgeDocument, distance.label("distance"))
        .join(kb_models.KnowledgeDocument, kb_models.KnowledgeDocument.id == kb_models.KnowledgeChunk.document_id)
        .filter(kb_models.KnowledgeDocument.is_active.is_(True))
        .filter(kb_models.KnowledgeChunk.embedding.is_not(None))
        .filter(distance < MAX_SEMANTIC_DISTANCE)
        .order_by(distance)
        .limit(limit)
        .all()
    )
    # Cosine distance is in [0, 2]; convert to a similarity-style rank
    # (higher = better) so this path's SearchHit.rank is comparable in
    # shape to the full-text path's ts_rank, even though the two scores
    # aren't on the same scale.
    return [SearchHit(chunk=chunk, document=document, rank=1.0 - float(d)) for chunk, document, d in rows]


def _search_chunks_fulltext(db: Session, *, query: str, limit: int) -> list[SearchHit]:
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


def search_chunks(db: Session, *, tenant_id: str, query: str, limit: int = 5) -> list[SearchHit]:
    """Semantic (pgvector cosine similarity) search is primary; falls
    back to keyword full-text search when the embeddings provider is
    unreachable (`EmbeddingUnavailable`) or returns no vector hits
    (e.g. every chunk was indexed before embeddings existed) - never
    raises up to the caller for a provider outage, per this module's
    docstring."""
    try:
        hits = _search_chunks_semantic(db, query=query, limit=limit)
        if hits:
            return hits
    except EmbeddingUnavailable:
        logger.warning("Embeddings provider unavailable; falling back to full-text search for tenant %s", tenant_id)

    return _search_chunks_fulltext(db, query=query, limit=limit)
