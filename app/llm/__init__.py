"""LLM Provider factory for Company Brain."""

from app.config import get_settings
from app.llm.base import BaseLLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.retrieval_only import RetrievalOnlyProvider


def get_llm_provider() -> BaseLLMProvider:
    """Return configured LLM provider or fallback based on environment configuration."""
    settings = get_settings()

    if settings.LLM_PROVIDER == "retrieval_only":
        return RetrievalOnlyProvider()

    if settings.LLM_PROVIDER == "gemini":
        if settings.GEMINI_API_KEY:
            return GeminiProvider(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
        return RetrievalOnlyProvider()

    # "auto" mode: use Gemini if API key is present, else retrieval_only
    if settings.GEMINI_API_KEY:
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
    return RetrievalOnlyProvider()
