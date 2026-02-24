"""Remote Gemini adapter: maps file_id to Gemini File API, uses google-genai SDK."""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from pydantic import BaseModel

from inference.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini API (remote)."""

    def __init__(  # noqa: D107
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self._model_name = model_name or os.getenv(
            "GEMINI_MODEL_NAME", "gemini-2.5-flash"
        )
        self._file_map: dict[str, str] = {}  # gateway_file_id -> gemini_file_name

    def _get_client(self) -> Any:
        from google import genai

        return genai.Client(api_key=self._api_key)

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Upload to Gemini File API, return gateway file_id."""
        import tempfile
        from uuid import uuid4

        client = self._get_client()
        with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            uploaded = client.files.upload(file=tmp_path)
            gateway_id = str(uuid4())
            self._file_map[gateway_id] = uploaded.name
            logger.info("Uploaded file to Gemini: %s -> %s", gateway_id, uploaded.name)
            return gateway_id
        finally:
            import os as _os

            try:
                _os.unlink(tmp_path)
            except OSError:
                pass

    async def generate(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
    ) -> str:
        """Generate text via Gemini API."""
        from google.genai import types

        client = self._get_client()
        contents: list[Any] = []

        if file_id and file_id in self._file_map:
            gemini_name = self._file_map[file_id]
            gemini_file = client.files.get(name=gemini_name)
            contents.append(gemini_file)

        contents.append(input_text)

        response = await client.aio.models.generate_content(
            model=self._model_name,
            contents=cast(Any, contents),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return response.text or ""

    async def generate_structured(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Generate structured output via Gemini API."""
        from google.genai import types

        client = self._get_client()
        contents: list[Any] = []

        if file_id and file_id in self._file_map:
            gemini_name = self._file_map[file_id]
            gemini_file = client.files.get(name=gemini_name)
            contents.append(gemini_file)

        contents.append(input_text)

        response = await client.aio.models.generate_content(
            model=self._model_name,
            contents=cast(Any, contents),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=output_schema,
            ),
        )

        if response.parsed is not None:
            return cast(BaseModel, response.parsed)

        text = response.text or ""
        return output_schema.model_validate_json(text)

    def cleanup_file(self, file_id: str) -> None:
        """Delete uploaded file from Gemini File API."""
        if file_id in self._file_map:
            try:
                client = self._get_client()
                client.files.delete(name=self._file_map[file_id])
            except Exception as e:
                logger.warning("Failed to cleanup Gemini file %s: %s", file_id, e)
            finally:
                del self._file_map[file_id]
