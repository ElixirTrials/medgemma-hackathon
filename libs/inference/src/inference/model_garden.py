"""MedGemma model loading for Vertex AI and local GPU backends.

Provides two deployment paths for MedGemma (google/medgemma-4b-it):

1. **Vertex AI Model Garden** (``MODEL_BACKEND=vertex``):
   Uses ``ModelGardenChatModel``, a LangChain BaseChatModel wrapper that
   calls a Vertex AI endpoint with Gemma chat template formatting and
   exponential-backoff retry for transient errors.

2. **Local GPU** (``MODEL_BACKEND=local``):
   Uses ``LocalMedGemmaChatModel``, which loads the HuggingFace model
   locally with optional 4-bit/8-bit quantization via bitsandbytes.
   Requires an NVIDIA GPU with 8 GB+ VRAM for the default 4-bit config.

Both backends expose a standard LangChain ``BaseChatModel`` interface so
the rest of the pipeline (``medgemma_decider.py``, ``ground.py``) is
backend-agnostic.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests  # type: ignore[import-untyped]
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


def _strip_model_garden_artifacts(text: str, full_prompt: str) -> str:
    """Strip echoed prompts and end-of-turn markers from response.

    Note: This is now minimal because Gemini handles JSON structuring.
    MedGemma's output goes to Gemini, so thinking tokens and other artifacts
    are handled by Gemini's structured output parser.
    """
    # Strip echoed prompt if present
    if text.startswith(full_prompt):
        text = text[len(full_prompt) :].strip()

    # Strip trailing end-of-turn marker
    if text.endswith("<end_of_turn>"):
        text = text[: -len("<end_of_turn>")].strip()

    return text


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
        pass  # google-api-core not installed; skip Google-specific checks

    # Do NOT retry on expired credentials — no point retrying with the same creds
    try:
        from google.auth.exceptions import RefreshError

        if isinstance(exception, RefreshError):
            return False
    except ImportError:
        pass  # google-auth not installed; skip RefreshError check

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

    The Endpoint object is instantiated once in the constructor and reused
    across calls to enable gRPC channel reuse and avoid per-call overhead.
    """

    endpoint_resource_name: str
    project: str
    location: str
    max_output_tokens: int = Field(default=8192)
    _endpoint: Any = None

    def model_post_init(self, __context: Any) -> None:
        """Initialize the Vertex AI Endpoint once for connection reuse."""
        from google.cloud import aiplatform

        self._endpoint = aiplatform.Endpoint(self.endpoint_resource_name)

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
        endpoint = self._endpoint

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
        text = _strip_model_garden_artifacts(text, full_prompt)

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


class LocalMedGemmaChatModel(BaseChatModel):
    """LangChain ChatModel wrapper for locally-loaded MedGemma.

    Loads google/medgemma-4b-it (or a custom model path) via HuggingFace
    ``transformers`` with optional bitsandbytes quantization. The model
    and tokenizer are loaded once on first call and reused.

    Requires:
        - NVIDIA GPU with sufficient VRAM (8 GB+ for 4-bit, 16 GB+ for 8-bit)
        - ``torch``, ``transformers``, ``accelerate`` packages
        - ``bitsandbytes`` package (for quantized loading)
    """

    model_path: str = Field(default="google/medgemma-4b-it")
    quantization: str = Field(default="4bit")
    max_output_tokens: int = Field(default=4096)
    _model: Any = None
    _tokenizer: Any = None

    def model_post_init(self, __context: Any) -> None:
        """Validate that required packages are available."""
        pass  # Defer actual loading to first call for fast startup

    def _ensure_loaded(self) -> None:
        """Load model and tokenizer on first use."""
        if self._model is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ImportError(
                "Local MedGemma backend requires torch, transformers, and "
                "accelerate installed. Install with: "
                "pip install torch transformers accelerate bitsandbytes"
            ) from exc

        if not torch.cuda.is_available():
            raise RuntimeError(
                "Local MedGemma backend requires an NVIDIA GPU with CUDA. "
                "No CUDA device detected. Use MODEL_BACKEND=vertex for "
                "cloud-based inference instead."
            )

        logger.info(
            "Loading MedGemma locally: model=%s, quantization=%s",
            self.model_path,
            self.quantization,
        )

        model_kwargs: dict[str, Any] = {
            "device_map": "auto",
            "torch_dtype": torch.bfloat16,
        }

        if self.quantization in ("4bit", "8bit"):
            try:
                from transformers import BitsAndBytesConfig
            except ImportError as exc:
                raise ImportError(
                    "Quantized loading requires bitsandbytes. "
                    "Install with: pip install bitsandbytes"
                ) from exc

            if self.quantization == "4bit":
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
            else:
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_8bit=True,
                )

        start_time = time.time()
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path, **model_kwargs
        )
        duration = time.time() - start_time
        logger.info("MedGemma loaded in %.1f seconds", duration)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a response using the locally-loaded MedGemma model.

        Args:
            messages: List of LangChain messages.
            stop: Optional stop sequences.
            run_manager: Optional callback manager.
            **kwargs: Additional keyword arguments (e.g. temperature).

        Returns:
            ChatResult containing the model's response.
        """
        import torch

        self._ensure_loaded()

        full_prompt = _build_gemma_prompt(messages)

        inputs = self._tokenizer(full_prompt, return_tensors="pt").to(
            self._model.device
        )
        input_length = inputs["input_ids"].shape[1]

        start_time = time.time()
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=self.max_output_tokens,
                temperature=kwargs.get("temperature", 0.1),
                top_p=0.95,
                top_k=40,
                do_sample=True,
            )
        duration = time.time() - start_time

        # Decode only the generated tokens (exclude prompt)
        generated_tokens = outputs[0][input_length:]
        text = self._tokenizer.decode(generated_tokens, skip_special_tokens=True)
        text = _strip_model_garden_artifacts(text, full_prompt)

        logger.debug(
            "Local MedGemma generated %d tokens in %.2f seconds",
            len(generated_tokens),
            duration,
        )

        message = AIMessage(content=text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "local_medgemma"


def create_model_loader(config: AgentConfig | None = None) -> Callable[[], Any]:
    """Create a lazy MedGemma model loader for the configured backend.

    Supports two backends:
        - ``vertex``: Vertex AI Model Garden (cloud, recommended for production)
        - ``local``: Local GPU with HuggingFace transformers (requires NVIDIA GPU)

    Args:
        config: Agent configuration. Defaults to ``AgentConfig.from_env()``.

    Returns:
        Callable that loads and returns a LangChain chat model when invoked.

    Raises:
        ValueError: If required configuration is missing for the selected backend.
    """
    cfg = config or AgentConfig.from_env()

    if cfg.backend == "vertex":
        return _create_vertex_model_loader(cfg)

    return _create_local_model_loader(cfg)


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


def _create_local_model_loader(cfg: AgentConfig) -> Callable[[], Any]:
    """Create a lazy local MedGemma model loader.

    Loads MedGemma (default: google/medgemma-4b-it) from HuggingFace
    with optional 4-bit or 8-bit quantization via bitsandbytes.

    Args:
        cfg: AgentConfig with backend=="local".

    Returns:
        Callable that lazily initializes and returns the model.
    """

    @lazy_singleton
    def load_model() -> Any:
        logger.info(
            "Initializing local MedGemma: model=%s, quantization=%s",
            cfg.model_path,
            cfg.quantization,
        )
        return LocalMedGemmaChatModel(
            model_path=cfg.model_path,
            quantization=cfg.quantization,
            max_output_tokens=cfg.max_new_tokens,
        )

    return load_model
