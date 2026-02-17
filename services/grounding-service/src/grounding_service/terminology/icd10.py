"""ICD-10-CM terminology client using NLM Clinical Tables API.

Searches the NLM Clinical Tables ICD-10-CM database (free, no API key).

API documentation: https://clinicaltables.nlm.nih.gov/apidoc/icd10cm/v3/doc.html
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

_NLM_ICD10_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
_SYSTEM = "ICD-10-CM"


class Icd10Client(BaseTerminologyClient):
    """Terminology client for ICD-10-CM via NLM Clinical Tables API.

    No API key required. Returns up to ``limit`` best matches.
    """

    _cache_namespace = "icd10"

    async def _fetch(self, term: str, limit: int) -> list[TerminologyResult]:
        """Search ICD-10-CM codes by term.

        Args:
            term: Clinical term to search (e.g., "type 2 diabetes").
            limit: Maximum results to return.

        Returns:
            List of TerminologyResult objects with system="ICD-10-CM".
        """
        params = {
            "sf": "code,name",
            "terms": term,
            "maxList": limit,
        }
        try:
            response = await self._http.get(_NLM_ICD10_URL, params=params)
        except Exception:
            raise

        if response.status_code >= 500:
            raise _TransientError(response.status_code, response.text)
        if response.status_code == 429:
            raise _TransientError(429, response.text)
        if not response.is_success:
            logger.warning(
                "ICD-10 Clinical Tables returned %s for term=%r",
                response.status_code,
                term,
            )
            return []

        data: Any = response.json()
        return self._parse_response(data, limit)

    @staticmethod
    def _parse_response(data: Any, limit: int) -> list[TerminologyResult]:
        """Parse NLM Clinical Tables ICD-10 response.

        Response format: [total_count, codes_array, extra_data, display_strings]
        - data[0]: total result count (int)
        - data[1]: list of code strings (e.g., ["E11", "E11.0", ...])
        - data[2]: null or extra data
        - data[3]: list of [code, name] pairs (e.g., [["E11", "Type 2 diabetes"]])

        Args:
            data: Parsed JSON response (list of 4 elements).
            limit: Maximum results to extract.

        Returns:
            List of TerminologyResult objects.
        """
        results: list[TerminologyResult] = []
        if not isinstance(data, list) or len(data) < 4:
            return results

        display_items = data[3]
        if not isinstance(display_items, list):
            return results

        for i, item in enumerate(display_items[:limit]):
            if not isinstance(item, list) or len(item) < 2:
                continue
            code = item[0]
            name = item[1]
            if not code:
                continue
            # Assign higher confidence to earlier results (ranked by relevance)
            confidence = max(0.5, 0.95 - i * 0.05)
            results.append(
                TerminologyResult(
                    code=str(code),
                    display=str(name) if name else str(code),
                    system=_SYSTEM,
                    confidence=round(confidence, 3),
                    method="nlm_clinical_tables",
                )
            )

        return results
