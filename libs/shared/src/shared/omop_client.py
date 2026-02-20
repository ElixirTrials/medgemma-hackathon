"""Client for querying OMOP Vocabulary database.

Provides methods to map clinical terms to OMOP standard concepts,
find synonyms, and retrieve concept relationships.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


@dataclass
class OmopConcept:
    """OMOP standard concept."""

    concept_id: int
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_class_id: str
    standard_concept: Optional[str]
    concept_code: str
    similarity_score: Optional[float] = None


@dataclass
class ConceptMapping:
    """Result of mapping a term to OMOP concepts."""

    query_term: str
    concepts: List[OmopConcept]
    mapping_method: str  # "exact", "fuzzy", "synonym"
    confidence: float


class OmopVocabularyClient:
    """Client for OMOP Vocabulary database queries."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize OMOP vocabulary client.

        Args:
            database_url: PostgreSQL connection string. If None, reads from
                OMOP_VOCAB_URL environment variable.
        """
        self.database_url = database_url or os.getenv("OMOP_VOCAB_URL")
        if not self.database_url:
            raise ValueError(
                "OMOP_VOCAB_URL not provided and not found in environment"
            )
        self.engine: Optional[Engine] = None

    def _get_engine(self) -> Engine:
        """Lazy-load database engine."""
        if self.engine is None:
            self.engine = create_engine(self.database_url, pool_pre_ping=True)
        return self.engine

    def map_term_to_concept(
        self,
        term: str,
        domain: Optional[str] = None,
        vocabulary: Optional[str] = None,
        limit: int = 5,
    ) -> ConceptMapping:
        """Map a clinical term to OMOP standard concepts.

        Tries three strategies in order:
        1. Exact match on concept name (case-insensitive)
        2. Fuzzy match using trigram similarity on concept names
        3. Fuzzy match on concept synonyms

        Args:
            term: Clinical term to map (e.g., "diabetes", "hypertension")
            domain: Filter by OMOP domain (e.g., "Condition", "Measurement", "Drug")
            vocabulary: Filter by vocabulary (e.g., "SNOMED", "RxNorm", "LOINC")
            limit: Maximum number of results to return

        Returns:
            ConceptMapping with matched concepts and confidence score
        """
        # Strategy 1: Exact match
        concepts = self._exact_match(term, domain, vocabulary, limit)
        if concepts:
            return ConceptMapping(
                query_term=term,
                concepts=concepts,
                mapping_method="exact",
                confidence=1.0,
            )

        # Strategy 2: Fuzzy match on concept names
        concepts = self._fuzzy_match_concept(term, domain, vocabulary, limit)
        if concepts:
            avg_score = sum(c.similarity_score or 0 for c in concepts) / len(concepts)
            return ConceptMapping(
                query_term=term,
                concepts=concepts,
                mapping_method="fuzzy",
                confidence=avg_score,
            )

        # Strategy 3: Fuzzy match on synonyms
        concepts = self._fuzzy_match_synonym(term, domain, vocabulary, limit)
        avg_score = sum(c.similarity_score or 0 for c in concepts) / len(concepts) if concepts else 0.0
        return ConceptMapping(
            query_term=term,
            concepts=concepts,
            mapping_method="synonym",
            confidence=avg_score * 0.9,  # Slightly lower confidence for synonym matches
        )

    def _exact_match(
        self,
        term: str,
        domain: Optional[str],
        vocabulary: Optional[str],
        limit: int,
    ) -> List[OmopConcept]:
        """Find exact matches on concept name."""
        query = text("""
            SELECT 
                concept_id,
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                concept_code
            FROM concept
            WHERE LOWER(concept_name) = LOWER(:term)
              AND standard_concept = 'S'
              AND invalid_reason IS NULL
              AND (:domain IS NULL OR domain_id = :domain)
              AND (:vocabulary IS NULL OR vocabulary_id = :vocabulary)
            LIMIT :limit
        """)

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                query, {"term": term, "domain": domain, "vocabulary": vocabulary, "limit": limit}
            )
            return [
                OmopConcept(
                    concept_id=row.concept_id,
                    concept_name=row.concept_name,
                    domain_id=row.domain_id,
                    vocabulary_id=row.vocabulary_id,
                    concept_class_id=row.concept_class_id,
                    standard_concept=row.standard_concept,
                    concept_code=row.concept_code,
                )
                for row in result
            ]

    def _fuzzy_match_concept(
        self,
        term: str,
        domain: Optional[str],
        vocabulary: Optional[str],
        limit: int,
    ) -> List[OmopConcept]:
        """Find fuzzy matches on concept name using trigram similarity."""
        query = text("""
            SELECT 
                concept_id,
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                concept_code,
                similarity(concept_name, :term) AS score
            FROM concept
            WHERE standard_concept = 'S'
              AND invalid_reason IS NULL
              AND (:domain IS NULL OR domain_id = :domain)
              AND (:vocabulary IS NULL OR vocabulary_id = :vocabulary)
              AND similarity(concept_name, :term) > 0.3
            ORDER BY score DESC, concept_id
            LIMIT :limit
        """)

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                query, {"term": term, "domain": domain, "vocabulary": vocabulary, "limit": limit}
            )
            return [
                OmopConcept(
                    concept_id=row.concept_id,
                    concept_name=row.concept_name,
                    domain_id=row.domain_id,
                    vocabulary_id=row.vocabulary_id,
                    concept_class_id=row.concept_class_id,
                    standard_concept=row.standard_concept,
                    concept_code=row.concept_code,
                    similarity_score=row.score,
                )
                for row in result
            ]

    def _fuzzy_match_synonym(
        self,
        term: str,
        domain: Optional[str],
        vocabulary: Optional[str],
        limit: int,
    ) -> List[OmopConcept]:
        """Find fuzzy matches on concept synonyms."""
        query = text("""
            SELECT DISTINCT
                c.concept_id,
                c.concept_name,
                c.domain_id,
                c.vocabulary_id,
                c.concept_class_id,
                c.standard_concept,
                c.concept_code,
                MAX(similarity(cs.concept_synonym_name, :term)) AS score
            FROM concept c
            JOIN concept_synonym cs ON c.concept_id = cs.concept_id
            WHERE c.standard_concept = 'S'
              AND c.invalid_reason IS NULL
              AND (:domain IS NULL OR c.domain_id = :domain)
              AND (:vocabulary IS NULL OR c.vocabulary_id = :vocabulary)
              AND similarity(cs.concept_synonym_name, :term) > 0.3
            GROUP BY c.concept_id, c.concept_name, c.domain_id, c.vocabulary_id, 
                     c.concept_class_id, c.standard_concept, c.concept_code
            ORDER BY score DESC, c.concept_id
            LIMIT :limit
        """)

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                query, {"term": term, "domain": domain, "vocabulary": vocabulary, "limit": limit}
            )
            return [
                OmopConcept(
                    concept_id=row.concept_id,
                    concept_name=row.concept_name,
                    domain_id=row.domain_id,
                    vocabulary_id=row.vocabulary_id,
                    concept_class_id=row.concept_class_id,
                    standard_concept=row.standard_concept,
                    concept_code=row.concept_code,
                    similarity_score=row.score,
                )
                for row in result
            ]

    def get_concept_by_code(
        self, code: str, vocabulary_id: str
    ) -> Optional[OmopConcept]:
        """Get concept by external code (e.g., SNOMED code).

        Args:
            code: External concept code (e.g., "201826" for SNOMED)
            vocabulary_id: Vocabulary system (e.g., "SNOMED", "RxNorm")

        Returns:
            OmopConcept if found, None otherwise
        """
        query = text("""
            SELECT 
                concept_id,
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                concept_code
            FROM concept
            WHERE concept_code = :code
              AND vocabulary_id = :vocabulary_id
              AND invalid_reason IS NULL
            LIMIT 1
        """)

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(query, {"code": code, "vocabulary_id": vocabulary_id})
            row = result.fetchone()
            if row:
                return OmopConcept(
                    concept_id=row.concept_id,
                    concept_name=row.concept_name,
                    domain_id=row.domain_id,
                    vocabulary_id=row.vocabulary_id,
                    concept_class_id=row.concept_class_id,
                    standard_concept=row.standard_concept,
                    concept_code=row.concept_code,
                )
            return None

    def get_concept_synonyms(self, concept_id: int) -> List[str]:
        """Get all synonyms for a concept.

        Args:
            concept_id: OMOP concept_id

        Returns:
            List of synonym strings
        """
        query = text("""
            SELECT DISTINCT concept_synonym_name
            FROM concept_synonym
            WHERE concept_id = :concept_id
            ORDER BY concept_synonym_name
        """)

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(query, {"concept_id": concept_id})
            return [row.concept_synonym_name for row in result]

    def close(self):
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
