"""RxNorm terminology client using NLM RxNav REST API.

Searches the NLM RxNorm database (free, no API key required).
Primary search: exact/partial drug name match via /REST/drugs.json.
Fallback: approximate term search via /REST/approximateTerm.json.

API documentation: https://rxnav.nlm.nih.gov/RxNormAPIs.html
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

_RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
_SYSTEM = "RxNorm"


class RxNormClient(BaseTerminologyClient):
    """Terminology client for NLM RxNorm via RxNav REST API.

    No API key required. Searches by drug name with approximate-match
    fallback when exact name lookup returns no results.
    """

    _cache_namespace = "rxnorm"

    async def _fetch(self, term: str, limit: int) -> list[TerminologyResult]:
        """Search RxNorm for drug/medication concepts.

        Tries /drugs.json first (exact/partial name match), then falls back
        to /approximateTerm.json if no results.

        Args:
            term: Drug or medication name to search.
            limit: Maximum results to return.

        Returns:
            List of TerminologyResult objects with system="RxNorm".
        """
        results = await self._search_drugs(term, limit)
        if not results:
            results = await self._search_approximate(term, limit)
        return results

    async def _search_drugs(self, term: str, limit: int) -> list[TerminologyResult]:
        """Search via /REST/drugs.json (name-based lookup)."""
        url = f"{_RXNAV_BASE}/drugs.json"
        try:
            response = await self._http.get(url, params={"name": term})
        except Exception:
            raise

        if response.status_code >= 500:
            raise _TransientError(response.status_code, response.text)
        if response.status_code == 429:
            raise _TransientError(429, response.text)
        if not response.is_success:
            logger.warning(
                "RxNorm /drugs.json returned %s for term=%r",
                response.status_code,
                term,
            )
            return []

        data: dict[str, Any] = response.json()
        return self._parse_drugs_response(data, limit)

    async def _search_approximate(
        self, term: str, limit: int
    ) -> list[TerminologyResult]:
        """Search via /REST/approximateTerm.json (fuzzy/approximate match)."""
        url = f"{_RXNAV_BASE}/approximateTerm.json"
        try:
            response = await self._http.get(
                url, params={"term": term, "maxEntries": limit}
            )
        except Exception:
            raise

        if response.status_code >= 500:
            raise _TransientError(response.status_code, response.text)
        if response.status_code == 429:
            raise _TransientError(429, response.text)
        if not response.is_success:
            logger.warning(
                "RxNorm /approximateTerm.json returned %s for term=%r",
                response.status_code,
                term,
            )
            return []

        data: dict[str, Any] = response.json()
        return self._parse_approximate_response(data, limit)

    @staticmethod
    def _parse_drugs_response(
        data: dict[str, Any], limit: int
    ) -> list[TerminologyResult]:
        """Parse /drugs.json response into TerminologyResult list.

        Response structure:
        {
          "drugGroup": {
            "conceptGroup": [
              { "tty": "...", "conceptProperties": [
                  {"rxcui": "...", "name": "...", ...}, ...
              ]},
              ...
            ]
          }
        }
        """
        results: list[TerminologyResult] = []
        drug_group = data.get("drugGroup", {})
        concept_groups = drug_group.get("conceptGroup", [])
        if not isinstance(concept_groups, list):
            return results

        for group in concept_groups:
            if not isinstance(group, dict):
                continue
            props = group.get("conceptProperties", [])
            if not isinstance(props, list):
                continue
            for prop in props:
                if not isinstance(prop, dict):
                    continue
                rxcui = prop.get("rxcui", "")
                name = prop.get("name", "")
                if rxcui and name:
                    results.append(
                        TerminologyResult(
                            code=str(rxcui),
                            display=str(name),
                            system=_SYSTEM,
                            confidence=0.9,
                            method="exact",
                        )
                    )
                if len(results) >= limit:
                    return results

        return results[:limit]

    @staticmethod
    def _parse_approximate_response(
        data: dict[str, Any], limit: int
    ) -> list[TerminologyResult]:
        """Parse /approximateTerm.json response into TerminologyResult list.

        Response structure:
        {
          "approximateGroup": {
            "candidate": [
              {"rxcui": "...", "rxaui": "...", "score": "...", "rank": "...", ...},
              ...
            ]
          }
        }
        """
        results: list[TerminologyResult] = []
        approx_group = data.get("approximateGroup", {})
        candidates = approx_group.get("candidate", [])
        if not isinstance(candidates, list):
            return results

        seen_rxcui: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            rxcui = candidate.get("rxcui", "")
            name = candidate.get("name", "")
            score_raw = candidate.get("score", "0")
            if not rxcui or rxcui in seen_rxcui:
                continue
            seen_rxcui.add(str(rxcui))

            # Normalise score to [0, 1] (RxNav scores are integers 0-100)
            try:
                score = min(float(score_raw), 100.0) / 100.0
            except (ValueError, TypeError):
                score = 0.5

            results.append(
                TerminologyResult(
                    code=str(rxcui),
                    display=str(name) if name else str(rxcui),
                    system=_SYSTEM,
                    confidence=round(score, 3),
                    method="approximate",
                )
            )
            if len(results) >= limit:
                break

        return results
