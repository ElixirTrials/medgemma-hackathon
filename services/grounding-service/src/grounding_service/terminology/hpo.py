"""HPO (Human Phenotype Ontology) terminology client using Monarch API.

Searches the HPO database via the Monarch Initiative API (free, no API key).

API documentation: https://ontology.jax.org/api
"""

from __future__ import annotations

import logging
from typing import Any

from grounding_service.terminology.base import (
    BaseTerminologyClient,
    TerminologyResult,
    _TransientError,
)

logger = logging.getLogger(__name__)

_HPO_SEARCH_URL = "https://ontology.jax.org/api/hp/search"
_SYSTEM = "HPO"


class HpoClient(BaseTerminologyClient):
    """Terminology client for HPO via Monarch Initiative API.

    No API key required. Returns up to ``limit`` best matches for
    phenotype/disease terms.
    """

    _cache_namespace = "hpo"

    async def _fetch(self, term: str, limit: int) -> list[TerminologyResult]:
        """Search HPO phenotype concepts by term.

        Args:
            term: Phenotype or disease term (e.g., "seizure", "ataxia").
            limit: Maximum results to return.

        Returns:
            List of TerminologyResult objects with system="HPO".
        """
        params = {
            "q": term,
            "rows": limit,
        }
        try:
            response = await self._http.get(_HPO_SEARCH_URL, params=params)
        except Exception:
            raise

        if response.status_code >= 500:
            raise _TransientError(response.status_code, response.text)
        if response.status_code == 429:
            raise _TransientError(429, response.text)
        if not response.is_success:
            logger.warning(
                "HPO Monarch API returned %s for term=%r",
                response.status_code,
                term,
            )
            return []

        data: dict[str, Any] = response.json()
        return self._parse_response(data, limit)

    @staticmethod
    def _parse_response(data: dict[str, Any], limit: int) -> list[TerminologyResult]:
        """Parse Monarch HPO search response.

        Response structure:
        {
          "docs": [
            {
              "id": "HP:0001250",
              "name": "Seizure",
              "synonym": [...],
              ...
            },
            ...
          ],
          "numFound": 42,
          ...
        }

        Args:
            data: Parsed JSON response dict.
            limit: Maximum results to extract.

        Returns:
            List of TerminologyResult objects.
        """
        results: list[TerminologyResult] = []
        docs = data.get("docs", [])
        if not isinstance(docs, list):
            return results

        for i, doc in enumerate(docs[:limit]):
            if not isinstance(doc, dict):
                continue
            hp_id = doc.get("id", "")
            name = doc.get("name", "")
            if not hp_id:
                continue
            # Earlier results have higher relevance
            confidence = max(0.5, 0.95 - i * 0.05)
            results.append(
                TerminologyResult(
                    code=str(hp_id),
                    display=str(name) if name else str(hp_id),
                    system=_SYSTEM,
                    confidence=round(confidence, 3),
                    method="monarch_search",
                )
            )

        return results
