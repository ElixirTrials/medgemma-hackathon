"""Remote Vertex adapter: uses existing ModelGardenChatModel."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from inference.adapters.base import BaseAdapter
from inference.config import AgentConfig

logger = logging.getLogger(__name__)


class VertexAdapter(BaseAdapter):
    """Adapter for Vertex AI Model Garden endpoints."""

    def __init__(self, config: AgentConfig | None = None) -> None:  # noqa: D107
        from inference.model_garden import create_model_loader

        self._config = config or AgentConfig.from_env()
        self._loader = create_model_loader(self._config)

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Vertex endpoints don't use file uploads; store locally."""
        from uuid import uuid4

        from inference.file_store import FileStore

        store = FileStore()
        file_id = str(uuid4())
        store.store(file_id, file_bytes, filename)
        return file_id

    async def generate(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
    ) -> str:
        """Generate via Vertex AI endpoint."""
        from langchain_core.messages import HumanMessage, SystemMessage

        model = self._loader()
        messages: list[Any] = [SystemMessage(content=system_prompt)]

        if file_id:
            from inference.file_store import FileStore

            store = FileStore()
            text_content = store.get_text(file_id)
            if text_content:
                input_text = f"Document content:\n{text_content}\n\n{input_text}"

        messages.append(HumanMessage(content=input_text))
        result = await model.ainvoke(messages)
        return str(result.content)

    async def generate_structured(
        self,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Generate structured output via Vertex AI."""
        from langchain_core.messages import HumanMessage, SystemMessage

        model = self._loader()
        structured = model.with_structured_output(output_schema)

        messages: list[Any] = [SystemMessage(content=system_prompt)]

        if file_id:
            from inference.file_store import FileStore

            store = FileStore()
            text_content = store.get_text(file_id)
            if text_content:
                input_text = f"Document content:\n{text_content}\n\n{input_text}"

        messages.append(HumanMessage(content=input_text))
        result = await structured.ainvoke(messages)

        if isinstance(result, output_schema):
            return result
        if isinstance(result, dict):
            return output_schema.model_validate(result)
        return result  # type: ignore[return-value]
