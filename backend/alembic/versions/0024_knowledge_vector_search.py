"""Real semantic search for the Knowledge Base (Phase 28): enable the
`pgvector` extension and add a nullable `embedding` column to
`knowledge_chunks`, populated via Ollama's `nomic-embed-text` (768-dim) -
see `app/knowledge/embeddings.py`. Nullable because a chunk indexed while
the embeddings provider is unreachable still gets stored and stays
full-text searchable, per the fail-open design in
`app/knowledge/service.py`.

HNSW (not IVFFlat) chosen for the vector index since it needs no
training/list-count tuning to be effective at small-to-medium row counts,
which is what a pilot-scale Knowledge Base actually has.

Revision ID: 0024
Revises: 0023
Create Date: 2027-02-08 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("knowledge_chunks", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.drop_column("knowledge_chunks", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
