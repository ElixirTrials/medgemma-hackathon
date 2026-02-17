"""TerminologyRouter: entity-type-aware routing to terminology APIs.

Routes entities to terminology APIs based on entity type using a YAML config.
Supports direct Python imports for UMLS/SNOMED and a ToolUniverse stub for
RxNorm/ICD-10/LOINC/HPO (pending ToolUniverse medical tool validation).

Per user decisions:
- Entity type → API mapping stored in config file (YAML), not hardcoded.
- UMLS/SNOMED accessed via direct Python import (not MCP subprocess).
- On API failure: retry transient errors; continue on permanent failures.
- Demographic entities explicitly skipped with logging, not silently dropped.

See config/routing.yaml for the entity type → API mapping.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
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


class TransientAPIError(Exception):
    """Retriable API failure: rate limit (429), timeout (408), server error (5xx).

    TerminologyRouter retries these automatically with exponential backoff.
    """


class PermanentAPIError(Exception):
    """Non-retriable API failure: auth error (401/403), validation (400/422).

    TerminologyRouter logs and skips these — retrying cannot fix them.
    """


class TerminologyRouter:
    """Route entities to terminology APIs based on YAML config.

    Loads entity type → API mapping from routing.yaml. For each entity,
    queries all matching APIs and returns a list of GroundingCandidate objects.
    MedGemma then selects the best match downstream.

    Implements error accumulation: individual API failures are logged and
    skipped, not propagated. The entity is still grounded by the remaining APIs.

    Usage:
        router = TerminologyRouter()
        candidates = await router.route_entity("metformin", "Medication")
        # candidates: [GroundingCandidate(source_api="umls", ...), ...]

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

        Returns an empty list for Demographic (explicitly skipped) and for
        entity types not found in the routing config. Both cases are logged.

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

        # Explicit skip (e.g. Demographic: {skip: true})
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

        Queries each API configured for the entity type. Individual API
        failures are logged and skipped (error accumulation). The caller
        (MedGemma ground node) receives all available candidates and
        selects the best match.

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
        api_configs: dict = self.config.get("api_configs", {})

        for api_name in api_names:
            api_config = api_configs.get(api_name, {})
            source = api_config.get("source", "")

            try:
                if source == "direct_python" and api_name == "umls":
                    candidates = await self._query_umls(entity_text)
                elif source == "direct_python" and api_name == "snomed":
                    candidates = await self._query_snomed(entity_text)
                elif source == "tooluniverse":
                    tool_name = api_config.get("tool_name", api_name)
                    candidates = await self._query_tooluniverse(
                        tool_name, entity_text
                    )
                else:
                    logger.warning(
                        "Unknown API source '%s' for api '%s'. Skipping.",
                        source,
                        api_name,
                    )
                    continue

                # Tag each candidate with the source API
                tagged = [
                    c.model_copy(update={"source_api": api_name})
                    for c in candidates
                ]
                all_candidates.extend(tagged)

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
    async def _query_umls(self, entity_text: str) -> list[GroundingCandidate]:
        """Query UMLS via direct Python import from umls_mcp_server.

        Uses get_umls_client() context manager for connection management.
        Retries on TransientAPIError (rate limits, server errors).

        Args:
            entity_text: Term to search in UMLS.

        Returns:
            List of GroundingCandidate objects from UMLS concept search.
        """
        from umls_mcp_server.umls_api import (  # type: ignore[import-untyped]
            UmlsApiAuthenticationError,
            UmlsApiRateLimitError,
            UmlsApiServerError,
            UmlsApiTimeoutError,
            get_umls_client,
        )

        try:
            with get_umls_client() as client:
                results = client.concept_search(entity_text)
                candidates = []
                for result in results:
                    candidates.append(
                        GroundingCandidate(
                            source_api="umls",
                            code=result.get("ui", ""),
                            preferred_term=result.get("name", entity_text),
                            semantic_type=result.get("semanticType"),
                            score=result.get("score", 0.0),
                        )
                    )
                return candidates
        except UmlsApiAuthenticationError as e:
            raise PermanentAPIError(f"UMLS auth error: {e}") from e
        except (UmlsApiRateLimitError, UmlsApiServerError, UmlsApiTimeoutError) as e:
            raise TransientAPIError(f"UMLS transient error: {e}") from e

    async def _query_snomed(self, entity_text: str) -> list[GroundingCandidate]:
        """Query SNOMED via direct Python import from grounding_service.

        Uses UMLS CUI lookup then maps to SNOMED code. This is a two-step
        process: first find UMLS candidates, then map CUI to SNOMED code.

        Args:
            entity_text: Term to search for SNOMED mapping.

        Returns:
            List of GroundingCandidate objects from SNOMED lookup.
            Empty list if no UMLS candidates found or SNOMED mapping fails.
        """
        # First find UMLS candidates to get CUIs, then look up SNOMED codes
        umls_candidates = await self._query_umls(entity_text)

        candidates: list[GroundingCandidate] = []
        for umls_c in umls_candidates[:3]:  # Limit to top 3 UMLS hits
            cui = umls_c.code
            if not cui:
                continue
            try:
                from grounding_service.umls_client import (  # type: ignore[import-untyped]
                    get_snomed_code_for_cui,
                )

                snomed_code = await get_snomed_code_for_cui(cui)
                if snomed_code:
                    candidates.append(
                        GroundingCandidate(
                            source_api="snomed",
                            code=snomed_code,
                            preferred_term=umls_c.preferred_term,
                            semantic_type=umls_c.semantic_type,
                            score=umls_c.score,
                        )
                    )
            except Exception as e:
                logger.warning(
                    "SNOMED lookup failed for CUI '%s' (entity: '%s'): %s",
                    cui,
                    entity_text,
                    e,
                )

        return candidates

    async def _query_tooluniverse(
        self, tool_name: str, entity_text: str
    ) -> list[GroundingCandidate]:
        """Query a ToolUniverse medical terminology tool.

        TODO: ToolUniverse medical tool availability needs validation.
        Per 31-RESEARCH Open Question 1: ToolUniverse has 1000+ scientific tools
        but specific RxNorm, ICD-10, LOINC, HPO tool availability and API
        signatures have not been confirmed via direct testing.

        Currently implemented as a stub that returns an empty list.
        The UMLS/SNOMED direct Python path is fully functional.

        Args:
            tool_name: ToolUniverse tool name (e.g. "rxnorm_search").
            entity_text: Term to search.

        Returns:
            Empty list (stub — ToolUniverse integration pending validation).
        """
        # TODO: Implement ToolUniverse Python SDK integration once medical
        # tool availability is validated. Expected usage:
        #
        #   from tooluniverse import ToolLoader
        #   loader = ToolLoader(tools=[tool_name], compact_mode=True)
        #   tool = loader.get_tool(tool_name)
        #   results = await tool.run(query=entity_text)
        #   return [GroundingCandidate(source_api=..., ...) for r in results]
        #
        # See: https://zitniklab.hms.harvard.edu/ToolUniverse/
        logger.debug(
            "ToolUniverse tool '%s' is a stub — returning empty candidates "
            "for entity '%s'. UMLS/SNOMED paths are active.",
            tool_name,
            entity_text,
        )
        return []
