"""Shared Gemini LLM utilities for protocol processor tools.

Centralizes the repeated pattern of creating a ChatGoogleGenerativeAI
client with structured output and parsing its response. Used by
structure_builder, ordinal_resolver, and field_mapper.

Falls back to Ollama when GOOGLE_API_KEY is not set but OLLAMA_BASE_URL
is configured.

Includes detection for a known Gemini structured-output bug where the
model enters a token repetition loop, producing repeating digits or
regurgitated schema descriptions instead of actual values.  See:
  - https://github.com/google-gemini/cookbook/issues/449
  - https://github.com/googleapis/python-genai/issues/1039
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Pattern that detects schema description regurgitation — the model
# outputs Pydantic field descriptions or chain-of-thought reasoning
# instead of actual values.
_SCHEMA_LEAK_RE = re.compile(
    r"(?:"
    r"Unit of measurement"
    r"|Value for standard type"
    r"|Duration value for"
    r"|measurement unit"
    r"|provided schema"
    r"|In the context of"
    r"|populate the .+ field"
    r"|will populate"
    r")",
    re.IGNORECASE,
)


def is_repetition_loop(text: str | None) -> bool:
    """Detect if text contains a Gemini repetition loop.

    Known Gemini bug: the model enters a token repetition loop during
    structured output generation, producing sequences like
    ``"220220220220220220"`` or ``"8598739459392231e-315"`` repeated
    until ``max_output_tokens`` is exhausted.

    Returns True if the text is likely a repetition artifact.
    """
    if not text or len(text) < 20:
        return False

    # Check 1: very low character diversity for the string length
    unique_ratio = len(set(text)) / len(text)
    if unique_ratio < 0.08 and len(text) > 30:
        return True

    # Check 2: repeating substring (3-30 chars repeated 3+ times)
    # Tries from position 0 first, then from later offsets to catch
    # repetition that starts after a short prefix.
    max_plen = min(31, len(text) // 3 + 1)
    for start in range(0, min(20, len(text) // 2)):
        remaining = text[start:]
        if len(remaining) < 9:
            break
        for plen in range(3, min(max_plen, len(remaining) // 3 + 1)):
            pattern = remaining[:plen]
            count = 0
            for i in range(0, len(remaining) - plen + 1, plen):
                if remaining[i : i + plen] == pattern:
                    count += 1
                else:
                    break
            if count >= 3 and count * plen >= len(remaining) * 0.7:
                return True

    # Check 3: schema description regurgitation
    if _SCHEMA_LEAK_RE.search(text):
        return True

    return False


class RepetitionLoopError(RuntimeError):
    """Raised when a Gemini structured-output response contains repetition artifacts."""


def check_model_for_repetition(model: BaseModel) -> list[str]:
    """Recursively inspect all string fields of a Pydantic model for repetition.

    Returns a list of field paths that contain repetition artifacts,
    e.g. ["mappings[0].value.unit", "mappings[1].value.value"].
    """
    bad_fields: list[str] = []

    def _check(obj: Any, prefix: str) -> None:
        if isinstance(obj, BaseModel):
            for field_name in obj.model_fields:
                _check(getattr(obj, field_name, None), f"{prefix}.{field_name}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check(item, f"{prefix}[{i}]")
        elif isinstance(obj, str) and is_repetition_loop(obj):
            bad_fields.append(prefix)

    _check(model, "root")
    return bad_fields


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
    gcp_project = os.getenv("GCP_PROJECT_ID")
    if google_api_key or gcp_project:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
            kwargs: dict[str, Any] = {
                "model": gemini_model_name,
                "max_output_tokens": 2048,
                "temperature": 0.1,
                "model_kwargs": {
                    "frequency_penalty": 0.8,
                    "presence_penalty": 0.5,
                },
            }
            if google_api_key:
                kwargs["google_api_key"] = google_api_key
            else:
                # Vertex AI mode — uses Application Default Credentials
                kwargs["project"] = gcp_project
                kwargs["location"] = os.getenv("GCP_REGION", "europe-west4")
                kwargs["vertexai"] = True
            gemini = ChatGoogleGenerativeAI(**kwargs)
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
