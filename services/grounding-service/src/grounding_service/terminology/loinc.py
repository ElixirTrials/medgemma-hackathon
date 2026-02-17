"""LOINC terminology client using NLM Clinical Tables LOINC API.

Searches the NLM Clinical Tables LOINC database (free, no API key).

API documentation: https://clinicaltables.nlm.nih.gov/apidoc/loincs/v3/doc.html
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

_NLM_LOINC_URL = "https://clinicaltables.nlm.nih.gov/api/loincs/v3/search"
_SYSTEM = "LOINC"


class LoincClient(BaseTerminologyClient):
    """Terminology client for LOINC via NLM Clinical Tables LOINC API.

    No API key required. Returns up to ``limit`` best matches.
    """

    _cache_namespace = "loinc"

    async def _fetch(self, term: str, limit: int) -> list[TerminologyResult]:
        """Search LOINC codes by term.

        Args:
            term: Lab or clinical observation term (e.g., "hemoglobin A1c").
            limit: Maximum results to return.

        Returns:
            List of TerminologyResult objects with system="LOINC".
        """
        params = {
            "terms": term,
            "maxList": limit,
            # Request LOINC_NUM and LONG_COMMON_NAME fields
            "df": "LOINC_NUM,LONG_COMMON_NAME",
        }
        try:
            response = await self._http.get(_NLM_LOINC_URL, params=params)
        except Exception:
            raise

        if response.status_code >= 500:
            raise _TransientError(response.status_code, response.text)
        if response.status_code == 429:
            raise _TransientError(429, response.text)
        if not response.is_success:
            logger.warning(
                "LOINC Clinical Tables returned %s for term=%r",
                response.status_code,
                term,
            )
            return []

        data: Any = response.json()
        return self._parse_response(data, limit)

    @staticmethod
    def _parse_response(data: Any, limit: int) -> list[TerminologyResult]:
        """Parse NLM Clinical Tables LOINC response.

        Response format: [total_count, codes_array, extra_data, display_strings]
        - data[0]: total result count (int)
        - data[1]: list of LOINC_NUM strings (e.g., ["4548-4", ...])
        - data[2]: null or extra data
        - data[3]: list of [LOINC_NUM, LONG_COMMON_NAME] pairs

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
            # Earlier results have higher relevance
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
