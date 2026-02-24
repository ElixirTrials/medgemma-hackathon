"""Model router: maps logical model names to provider adapters based on config."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from inference.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


@dataclass
class AdapterConfig:
    """Configuration for a single adapter mapping."""

    provider: str  # "gemini", "vertex", "ollama"
    model: str | None = None
    base_url: str | None = None


class ModelRouter:
    """Routes logical model names to adapters based on config."""

    def __init__(  # noqa: D107
        self, config: dict[str, AdapterConfig] | None = None
    ) -> None:
        self._config = config or self._default_config()
        self._adapters: dict[str, BaseAdapter] = {}

    @staticmethod
    def _default_config() -> dict[str, AdapterConfig]:
        """Build default config from environment variables."""
        backend = os.getenv("MODEL_BACKEND", "gemini").lower()

        if backend == "ollama":
            return {
                "extraction": AdapterConfig(
                    provider="ollama",
                    model=os.getenv("OLLAMA_EXTRACTION_MODEL", "qwen2.5:14b"),
                ),
                "grounding": AdapterConfig(
                    provider="ollama",
                    model=os.getenv("OLLAMA_MODEL", "gemma2:9b"),
                ),
                "structuring": AdapterConfig(
                    provider="ollama",
                    model=os.getenv("OLLAMA_MODEL", "gemma2:9b"),
                ),
            }
        elif backend == "vertex":
            return {
                "extraction": AdapterConfig(provider="vertex"),
                "grounding": AdapterConfig(provider="vertex"),
                "structuring": AdapterConfig(provider="vertex"),
            }
        else:
            # Default: gemini for extraction, gemini for structuring
            return {
                "extraction": AdapterConfig(provider="gemini"),
                "grounding": AdapterConfig(provider="gemini"),
                "structuring": AdapterConfig(provider="gemini"),
            }

    def _create_adapter(self, cfg: AdapterConfig) -> BaseAdapter:
        """Create adapter instance from config."""
        if cfg.provider == "ollama":
            from inference.adapters.ollama_adapter import OllamaAdapter

            return OllamaAdapter(
                base_url=cfg.base_url,
                model=cfg.model,
            )
        elif cfg.provider == "vertex":
            from inference.adapters.vertex_adapter import VertexAdapter

            return VertexAdapter()
        else:
            from inference.adapters.gemini_adapter import GeminiAdapter

            return GeminiAdapter(model_name=cfg.model)

    def get_adapter(self, role: str) -> BaseAdapter:
        """Get adapter for a logical role."""
        if role not in self._adapters:
            if role not in self._config:
                raise ValueError(
                    f"No adapter configured for role '{role}'. "
                    f"Available: {list(self._config.keys())}"
                )
            self._adapters[role] = self._create_adapter(self._config[role])
        return self._adapters[role]
