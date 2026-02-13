"""Extract node: call Gemini with structured output for criteria extraction.

This node invokes google.genai.Client with File API upload for PDF handling
using Jinja2-rendered system and user prompts. The output is a list of
criteria dicts ready for post-processing by the parse node.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

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

from extraction_service.schemas.criteria import ExtractionResult
from extraction_service.state import ExtractionState

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
        ExtractionResult from Gemini.
    """
    response = await client.aio.models.generate_content(
        model=model,
        contents=[uploaded_file, user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=ExtractionResult,
        ),
    )

    # Return parsed Pydantic model directly
    if response.parsed is not None:
        return response.parsed

    # Fallback to parsing response.text if parsed is None
    return ExtractionResult.model_validate_json(response.text)


async def extract_node(state: ExtractionState) -> dict[str, Any]:
    """Extract structured criteria from PDF using Gemini File API.

    Args:
        state: Current extraction state with pdf_bytes and title.

    Returns:
        Dict with raw_criteria list of dicts, or error dict on failure.
    """
    if state.get("error"):
        return {}

    tmp_path = None
    uploaded_file = None
    client = None

    try:
        # Instantiate client
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        # Write PDF to temp file for File API upload
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(state["pdf_bytes"])
            tmp_path = tmp.name

        # Upload via File API
        uploaded_file = client.files.upload(file=tmp_path)

        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={
                "title": state["title"],
            },
        )

        extraction_result = await _invoke_gemini(
            client, model_name, uploaded_file, system_prompt, user_prompt
        )
        criteria_dicts = [c.model_dump() for c in extraction_result.criteria]

        logger.info(
            "Extracted %d criteria from protocol %s (Gemini File API)",
            len(criteria_dicts),
            state["protocol_id"],
        )
        return {"raw_criteria": criteria_dicts}

    except ValidationError as e:
        msg = _format_validation_error(e)
        logger.error(
            "Extraction validation failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            msg,
        )
        return {"error": f"Extraction failed (validation): {msg}"}
    except Exception as e:
        logger.exception(
            "Extraction failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Extraction failed: {e}"}
    finally:
        # Clean up temp file
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.warning("Failed to delete temp file %s: %s", tmp_path, cleanup_err)

        # Clean up uploaded file
        if uploaded_file and client:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as cleanup_err:
                logger.warning("Failed to delete uploaded file %s: %s", uploaded_file.name, cleanup_err)
