"""Gemini extractor tool: structured criteria extraction via Gemini File API.

Uploads PDF to Gemini File API, calls Gemini with structured output using
ExtractionResult as the response schema, and returns a JSON string.

Returns JSON string (not dict) to minimize LangGraph state size.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, cast

from google import genai
from google.genai import types
from pydantic import ValidationError
from shared.resilience import gemini_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from protocol_processor.prompts import render_template
from protocol_processor.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)

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
    pdf_content: Any,
    system_prompt: str,
    user_prompt: str,
) -> ExtractionResult:
    """Invoke Gemini with retry and circuit breaker.

    Args:
        client: Google GenAI client instance.
        model: Model name to use.
        pdf_content: PDF as File (Developer API) or Part (Vertex AI inline bytes).
        system_prompt: System instruction.
        user_prompt: User prompt text.

    Returns:
        ExtractionResult parsed from Gemini's structured output.
    """
    from protocol_processor.tracing import llm_span

    with llm_span("gemini_extraction", model) as llm:
        llm.set_request(f"[system] {system_prompt}\n\n[user] {user_prompt}")

        response = await client.aio.models.generate_content(
            model=model,
            contents=cast(Any, [pdf_content, user_prompt]),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
            ),
        )

        resp_text = response.text or ""
        usage: dict[str, int] = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            if hasattr(um, "prompt_token_count") and um.prompt_token_count:
                usage["input_tokens"] = um.prompt_token_count
            if hasattr(um, "candidates_token_count") and um.candidates_token_count:
                usage["output_tokens"] = um.candidates_token_count
            if hasattr(um, "total_token_count") and um.total_token_count:
                usage["total_tokens"] = um.total_token_count
        llm.set_response(resp_text, usage or None)

    # Return parsed Pydantic model directly
    if response.parsed is not None:
        return cast(ExtractionResult, response.parsed)

    # Fallback to parsing response.text if parsed is None
    text = response.text or ""
    return ExtractionResult.model_validate_json(text)


async def _extract_via_gateway(
    pdf_bytes: bytes,
    protocol_id: str,
    title: str,
) -> str:
    """Extract criteria using the unified InferenceGateway (local/Ollama path).

    Used when LOCAL_EXTRACTION_ENABLED=true. Routes through InferenceGateway
    instead of direct google.genai.Client.
    """
    from inference.gateway import InferenceGateway

    gateway = InferenceGateway()

    system_prompt = render_template("system.jinja2", title=title)
    user_prompt = render_template("user.jinja2", title=title)

    file_id = await gateway.upload_file(pdf_bytes, f"{protocol_id}.pdf")
    try:
        result = await gateway.generate_structured(
            role="extraction",
            file_id=file_id,
            input_text=user_prompt,
            system_prompt=system_prompt,
            output_schema=ExtractionResult,
        )
        extraction_result = (
            result
            if isinstance(result, ExtractionResult)
            else ExtractionResult.model_validate(result.model_dump())
        )
        logger.info(
            "Extracted %d criteria from protocol %s (gateway)",
            len(extraction_result.criteria),
            protocol_id,
        )
        return extraction_result.model_dump_json()
    finally:
        gateway.cleanup(file_id)


async def extract_criteria_structured(
    pdf_bytes: bytes,
    protocol_id: str,
    title: str,
) -> str:
    """Extract criteria from PDF using Gemini File API with structured output.

    Uploads the PDF to Gemini File API, calls Gemini with ExtractionResult
    as the response schema, and returns the result as a JSON string.

    When LOCAL_EXTRACTION_ENABLED=true, routes through InferenceGateway
    instead of direct google.genai.Client.

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
    # Route through gateway when local extraction is enabled
    if os.getenv("LOCAL_EXTRACTION_ENABLED", "").lower() == "true":
        return await _extract_via_gateway(pdf_bytes, protocol_id, title)

    tmp_path = None
    uploaded_file = None
    client = None

    try:
        # Instantiate client — prefer API key, fall back to Vertex AI ADC
        api_key = os.getenv("GOOGLE_API_KEY")
        use_vertex = not api_key
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client(
                vertexai=True,
                project=os.getenv("GCP_PROJECT_ID"),
                location=os.getenv("GCP_REGION", "europe-west4"),
            )
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        if use_vertex:
            # Vertex AI: File API not available, pass PDF bytes inline
            pdf_content = types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            )
        else:
            # Developer API: upload via File API (supports larger files)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            uploaded_file = client.files.upload(file=tmp_path)
            pdf_content = uploaded_file

        system_prompt = render_template("system.jinja2", title=title)
        user_prompt = render_template("user.jinja2", title=title)

        extraction_result = await _invoke_gemini(
            client, model_name, pdf_content, system_prompt, user_prompt
        )

        logger.info(
            "Extracted %d criteria from protocol %s (%s)",
            len(extraction_result.criteria),
            protocol_id,
            "Vertex AI inline" if use_vertex else "Gemini File API",
        )

        # Return as JSON string (not dict) for minimal state
        json_str: str = extraction_result.model_dump_json()
        return json_str

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
        # Clean up temp file (Developer API path only)
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to delete temp file %s: %s", tmp_path, cleanup_err
                )

        # Clean up uploaded file (Developer API path only)
        if uploaded_file and client and uploaded_file.name:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to delete uploaded file %s: %s",
                    uploaded_file.name,
                    cleanup_err,
                )
