"""TerminologyRouter: entity-type-aware routing to terminology APIs.

Routes entities to terminology APIs based on entity type using a YAML config.
Supports direct Python imports for UMLS/SNOMED and direct NLM API calls for
RxNorm/ICD-10/LOINC/HPO.

Per user decisions:
- Entity type → API mapping stored in config file (YAML), not hardcoded.
- UMLS/SNOMED accessed via direct Python import (not MCP subprocess).
- RxNorm/ICD-10/LOINC/HPO via direct NLM REST APIs (httpx, no auth required).
- On API failure: retry transient errors; continue on permanent failures.
- Demographic entities explicitly skipped with logging, not silently dropped.

See config/routing.yaml for the entity type → API mapping.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
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

# NLM API URLs
_RXNORM_APPROXIMATE_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
_ICD10_SEARCH_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
_LOINC_SEARCH_URL = "https://clinicaltables.nlm.nih.gov/api/loincs/v3/search"
_HPO_SEARCH_URL = "https://ontology.jax.org/api/hp/search"

# HTTP timeout for NLM API calls
_HTTP_TIMEOUT = 10.0

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
                elif source == "direct_api":
                    candidates = await self._query_direct_api(api_name, entity_text)
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

    @retry(
        retry=retry_if_exception_type(TransientAPIError),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _query_direct_api(
        self, api_name: str, entity_text: str
    ) -> list[GroundingCandidate]:
        """Query NLM terminology APIs directly via HTTP.

        Dispatches to the appropriate NLM REST API based on api_name.
        Uses diskcache for 7-day TTL caching. Retries on 429/5xx errors.

        Supported apis: rxnorm, icd10, loinc, hpo.

        Args:
            api_name: One of "rxnorm", "icd10", "loinc", "hpo".
            entity_text: Term to search.

        Returns:
            List of GroundingCandidate objects parsed from the API response.

        Raises:
            TransientAPIError: On 429 or 5xx responses.
            PermanentAPIError: On 4xx responses.
        """
        cache_key = f"terminology:{api_name}:{entity_text.lower().strip()}"
        cache = _get_cache()

        if cache is not None:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    "Cache hit for %s '%s' (%d candidates)",
                    api_name,
                    entity_text,
                    len(cached),
                )
                return [GroundingCandidate(**c) for c in cached]

        candidates: list[GroundingCandidate] = []

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if api_name == "rxnorm":
                candidates = await self._fetch_rxnorm(client, entity_text)
            elif api_name == "icd10":
                candidates = await self._fetch_icd10(client, entity_text)
            elif api_name == "loinc":
                candidates = await self._fetch_loinc(client, entity_text)
            elif api_name == "hpo":
                candidates = await self._fetch_hpo(client, entity_text)
            else:
                logger.warning(
                    "Unknown direct_api name '%s' for entity '%s'. Skipping.",
                    api_name,
                    entity_text,
                )
                return []

        if cache is not None and candidates:
            cache.set(
                cache_key,
                [c.model_dump() for c in candidates],
                expire=_CACHE_TTL,
            )

        return candidates

    async def _fetch_rxnorm(
        self, client: httpx.AsyncClient, entity_text: str
    ) -> list[GroundingCandidate]:
        """Fetch RxNorm candidates from the NLM RxNav approximate term API.

        Args:
            client: httpx async client.
            entity_text: Drug/medication term to search.

        Returns:
            List of GroundingCandidate objects with RxCUI codes.

        Raises:
            TransientAPIError: On 429 or 5xx responses.
            PermanentAPIError: On other 4xx responses.
        """
        resp = await client.get(
            _RXNORM_APPROXIMATE_URL,
            params={"term": entity_text, "maxEntries": "5"},
        )
        self._raise_for_status(resp, "rxnorm")

        data = resp.json()
        candidates: list[GroundingCandidate] = []

        # Response: {"approximateGroup": {"inputTerm": ..., "candidate": [...]}}
        approx_group = data.get("approximateGroup", {})
        raw_candidates = approx_group.get("candidate", []) or []

        for i, item in enumerate(raw_candidates[:5]):
            rxcui = item.get("rxcui", "")
            name = item.get("name", entity_text)
            # RxNorm scores are integers (rank); normalize to 0.0-1.0
            raw_score = float(item.get("score", 0))
            score = min(raw_score / 100.0, 1.0) if raw_score > 0 else 0.5

            if rxcui:
                candidates.append(
                    GroundingCandidate(
                        source_api="rxnorm",
                        code=rxcui,
                        preferred_term=name,
                        semantic_type=None,
                        score=score,
                    )
                )

        logger.debug(
            "RxNorm: '%s' → %d candidates", entity_text, len(candidates)
        )
        return candidates

    async def _fetch_icd10(
        self, client: httpx.AsyncClient, entity_text: str
    ) -> list[GroundingCandidate]:
        """Fetch ICD-10-CM candidates from NLM Clinical Tables API.

        Args:
            client: httpx async client.
            entity_text: Condition/diagnosis term to search.

        Returns:
            List of GroundingCandidate objects with ICD-10 codes.

        Raises:
            TransientAPIError: On 429 or 5xx responses.
            PermanentAPIError: On other 4xx responses.
        """
        resp = await client.get(
            _ICD10_SEARCH_URL,
            params={"sf": "code,name", "terms": entity_text, "maxList": "5"},
        )
        self._raise_for_status(resp, "icd10")

        data = resp.json()
        candidates: list[GroundingCandidate] = []

        # Response format: [total, codes_list, extra_fields, display_strings]
        # codes_list is at index 1: list of lists like [["J45.909"], ["E11.9"]]
        # display_strings at index 3: list of lists like [["Asthma", "..."]]
        if not isinstance(data, list) or len(data) < 4:
            logger.debug("ICD-10 API returned unexpected format for '%s'", entity_text)
            return candidates

        codes_list = data[1] or []
        display_list = data[3] or []

        for i, code_item in enumerate(codes_list[:5]):
            if not isinstance(code_item, list) or not code_item:
                continue
            code = code_item[0] if code_item else ""
            display = ""
            if i < len(display_list) and isinstance(display_list[i], list):
                display = display_list[i][0] if display_list[i] else entity_text
            else:
                display = entity_text

            if code:
                # Rank-based score: first result = 1.0, decreasing by 0.1
                score = max(1.0 - i * 0.1, 0.5)
                candidates.append(
                    GroundingCandidate(
                        source_api="icd10",
                        code=code,
                        preferred_term=display,
                        semantic_type=None,
                        score=score,
                    )
                )

        logger.debug(
            "ICD-10: '%s' → %d candidates", entity_text, len(candidates)
        )
        return candidates

    async def _fetch_loinc(
        self, client: httpx.AsyncClient, entity_text: str
    ) -> list[GroundingCandidate]:
        """Fetch LOINC candidates from NLM Clinical Tables API.

        Args:
            client: httpx async client.
            entity_text: Lab test/observation term to search.

        Returns:
            List of GroundingCandidate objects with LOINC codes.

        Raises:
            TransientAPIError: On 429 or 5xx responses.
            PermanentAPIError: On other 4xx responses.
        """
        resp = await client.get(
            _LOINC_SEARCH_URL,
            params={
                "sf": "LOINC_NUM,LONG_COMMON_NAME",
                "terms": entity_text,
                "maxList": "5",
            },
        )
        self._raise_for_status(resp, "loinc")

        data = resp.json()
        candidates: list[GroundingCandidate] = []

        # Same format as ICD-10: [total, codes_list, extra_fields, display_strings]
        if not isinstance(data, list) or len(data) < 4:
            logger.debug("LOINC API returned unexpected format for '%s'", entity_text)
            return candidates

        codes_list = data[1] or []
        display_list = data[3] or []

        for i, code_item in enumerate(codes_list[:5]):
            if not isinstance(code_item, list) or not code_item:
                continue
            code = code_item[0] if code_item else ""
            display = ""
            if i < len(display_list) and isinstance(display_list[i], list):
                display = display_list[i][0] if display_list[i] else entity_text
            else:
                display = entity_text

            if code:
                score = max(1.0 - i * 0.1, 0.5)
                candidates.append(
                    GroundingCandidate(
                        source_api="loinc",
                        code=code,
                        preferred_term=display,
                        semantic_type=None,
                        score=score,
                    )
                )

        logger.debug(
            "LOINC: '%s' → %d candidates", entity_text, len(candidates)
        )
        return candidates

    async def _fetch_hpo(
        self, client: httpx.AsyncClient, entity_text: str
    ) -> list[GroundingCandidate]:
        """Fetch HPO candidates from JAX HPO ontology API.

        Args:
            client: httpx async client.
            entity_text: Phenotype/biomarker term to search.

        Returns:
            List of GroundingCandidate objects with HPO codes.

        Raises:
            TransientAPIError: On 429 or 5xx responses.
            PermanentAPIError: On other 4xx responses.
        """
        resp = await client.get(
            _HPO_SEARCH_URL,
            params={"q": entity_text, "max": "5"},
        )
        self._raise_for_status(resp, "hpo")

        data = resp.json()
        candidates: list[GroundingCandidate] = []

        # Response: {"terms": [{"id": "HP:0001234", "name": "...", ...}, ...]}
        terms = data.get("terms", []) or []

        for i, term in enumerate(terms[:5]):
            hpo_id = term.get("id", "")
            name = term.get("name", entity_text)
            # HPO score not provided; use rank-based
            score = max(1.0 - i * 0.1, 0.5)

            if hpo_id:
                candidates.append(
                    GroundingCandidate(
                        source_api="hpo",
                        code=hpo_id,
                        preferred_term=name,
                        semantic_type=None,
                        score=score,
                    )
                )

        logger.debug(
            "HPO: '%s' → %d candidates", entity_text, len(candidates)
        )
        return candidates

    @staticmethod
    def _raise_for_status(resp: httpx.Response, api_name: str) -> None:
        """Raise appropriate error class based on HTTP status code.

        Args:
            resp: httpx response object.
            api_name: API name for logging context.

        Raises:
            TransientAPIError: On 408, 429, or 5xx status codes.
            PermanentAPIError: On 4xx status codes (not 408/429).
        """
        if resp.status_code == 429:
            raise TransientAPIError(
                f"{api_name} rate limited (429): {resp.text[:200]}"
            )
        if resp.status_code == 408:
            raise TransientAPIError(
                f"{api_name} request timeout (408)"
            )
        if resp.status_code >= 500:
            raise TransientAPIError(
                f"{api_name} server error ({resp.status_code}): {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise PermanentAPIError(
                f"{api_name} client error ({resp.status_code}): {resp.text[:200]}"
            )
