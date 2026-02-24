"""Base adapter ABC for provider-agnostic inference."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class BaseAdapter(ABC):
    """Provider-agnostic inference adapter."""

    @abstractmethod
    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Upload file, return file_id.

        Remote adapters use provider File API.
        Local adapters store to disk and return local file_id.
        """

    @abstractmethod
    async def generate(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
    ) -> str:
        """Generate text response.

        For remote: passes provider file_id in request.
        For local: retrieves stored file, extracts text, feeds to LLM.
        """

    @abstractmethod
    async def generate_structured(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Generate structured output.

        Remote: native structured output.
        Local: JSON mode + Pydantic validation.
        """
