"""Local file store for the inference gateway."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_STORE_DIR = Path(tempfile.gettempdir()) / "inference_file_store"


class FileStore:
    """Simple local file store for PDF and text content.

    Stores files on disk keyed by file_id. Provides both raw bytes
    and extracted text retrieval.
    """

    def __init__(self, base_dir: Path | None = None) -> None:  # noqa: D107
        self._base_dir = base_dir or _STORE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, file_id: str, data: bytes, filename: str) -> Path:
        """Store file bytes and return the path."""
        file_path = self._base_dir / f"{file_id}_{filename}"
        file_path.write_bytes(data)
        return file_path

    def get(self, file_id: str) -> bytes | None:
        """Retrieve file bytes by file_id prefix."""
        for path in self._base_dir.iterdir():
            if path.name.startswith(file_id):
                return path.read_bytes()
        return None

    def get_text(self, file_id: str) -> str | None:
        """Retrieve file and extract text (PDF -> markdown)."""
        file_bytes = self.get(file_id)
        if file_bytes is None:
            return None

        try:
            import pymupdf4llm

            return pymupdf4llm.to_markdown(file_bytes)
        except (ImportError, Exception):
            try:
                import pymupdf

                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
                pages = [doc[i] for i in range(len(doc))]
                return "\n\n".join(
                    p.get_text()  # type: ignore[attr-defined]
                    for p in pages
                )
            except Exception as e:
                logger.warning("Failed to extract text from file %s: %s", file_id, e)
                return file_bytes.decode("utf-8", errors="replace")

    def delete(self, file_id: str) -> None:
        """Delete stored file."""
        for path in self._base_dir.iterdir():
            if path.name.startswith(file_id):
                path.unlink(missing_ok=True)
