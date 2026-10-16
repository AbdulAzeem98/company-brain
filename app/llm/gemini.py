"""Gemini LLM Provider using Google GenAI SDK with grounded prompt engineering."""

import logging
from typing import List, Optional, Tuple
from google import genai
from google.genai import types

from app.config import get_settings
from app.llm.base import BaseLLMProvider
from app.llm.retrieval_only import RetrievalOnlyProvider
from app.models import SearchResultItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Company Brain, the enterprise AI knowledge assistant for Nexora Technologies.
Your sole mission is to provide accurate, grounded answers to employees based EXCLUSIVELY on the provided document excerpts.

STRICT GROUNDING RULES:
1. Grounding Guarantee: Rely ONLY on facts stated in the provided excerpts. Never make assumptions, invent numbers, policies, or extrapolate beyond the provided text.
2. Insufficient Evidence: If the provided excerpts do not contain sufficient verified facts to answer the question, you MUST explicitly state: "Based on the available internal documentation, there is insufficient evidence to answer this question." Do not attempt to guess.
3. Citations: Explicitly cite document IDs (e.g., `[NEX-HR-001]`) for every factual claim.
4. Tone: Professional, direct, concise, and objective.
5. Synthetic Notice: Remember that all information pertains to the synthetic company Nexora Technologies.
"""


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider supporting strictly grounded answers and uncertainty admission."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._fallback_provider = RetrievalOnlyProvider()

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    @property
    def name(self) -> str:
        return "gemini"

    async def generate_answer(
        self,
        question: str,
        sources: List[SearchResultItem],
    ) -> Tuple[str, str]:
        """Generate answer via Gemini or fall back to retrieval-only if unconfigured/failed."""
        if not self.client:
            logger.warning("Gemini API key not configured; falling back to retrieval-only mode.")
            return await self._fallback_provider.generate_answer(question, sources)

        if not sources:
            return (
                "Based on the company documentation accessible to your role, "
                "no verified information was found to answer this question. "
                "The available documents do not contain evidence for this topic.",
                "insufficient_evidence",
            )

        # Build context block
        context_parts = []
        for i, s in enumerate(sources, 1):
            heading = f" > {s.heading}" if s.heading else ""
            context_parts.append(
                f"--- SOURCE {i} ---\n"
                f"Document ID: {s.document_id}\n"
                f"Title: {s.title} ({s.category}){heading}\n"
                f"Classification: {s.access_classification}\n"
                f"Excerpt:\n{s.excerpt}\n"
            )
        context_str = "\n".join(context_parts)

        prompt = (
            f"Question:\n{question}\n\n"
            f"Retrieved Company Documents Context:\n{context_str}\n\n"
            f"Please provide a grounded answer following your strict instructions."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,  # Low temperature for strict factual grounding
                    max_output_tokens=800,
                ),
            )
            answer_text = response.text or ""

            # Detect if model declared insufficient evidence
            lowered = answer_text.lower()
            if "insufficient evidence" in lowered or "does not contain" in lowered and "information" in lowered:
                confidence = "insufficient_evidence"
            else:
                confidence = "grounded"

            return answer_text, confidence

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}. Falling back to retrieval-only provider.")
            fallback_answer, _ = await self._fallback_provider.generate_answer(question, sources)
            return (
                f"{fallback_answer}\n\n*(Note: Gemini generation failed due to: {type(e).__name__}; displayed extractive retrieval)*",
                "grounded" if sources else "insufficient_evidence",
            )
