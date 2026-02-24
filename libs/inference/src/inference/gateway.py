"""Core inference gateway: unified entry point for all model interactions.

App code uses InferenceGateway, never provider SDKs directly.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from inference.file_store import FileStore
from inference.router import ModelRouter

logger = logging.getLogger(__name__)


class InferenceGateway:
    """Unified entry point for model inference.

    Routes requests to the appropriate adapter based on role.
    Manages file storage across all providers.
    """

    def __init__(  # noqa: D107
        self,
        router: ModelRouter | None = None,
        file_store: FileStore | None = None,
    ) -> None:
        self._router = router or ModelRouter()
        self._file_store = file_store or FileStore()

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Store file and return gateway file_id.

        The file is stored in the local file store. When an adapter
        needs to upload to a remote provider, it handles that internally.
        """
        from uuid import uuid4

        file_id = str(uuid4())
        self._file_store.store(file_id, file_bytes, filename)
        logger.info("Gateway stored file: %s (%s)", file_id, filename)
        return file_id

    async def generate(
        self,
        role: str,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
    ) -> str:
        """Route text generation to appropriate adapter by role."""
        adapter = self._router.get_adapter(role)

        # For remote adapters that need their own file upload
        adapter_file_id = None
        if file_id:
            file_bytes = self._file_store.get(file_id)
            if file_bytes:
                adapter_file_id = await adapter.upload_file(
                    file_bytes, f"{file_id}.pdf"
                )

        return await adapter.generate(adapter_file_id, input_text, system_prompt)

    async def generate_structured(
        self,
        role: str,
        file_id: str | None,
        input_text: str,
        system_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        """Route structured generation to appropriate adapter by role."""
        adapter = self._router.get_adapter(role)

        adapter_file_id = None
        if file_id:
            file_bytes = self._file_store.get(file_id)
            if file_bytes:
                adapter_file_id = await adapter.upload_file(
                    file_bytes, f"{file_id}.pdf"
                )

        return await adapter.generate_structured(
            adapter_file_id, input_text, system_prompt, output_schema
        )

    def cleanup(self, file_id: str) -> None:
        """Clean up stored file."""
        self._file_store.delete(file_id)
