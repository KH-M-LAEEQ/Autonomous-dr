"""FROZEN INTERFACE 5 of 5 -- ExplanationEngine.

Implemented by: TemplateExplanationEngine (W5, always the fallback),
LLMExplanationEngine (W16, hosted Llama 3 via Groq).

Hard rule: explanation is NEVER on the critical path. If the LLM is down,
recovery still happens and the template fills in.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from core.models.domain import ExplanationContext


@dataclass
class Explanation:
    """Structured result of `ExplanationEngine.explain`.

    A bare string can't be checked against `context.retrieved_documents` or
    rendered as expandable citations in the UI -- this can (ADR-0009).
    """

    text: str
    citations: list[UUID]  # corpus_chunk ids from context.retrieved_documents actually cited
    engine: str  # "llm" | "template"
    unsupported: list[str] = field(default_factory=list)  # claims in `text` not backed by citations


class ExplanationEngine(ABC):
    """Turns a decision into plain English a human can audit.

    Contract:
      * Must cite only `context.retrieved_documents`. Every claim in `text` not
        traceable to a retrieved document belongs in `unsupported`, not silently
        dropped -- that list is the Week 16 hallucination audit.
      * Must return a usable Explanation on failure, never raise.
      * Must complete or time out well inside the incident lifetime; it runs as
        a Celery task (ADR-0006) and the result is attached to the incident
        when ready. Synchronous by design: this was the only async method
        across the five frozen interfaces, and its one production caller is
        sync by default. An LLM-backed implementation that needs an async
        client bridges internally (e.g. `asyncio.run`) rather than pushing
        async through the interface.
    """

    name: str

    @abstractmethod
    def explain(self, context: ExplanationContext) -> Explanation:
        """Human-readable justification with inline source references."""
        ...
