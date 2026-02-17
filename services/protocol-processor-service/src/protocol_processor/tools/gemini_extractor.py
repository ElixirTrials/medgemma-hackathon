"""Gemini extractor tool: structured criteria extraction via Gemini File API.

Uploads PDF to Gemini File API, calls Gemini with structured output using
ExtractionResult as the response schema, and returns a JSON string.

Returns JSON string (not dict) to minimize LangGraph state size.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from google import genai
from google.genai import types
from inference.factory import render_prompts
from pydantic import ValidationError
from shared.resilience import gemini_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from protocol_processor.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Max length when formatting validation errors (avoids huge console dumps)
_VALIDATION_ERROR_STR_MAX = 200


def _truncate(s: str, max_len: int = _VALIDATION_ERROR_STR_MAX) -> str:
    """Truncate string for safe inclusion in error messages."""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _format_validation_error(err: ValidationError) -> str:
    """Format ValidationError with truncated input/context for safe logging."""
    errors = err.errors()
    parts = [f"ValidationError ({len(errors)} error(s))"]
    for e in errors:
        loc = ".".join(str(x) for x in e.get("loc", ()))
        msg = e.get("msg", "")
        ctx = e.get("ctx") or {}
        inp = e.get("input")
        part = f"  {loc}: {msg}"
        if ctx:
            part += f" (ctx: {_truncate(str(ctx))})"
        if inp is not None:
            part += f" | input: {_truncate(str(inp))}"
        parts.append(part)
    return "\n".join(parts)


@gemini_breaker
@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _invoke_gemini(
    client: genai.Client,
    model: str,
    uploaded_file: types.File,
    system_prompt: str,
    user_prompt: str,
) -> ExtractionResult:
    """Invoke Gemini with retry and circuit breaker.

    Args:
        client: Google GenAI client instance.
        model: Model name to use.
        uploaded_file: Uploaded PDF file from File API.
        system_prompt: System instruction.
        user_prompt: User prompt text.

    Returns:
        ExtractionResult parsed from Gemini's structured output.
    """
    response = await client.aio.models.generate_content(
        model=model,
        contents=cast(Any, [uploaded_file, user_prompt]),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=ExtractionResult,
        ),
    )

    # Return parsed Pydantic model directly
    if response.parsed is not None:
        return cast(ExtractionResult, response.parsed)

    # Fallback to parsing response.text if parsed is None
    text = response.text or ""
    return ExtractionResult.model_validate_json(text)


async def extract_criteria_structured(
    pdf_bytes: bytes,
    protocol_id: str,
    title: str,
) -> str:
    """Extract criteria from PDF using Gemini File API with structured output.

    Uploads the PDF to Gemini File API, calls Gemini with ExtractionResult
    as the response schema, and returns the result as a JSON string.

    Returns JSON string (not dict) to minimize LangGraph state size.

    Args:
        pdf_bytes: Raw PDF bytes to extract criteria from.
        protocol_id: UUID of the protocol (for logging).
        title: Protocol title (used in user prompt).

    Returns:
        JSON string representation of ExtractionResult.

    Raises:
        ValidationError: If Gemini response cannot be parsed as ExtractionResult.
        Exception: On Gemini API or File API errors after retries exhausted.
    """
    tmp_path = None
    uploaded_file = None
    client = None

    try:
        # Instantiate client
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        # Write PDF to temp file for File API upload
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # Upload via File API
        uploaded_file = client.files.upload(file=tmp_path)

        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={
                "title": title,
            },
        )

        extraction_result = await _invoke_gemini(
            client, model_name, uploaded_file, system_prompt, user_prompt
        )

        logger.info(
            "Extracted %d criteria from protocol %s (Gemini File API)",
            len(extraction_result.criteria),
            protocol_id,
        )

        # Return as JSON string (not dict) for minimal state
        return extraction_result.model_dump_json()

    except ValidationError as e:
        msg = _format_validation_error(e)
        logger.error(
            "Extraction validation failed for protocol %s: %s",
            protocol_id,
            msg,
        )
        raise

    except Exception:
        logger.exception(
            "Extraction failed for protocol %s",
            protocol_id,
        )
        raise

    finally:
        # Clean up temp file
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to delete temp file %s: %s", tmp_path, cleanup_err
                )

        # Clean up uploaded file
        if uploaded_file and client and uploaded_file.name:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to delete uploaded file %s: %s",
                    uploaded_file.name,
                    cleanup_err,
                )
