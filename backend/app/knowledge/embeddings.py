"""Embeddings provider (Phase 28) - ADR-011's provider-abstraction
principle applied to embeddings, not just chat: one internal interface,
Ollama (local) as the default, so a future OpenAI-compatible embeddings
provider drops in later without touching `service.py`'s call sites.

Unlike `ai/llm_provider.py` (still stub-only - no LLM deployment target
chosen), this one is real: the user confirmed Ollama is available and it
now runs as a docker-compose service (`ollama`), so
`OllamaEmbeddingProvider` makes a real HTTP call rather than being a
placeholder.

Fails open the same way `core/rate_limit.py` does when Redis is
unreachable (NFR-004): if Ollama is down, embedding generation raises
`EmbeddingUnavailable` rather than crashing the caller - `service.py`
catches it and falls back to keyword-only search rather than the whole
document-indexing or search request failing.
"""
from typing import Protocol

import httpx

from ..config import settings

EMBEDDING_DIM = 768  # nomic-embed-text's output dimension


class EmbeddingUnavailable(Exception):
    """Raised when the embeddings provider can't be reached or errors -
    callers fall back to keyword-only search rather than propagating a
    500, per NFR-004's "degrade gracefully" principle applied here too."""


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        ...


class OllamaEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        try:
            response = httpx.post(
                f"{settings.ollama_url}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable(str(exc)) from exc

        embedding = response.json().get("embedding")
        if not embedding:
            raise EmbeddingUnavailable("Ollama returned no embedding")
        return embedding


default_provider: EmbeddingProvider = OllamaEmbeddingProvider()
