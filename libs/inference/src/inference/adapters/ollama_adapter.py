"""Local Ollama adapter: stores PDFs locally, extracts text, feeds to Ollama."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel

from inference.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """Adapter for local Ollama inference."""

    def __init__(  # noqa: D107
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self._model = model or os.getenv("OLLAMA_MODEL", "gemma2:9b")

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Store PDF locally and return file_id."""
        from uuid import uuid4

        from inference.file_store import FileStore

        store = FileStore()
        file_id = str(uuid4())
        store.store(file_id, file_bytes, filename)
        logger.info("Stored file locally: %s (%s)", file_id, filename)
        return file_id

    def _extract_text(self, file_id: str) -> str:
        """Extract text from stored PDF via pymupdf4llm."""
        from inference.file_store import FileStore

        store = FileStore()
        file_bytes = store.get(file_id)
        if file_bytes is None:
            raise FileNotFoundError(f"File {file_id} not found in store")

        try:
            import pymupdf4llm

            return pymupdf4llm.to_markdown(file_bytes)
        except ImportError:
            import pymupdf

            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            pages = [doc[i] for i in range(len(doc))]
            return "\n\n".join(
                p.get_text()  # type: ignore[attr-defined]
                for p in pages
            )

    async def _call_ollama(
        self,
        prompt: str,
        system_prompt: str,
        json_mode: bool = False,
    ) -> str:
        """Call Ollama chat API."""
        import httpx

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def generate(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
    ) -> str:
        """Generate text via Ollama."""
        prompt = input_text
        if file_id:
            text_content = self._extract_text(file_id)
            prompt = f"Document content:\n{text_content}\n\n{input_text}"

        return await self._call_ollama(prompt, system_prompt)

    async def generate_structured(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Generate structured output via Ollama JSON mode + Pydantic validation."""
        prompt = input_text
        if file_id:
            text_content = self._extract_text(file_id)
            prompt = f"Document content:\n{text_content}\n\n{input_text}"

        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        structured_prompt = (
            f"{prompt}\n\nRespond with valid JSON matching this schema:\n{schema_json}"
        )

        result = await self._call_ollama(
            structured_prompt, system_prompt, json_mode=True
        )
        return output_schema.model_validate_json(result)
