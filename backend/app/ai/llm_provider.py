"""LLM provider abstraction (AI-003, ADR-011) - "shape now, real
integration later", same treatment as `weather.provider.WeatherProvider`
and Phase 9's `VisionInferenceEngine`. No Ollama/OpenAI-compatible
endpoint is wired yet (no deployment target decided for this pilot); the
interface is what ADR-011 requires so Copilot's business logic never
hardcodes a provider SDK, and a real provider drops in later without
touching `copilot.py`.
"""
from typing import Protocol


class LLMProvider(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        ...


class StubLLMProvider:
    """Deterministic, no-network stand-in. Copilot's grounding logic
    (`copilot.py::answer_question`) does not actually call this for its
    answers - it answers directly from real queried data so the "answers
    only from real platform data" contract holds even without a live LLM.
    This class exists so callers depend on `LLMProvider`, not a concrete
    absence of one, and so a future free-text-composition step (turning
    the grounded facts into more natural prose) has a seam to plug into."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return user_prompt
