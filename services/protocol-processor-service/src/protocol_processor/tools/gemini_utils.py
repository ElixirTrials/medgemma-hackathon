"""Shared Gemini LLM utilities for protocol processor tools.

Centralizes the repeated pattern of creating a ChatGoogleGenerativeAI
client with structured output and parsing its response. Used by
structure_builder, ordinal_resolver, and field_mapper.
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
    """Create a Gemini LLM client with structured output.

    Guards on GOOGLE_API_KEY. Uses late import of ChatGoogleGenerativeAI
    to avoid import errors when the package is not installed.

    Args:
        output_schema: Pydantic model class for structured output.

    Returns:
        A structured LLM instance, or None if GOOGLE_API_KEY is not set
        or client creation fails.
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.warning("GOOGLE_API_KEY not set — skipping Gemini call")
        return None

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        gemini = ChatGoogleGenerativeAI(
            model=gemini_model_name,
            google_api_key=google_api_key,
        )
        return gemini.with_structured_output(output_schema)
    except Exception as e:
        logger.warning("Failed to create Gemini client: %s", e)
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
    return result  # type: ignore[return-value]
