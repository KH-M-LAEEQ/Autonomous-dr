"""FROZEN INTERFACE 5 of 5 -- ExplanationEngine.

Implemented by: TemplateExplanationEngine (W5, always the fallback),
LLMExplanationEngine (W16, hosted Llama 3 via Groq).

Hard rule: explanation is NEVER on the critical path. If the LLM is down,
recovery still happens and the template fills in.
"""

from abc import ABC, abstractmethod

from core.models.domain import ExplanationContext


class ExplanationEngine(ABC):
    """Turns a decision into plain English a human can audit.

    Contract:
      * Must cite only `context.retrieved_documents`. Unsupported claims are
        hallucinations and are counted in the Week 16 audit.
      * Must return a usable string on failure, never raise.
      * Must complete or time out well inside the incident lifetime; it runs as a
        Celery task and the result is attached to the incident when ready.
    """

    name: str

    @abstractmethod
    async def explain(self, context: ExplanationContext) -> str:
        """Human-readable justification with inline source references."""
        ...
