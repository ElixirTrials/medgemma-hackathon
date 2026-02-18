"""TerminologyRouter: entity-type-aware routing to terminology APIs via ToolUniverse.

Routes entities to terminology APIs based on entity type using a YAML config.
All 6 systems (UMLS, SNOMED, ICD-10, LOINC, RxNorm, HPO) are accessed via the
ToolUniverse SDK singleton in tooluniverse_client.py.

Per user decisions:
- Entity type → API mapping stored in config file (YAML), not hardcoded.
- All terminology systems accessed via ToolUniverse SDK (single dependency).
- On API failure: retry transient errors; continue on permanent failures.
- Consent entities explicitly skipped with logging.
- Demographic entities routed normally (not skipped); MedGemma handles derived
  entity mapping (age → birthDate concept, gender → SNOMED gender concepts).

See config/routing.yaml for the entity type → API mapping.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from platformdirs import user_cache_dir
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from protocol_processor.schemas.grounding import GroundingCandidate

logger = logging.getLogger(__name__)

# Default routing config path relative to this file
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "routing.yaml"

# diskcache TTL: 7 days in seconds
_CACHE_TTL = 7 * 24 * 60 * 60


def _get_cache():
    """Get or create the diskcache Cache instance.

    Returns:
        diskcache.Cache instance stored in user cache dir, or None if
        diskcache is not installed.
    """
    try:
        import diskcache

        cache_dir = Path(user_cache_dir("medgemma-terminology-router"))
        return diskcache.Cache(str(cache_dir))
    except ImportError:
        logger.debug("diskcache not installed — terminology API caching disabled.")
        return None


class TransientAPIError(Exception):
    """Retriable API failure: rate limit (429), timeout (408), server error (5xx).

    TerminologyRouter retries these automatically with exponential backoff.
    """


class PermanentAPIError(Exception):
    """Non-retriable API failure: auth error (401/403), validation (400/422).

    TerminologyRouter logs and skips these — retrying cannot fix them.
    """


class TerminologyRouter:
    """Route entities to terminology APIs via ToolUniverse SDK.

    Loads entity type → API mapping from routing.yaml. For each entity,
    queries all matching APIs via the ToolUniverse singleton client and
    returns a list of GroundingCandidate objects. MedGemma then selects
    the best match downstream.

    Implements error accumulation: individual API failures are logged and
    skipped, not propagated. The entity is still grounded by remaining APIs.

    Usage:
        router = TerminologyRouter()
        candidates = await router.route_entity("metformin", "Medication")
        # candidates: [GroundingCandidate(source_api="rxnorm", ...), ...]

    Attributes:
        config: Parsed YAML config dict.
        config_path: Path to the routing.yaml file used.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize TerminologyRouter with routing config.

        Args:
            config_path: Path to routing.yaml. Defaults to config/routing.yaml
                relative to this package.
        """
        self.config_path = config_path or _DEFAULT_CONFIG_PATH
        with open(self.config_path) as f:
            self.config: dict = yaml.safe_load(f)

    def get_apis_for_entity(self, entity_type: str) -> list[str]:
        """Get list of API names to query for this entity type.

        Returns an empty list for entity types with skip: true in routing config
        (e.g. Consent) and for entity types not found in the routing config.
        Both cases are logged.

        Args:
            entity_type: Entity type string (e.g. "Medication", "Condition").

        Returns:
            List of API names to query, or empty list if entity should be skipped.
        """
        routing_rules: dict = self.config.get("routing_rules", {})
        rule = routing_rules.get(entity_type)

        if rule is None:
            logger.warning(
                "Unknown entity type '%s' — not in routing config. "
                "Skipping grounding. Add to config/routing.yaml to enable.",
                entity_type,
            )
            return []

        # Explicit skip (e.g. Consent: {skip: true})
        if isinstance(rule, dict) and rule.get("skip"):
            logger.info(
                "Entity type '%s' is explicitly skipped in routing config "
                "(no terminology grounding for this type).",
                entity_type,
            )
            return []

        if isinstance(rule, list):
            return rule

        # Unexpected rule format — treat as unknown
        logger.warning(
            "Unexpected routing rule format for '%s': %r. Skipping.",
            entity_type,
            rule,
        )
        return []

    async def route_entity(
        self, entity_text: str, entity_type: str
    ) -> list[GroundingCandidate]:
        """Route entity to all matching APIs and return all candidates.

        Queries each API configured for the entity type via ToolUniverse SDK.
        Individual API failures are logged and skipped (error accumulation).
        The caller (MedGemma ground node) receives all available candidates
        and selects the best match.

        Args:
            entity_text: The entity text to look up (e.g. "metformin").
            entity_type: The entity type (e.g. "Medication").

        Returns:
            List of GroundingCandidate objects from all queried APIs.
            Empty list if entity type is skipped or all APIs fail.
        """
        api_names = self.get_apis_for_entity(entity_type)

        if not api_names:
            return []

        all_candidates: list[GroundingCandidate] = []

        for api_name in api_names:
            try:
                candidates = await self._query_tooluniverse(api_name, entity_text)
                all_candidates.extend(candidates)

            except PermanentAPIError as e:
                # Non-retriable: log and skip this API
                logger.error(
                    "Permanent API error from '%s' for entity '%s': %s",
                    api_name,
                    entity_text,
                    e,
                )
            except Exception as e:
                # Transient/unexpected: log and skip (tenacity already retried)
                logger.error(
                    "API '%s' failed for entity '%s' after retries: %s",
                    api_name,
                    entity_text,
                    e,
                )

        return all_candidates

    @retry(
        retry=retry_if_exception_type(TransientAPIError),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _query_tooluniverse(
        self, api_name: str, entity_text: str
    ) -> list[GroundingCandidate]:
        """Query terminology system via ToolUniverse client wrapper.

        Uses the singleton search_terminology function which handles tool
        dispatch, response parsing, and in-memory TTL caching.

        Retries on TransientAPIError with exponential backoff (3 attempts max).

        Args:
            api_name: Terminology system name (e.g. "umls", "icd10").
            entity_text: Term to search.

        Returns:
            List of GroundingCandidate objects from ToolUniverse.

        Raises:
            TransientAPIError: On retriable errors (rate limit, timeout, 5xx).
        """
        from protocol_processor.tools.tooluniverse_client import search_terminology

        candidates = await search_terminology(api_name, entity_text, max_results=10)
        return candidates
