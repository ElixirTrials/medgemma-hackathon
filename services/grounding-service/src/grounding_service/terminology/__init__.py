"""Terminology HTTP clients for multi-system medical code lookup.

Provides async HTTP clients for:
- RxNorm: medications and drug concepts (NLM RxNav)
- ICD-10-CM: diagnoses and clinical findings (NLM Clinical Tables)
- LOINC: lab tests and observations (NLM Clinical Tables)
- HPO: phenotypes and rare disease terms (Monarch Initiative)

All clients share the same interface (BaseTerminologyClient.search),
disk caching, and retry-with-backoff behaviour.

Example usage::

    from grounding_service.terminology import RxNormClient, TerminologyResult

    client = RxNormClient()
    results: list[TerminologyResult] = await client.search("aspirin", limit=3)
    await client.aclose()
"""

from grounding_service.terminology.base import BaseTerminologyClient, TerminologyResult
from grounding_service.terminology.hpo import HpoClient
from grounding_service.terminology.icd10 import Icd10Client
from grounding_service.terminology.loinc import LoincClient
from grounding_service.terminology.rxnorm import RxNormClient

__all__ = [
    "BaseTerminologyClient",
    "TerminologyResult",
    "RxNormClient",
    "Icd10Client",
    "LoincClient",
    "HpoClient",
]
