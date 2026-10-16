"""Abstract base interface for LLM answer generation providers."""

from abc import ABC, abstractmethod
from typing import List, Tuple
from app.models import SearchResultItem


class BaseLLMProvider(ABC):
    """Abstract interface for grounded answer synthesis."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier string."""
        pass

    @abstractmethod
    async def generate_answer(
        self,
        question: str,
        sources: List[SearchResultItem],
    ) -> Tuple[str, str]:
        """
        Generate an answer strictly grounded in the provided sources.

        Returns:
            Tuple[answer_text, confidence_level]
            confidence_level: 'grounded' | 'insufficient_evidence'
        """
        pass
