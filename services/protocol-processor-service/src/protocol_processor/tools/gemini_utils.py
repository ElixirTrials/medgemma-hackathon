"""Shared Gemini LLM utilities for protocol processor tools.

Centralizes the repeated pattern of creating a ChatGoogleGenerativeAI
client with structured output and parsing its response. Used by
structure_builder, ordinal_resolver, and field_mapper.

Falls back to Ollama when GOOGLE_API_KEY is not set but OLLAMA_BASE_URL
is configured.
"""

from __future__ import annotations

import logging
import os
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def create_structured_llm(
    output_schema: type[T],
) -> Any | None:
    """Create an LLM client with structured output.

    Tries Gemini first (GOOGLE_API_KEY), falls back to Ollama
    (OLLAMA_BASE_URL) if Gemini is not configured.

    Args:
        output_schema: Pydantic model class for structured output.

    Returns:
        A structured LLM instance, or None if no backend is available.
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
            gemini = ChatGoogleGenerativeAI(
                model=gemini_model_name,
                google_api_key=google_api_key,
                max_output_tokens=2048,
            )
            return gemini.with_structured_output(output_schema)
        except Exception as e:
            logger.warning("Failed to create Gemini client: %s", e)

    # Fallback to Ollama
    ollama_base_url = os.getenv("OLLAMA_BASE_URL")
    if ollama_base_url:
        try:
            from langchain_community.chat_models import ChatOllama

            ollama_model = os.getenv("OLLAMA_MODEL", "gemma2:9b")
            logger.info(
                "Using Ollama for structured output: %s/%s",
                ollama_base_url,
                ollama_model,
            )
            ollama = ChatOllama(
                base_url=ollama_base_url,
                model=ollama_model,
                format="json",
                temperature=0.1,
            )
            return ollama.with_structured_output(output_schema)
        except Exception as e:
            logger.warning("Failed to create Ollama client: %s", e)

    logger.warning("No LLM backend available — skipping structured output call")
    return None


def parse_structured_output(result: Any, model: type[T]) -> T:
    """Parse a structured LLM output into a Pydantic model.

    Handles both dict and already-parsed model instances returned
    by LangChain's with_structured_output().

    Args:
        result: Raw LLM output (dict or model instance).
        model: Pydantic model class to validate against.

    Returns:
        Validated model instance.
    """
    if isinstance(result, dict):
        return model.model_validate(result)
    return result  # type: ignore[no-any-return]
