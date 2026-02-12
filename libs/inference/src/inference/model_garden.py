"""Vertex AI Model Garden integration for MedGemma.

Provides ModelGardenChatModel (a LangChain BaseChatModel wrapper for
Vertex AI Model Garden endpoints) and a factory function for creating
lazy model loaders.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from shared.lazy_cache import lazy_singleton
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from inference.config import AgentConfig

logger = logging.getLogger(__name__)


def _build_gemma_prompt(messages: list[Any]) -> str:
    """Build Gemma chat template prompt from messages.

    Args:
        messages: List of LangChain messages.

    Returns:
        Formatted prompt string.
    """
    prompt_parts = []
    for msg in messages:
        role = "user"
        if msg.type == "ai":
            role = "model"

        content = msg.content
        if not isinstance(content, str):
            content = str(content)

        if role == "user":
            content = f"### Instruction:\n{content}"

        prompt_parts.append(f"<start_of_turn>{role}\n{content}<end_of_turn>")

    return "\n".join(prompt_parts) + "\n<start_of_turn>model\n"


def _is_retryable_error(exception: BaseException) -> bool:
    """Check if an exception is retryable (transient error).

    Args:
        exception: The exception to check.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    # Retry on network/connection errors
    if isinstance(
        exception,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True

    # Retry on Google API transient server errors
    try:
        from google.api_core import exceptions as google_exceptions

        if isinstance(
            exception,
            (
                google_exceptions.ServiceUnavailable,
                google_exceptions.InternalServerError,
                google_exceptions.DeadlineExceeded,
                google_exceptions.ResourceExhausted,
            ),
        ):
            return True

        # Do NOT retry on client errors
        if isinstance(
            exception,
            (
                google_exceptions.PermissionDenied,
                google_exceptions.Unauthenticated,
                google_exceptions.InvalidArgument,
                google_exceptions.NotFound,
                google_exceptions.AlreadyExists,
                google_exceptions.FailedPrecondition,
                google_exceptions.OutOfRange,
            ),
        ):
            return False
    except ImportError:
        pass

    return False


@retry(
    retry=retry_if_exception(_is_retryable_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _predict_with_retry(
    endpoint: Any, instances: list[dict[str, Any]], parameters: dict[str, Any]
) -> Any:
    """Call Vertex AI endpoint.predict with retry on transient errors.

    Args:
        endpoint: Vertex AI Endpoint object.
        instances: List of prediction instances.
        parameters: Prediction parameters.

    Returns:
        Prediction response from the endpoint.
    """
    return endpoint.predict(instances=instances, parameters=parameters)


class ModelGardenChatModel(BaseChatModel):
    """LangChain ChatModel wrapper for Vertex AI Model Garden endpoints.

    Wraps a Vertex AI endpoint that serves MedGemma (or other Gemma-family
    models) using the Gemma chat template for prompt formatting and
    exponential-backoff retry for transient errors.
    """

    endpoint_resource_name: str
    project: str
    location: str
    max_output_tokens: int = Field(default=512)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a chat response from the Model Garden endpoint.

        Args:
            messages: List of LangChain messages.
            stop: Optional stop sequences (unused by Model Garden).
            run_manager: Optional callback manager.
            **kwargs: Additional keyword arguments (e.g. temperature).

        Returns:
            ChatResult containing the model's response.
        """
        from google.cloud import aiplatform

        endpoint = aiplatform.Endpoint(self.endpoint_resource_name)

        full_prompt = _build_gemma_prompt(messages)

        instance = {
            "prompt": full_prompt,
            "max_tokens": self.max_output_tokens,
            "temperature": kwargs.get("temperature", 0.1),
            "top_p": 0.95,
            "top_k": 40,
        }
        parameters = {
            "max_output_tokens": self.max_output_tokens,
            "temperature": kwargs.get("temperature", 0.1),
        }

        start_time = time.time()
        try:
            logger.debug(
                "Calling Vertex AI endpoint.predict for endpoint: %s",
                self.endpoint_resource_name,
            )
            response = _predict_with_retry(
                endpoint=endpoint, instances=[instance], parameters=parameters
            )
            duration = time.time() - start_time
            logger.debug(
                "Vertex AI endpoint.predict succeeded in %.2f seconds",
                duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.warning(
                "Vertex AI endpoint.predict failed after %.2f seconds: %s",
                duration,
                e,
                exc_info=True,
            )
            raise

        text = response.predictions[0]
        if text.startswith(full_prompt):
            text = text[len(full_prompt) :].strip()

        message = AIMessage(content=text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "vertex_model_garden"


def _validate_vertex_config(cfg: AgentConfig) -> tuple[str, str, str, str]:
    """Validate Vertex AI configuration fields.

    Args:
        cfg: AgentConfig instance.

    Returns:
        Tuple of (project_id, region, endpoint_id, vertex_model_name).

    Raises:
        ValueError: If required configuration is missing.
    """
    project_id = (cfg.gcp_project_id or "").strip()
    region = (cfg.gcp_region or "").strip()
    endpoint_id = (cfg.vertex_endpoint_id or "").strip()
    vertex_model_name = (cfg.vertex_model_name or "").strip()

    if not project_id:
        raise ValueError("GCP_PROJECT_ID is required when MODEL_BACKEND=vertex")
    if not region:
        raise ValueError("GCP_REGION is required when MODEL_BACKEND=vertex")
    if not endpoint_id and not vertex_model_name:
        raise ValueError(
            "VERTEX_ENDPOINT_ID or VERTEX_MODEL_NAME is required when "
            "MODEL_BACKEND=vertex"
        )

    return project_id, region, endpoint_id, vertex_model_name


def create_model_loader(config: AgentConfig | None = None) -> Callable[[], Any]:
    """Create a lazy MedGemma model loader for the configured backend.

    Args:
        config: Agent configuration. Defaults to ``AgentConfig.from_env()``.

    Returns:
        Callable that loads and returns a LangChain chat model when invoked.

    Raises:
        ValueError: If required Vertex configuration is missing.
        NotImplementedError: If backend is "local" (not yet ported).
    """
    cfg = config or AgentConfig.from_env()

    if cfg.backend == "vertex":
        return _create_vertex_model_loader(cfg)

    raise NotImplementedError("Local MedGemma loading not yet ported")


def _create_vertex_model_loader(cfg: AgentConfig) -> Callable[[], Any]:
    """Create a lazy Vertex AI model loader.

    Args:
        cfg: Validated AgentConfig with backend=="vertex".

    Returns:
        Callable that lazily initializes and returns the model.
    """
    project_id, region, endpoint_id, vertex_model_name = _validate_vertex_config(cfg)

    @lazy_singleton
    def load_model() -> Any:
        try:
            import vertexai
        except ImportError as exc:
            raise ImportError(
                "Vertex AI backend requires google-cloud-aiplatform installed."
            ) from exc

        vertexai.init(project=project_id, location=region)

        if vertex_model_name:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise ImportError(
                    "Vertex AI backend requires langchain-google-genai installed."
                ) from exc

            return ChatGoogleGenerativeAI(
                model=vertex_model_name,
                project=project_id,
                location=region,
                vertexai=True,
                max_output_tokens=cfg.max_new_tokens,
            )

        endpoint_resource_name = (
            f"projects/{project_id}/locations/{region}/endpoints/{endpoint_id}"
        )
        return ModelGardenChatModel(
            endpoint_resource_name=endpoint_resource_name,
            project=project_id,
            location=region,
            max_output_tokens=cfg.max_new_tokens,
        )

    return load_model
