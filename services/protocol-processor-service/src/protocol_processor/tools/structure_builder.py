"""Structure builder tool for expression tree construction.

Phase 2: Detects AND/OR/NOT logic in criterion text using Gemini,
then builds normalized atomic_criteria/composite_criteria records
and returns a StructuredCriterionTree for JSONB storage.

Follows the field_mapper.py pattern: Gemini structured output with
graceful fallback on failure.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.models import AtomicCriterion, CompositeCriterion, CriterionRelationship
from sqlmodel import Session

from protocol_processor.schemas.structure import (
    ExpressionNode,
    LogicDetectionResponse,
    LogicNode,
    StructuredCriterionTree,
)
from protocol_processor.tools.unit_normalizer import (
    normalize_ordinal_value,
    normalize_unit,
    normalize_value,
)

logger = logging.getLogger(__name__)

# Map pipeline entity_type to OMOP-style entity_domain.
# Used when field_mappings don't include an explicit entity_domain.
_ENTITY_TYPE_TO_DOMAIN: dict[str, str] = {
    "Condition": "condition",
    "Medication": "drug",
    "Lab_Value": "measurement",
    "Procedure": "procedure",
    "Demographic": "demographics",
    "Other": "observation",
}


def _parse_value(
    raw_value: str,
) -> tuple[float | None, str | None]:
    """Parse a value string into numeric or text.

    Tries float conversion first. If it succeeds, returns (numeric, None).
    Otherwise returns (None, text).

    Args:
        raw_value: Raw value string from field_mapping.

    Returns:
        Tuple of (value_numeric, value_text) — one is always None.
    """
    try:
        return (float(raw_value), None)
    except (ValueError, TypeError):
        return (None, raw_value)


async def detect_logic_structure(
    criterion_text: str,
    field_mappings: list[dict[str, Any]],
) -> LogicDetectionResponse | None:
    """Detect AND/OR/NOT logic structure in criterion text using Gemini.

    Skips LLM call if there's only 1 field_mapping (single atom, no logic).
    Returns None on any failure (triggers fallback in caller).

    Args:
        criterion_text: Full criterion text.
        field_mappings: List of field_mapping dicts from conditions.

    Returns:
        LogicDetectionResponse with the detected tree, or None on failure.
    """
    if len(field_mappings) <= 1:
        return None

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.warning(
            "GOOGLE_API_KEY not set — skipping logic detection for '%s'",
            criterion_text[:50],
        )
        return None

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        gemini = ChatGoogleGenerativeAI(
            model=gemini_model_name,
            google_api_key=google_api_key,
        )
        structured_llm = gemini.with_structured_output(LogicDetectionResponse)

        # Build field mapping descriptions for context
        mapping_lines = []
        for i, fm in enumerate(field_mappings):
            entity = fm.get("entity", "?")
            relation = fm.get("relation", "?")
            value = fm.get("value", "?")
            unit = fm.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            mapping_lines.append(f"  [{i}] {entity} {relation} {value}{unit_str}")
        mappings_text = "\n".join(mapping_lines)

        prompt = (
            "You are a clinical trial protocol analyst. Analyze the logical"
            " structure of this eligibility criterion.\n\n"
            f"Criterion text: {criterion_text}\n\n"
            f"Field mappings (indexed):\n{mappings_text}\n\n"
            "Instructions:\n"
            "- Determine how the field mappings are logically connected\n"
            "- Use AND when all conditions must be met simultaneously\n"
            "- Use OR when any one condition suffices\n"
            "- Use NOT to negate a condition\n"
            "- Use ATOMIC for leaf nodes that reference a single"
            " field_mapping by index\n"
            "- Return a tree where the root is AND, OR, NOT, or ATOMIC\n"
            "- Every ATOMIC node must have field_mapping_index set to a"
            " valid index (0 to "
            f"{len(field_mappings) - 1})\n"
            "- Each field_mapping index should appear exactly once\n"
        )

        result = structured_llm.invoke(prompt)
        if isinstance(result, dict):
            response = LogicDetectionResponse.model_validate(result)
        else:
            response = result  # type: ignore[assignment]

        # Validate all field_mapping_index values are in range
        if not _validate_logic_tree(response.root, len(field_mappings)):
            logger.warning(
                "Logic tree validation failed for '%s' — invalid indices",
                criterion_text[:50],
            )
            return None

        return response

    except Exception as e:
        logger.warning(
            "Logic detection failed for '%s': %s",
            criterion_text[:50],
            e,
            exc_info=True,
        )
        return None


def _validate_logic_tree(node: LogicNode, num_mappings: int) -> bool:
    """Validate that all field_mapping_index values are in range.

    Args:
        node: Root LogicNode to validate.
        num_mappings: Number of field_mappings (valid range: 0..num_mappings-1).

    Returns:
        True if all indices are valid, False otherwise.
    """
    if node.node_type == "ATOMIC":
        if node.field_mapping_index is None:
            return False
        return 0 <= node.field_mapping_index < num_mappings
    if node.children:
        return all(_validate_logic_tree(child, num_mappings) for child in node.children)
    # Non-ATOMIC with no children is invalid (AND/OR/NOT need children)
    return False


def _create_atomic_from_mapping(
    fm: dict[str, Any],
    criterion_id: str,
    protocol_id: str,
    inclusion_exclusion: str,
    criterion_text: str,
) -> AtomicCriterion:
    """Create an AtomicCriterion record from a field_mapping dict.

    Args:
        fm: Field mapping dict with entity, relation, value, unit keys.
        criterion_id: FK to criteria table.
        protocol_id: FK to protocol table.
        inclusion_exclusion: "inclusion" or "exclusion".
        criterion_text: Original criterion text.

    Returns:
        AtomicCriterion instance (not yet added to session).
    """
    value_str = fm.get("value", "")
    value_numeric, value_text = _parse_value(value_str)

    relation = fm.get("relation", "has")
    negation = relation.upper() == "NOT" if relation else False

    raw_unit = fm.get("unit")
    _, unit_concept_id = normalize_unit(raw_unit)

    value_concept_id: int | None = None
    entity_text = fm.get("entity")
    raw_value = str(fm.get("value", ""))

    # Ordinal-first: check if entity is an ordinal scale
    ordinal_result = normalize_ordinal_value(raw_value, entity_text)
    if ordinal_result is not None:
        ordinal_value_cid, ordinal_unit_cid = ordinal_result
        value_concept_id = ordinal_value_cid
        if ordinal_unit_cid is not None:
            unit_concept_id = ordinal_unit_cid
    elif value_text and value_numeric is None:
        _, value_concept_id = normalize_value(value_text)

    # Derive entity_domain from entity_type when not explicitly provided
    entity_domain = fm.get("entity_domain")
    if not entity_domain:
        entity_type = fm.get("entity_type", "")
        entity_domain = _ENTITY_TYPE_TO_DOMAIN.get(entity_type)

    return AtomicCriterion(
        criterion_id=criterion_id,
        protocol_id=protocol_id,
        inclusion_exclusion=inclusion_exclusion,
        entity_concept_id=fm.get("entity_concept_id"),
        entity_concept_system=fm.get("entity_concept_system"),
        omop_concept_id=fm.get("omop_concept_id"),
        entity_domain=entity_domain,
        relation_operator=relation,
        value_numeric=value_numeric,
        value_text=value_text,
        unit_text=raw_unit,
        unit_concept_id=unit_concept_id,
        value_concept_id=value_concept_id,
        negation=negation,
        original_text=criterion_text,
        confidence_score=fm.get("confidence_score"),
    )


def _build_tree_from_logic(
    node: LogicNode,
    field_mappings: list[dict[str, Any]],
    atomic_records: list[AtomicCriterion],
    criterion_id: str,
    protocol_id: str,
    inclusion_exclusion: str,
    session: Session,
) -> ExpressionNode:
    """Recursively build ExpressionNode tree and DB records from LogicNode.

    Creates CompositeCriterion and CriterionRelationship records for
    branch nodes. Leaf nodes reference already-created AtomicCriterion
    records by index.

    Args:
        node: Current LogicNode from LLM output.
        field_mappings: List of field_mapping dicts.
        atomic_records: Pre-created AtomicCriterion records (indexed).
        criterion_id: FK to criteria table.
        protocol_id: FK to protocol table.
        inclusion_exclusion: "inclusion" or "exclusion".
        session: Active SQLModel session.

    Returns:
        ExpressionNode for JSONB storage.
    """
    if node.node_type == "ATOMIC":
        idx = node.field_mapping_index or 0
        atomic = atomic_records[idx]
        fm = field_mappings[idx]
        return ExpressionNode(
            type="ATOMIC",
            atomic_criterion_id=atomic.id,
            entity=fm.get("entity"),
            relation=fm.get("relation"),
            value=fm.get("value"),
            unit=fm.get("unit"),
            omop_concept_id=fm.get("omop_concept_id"),
        )

    # Branch node: create CompositeCriterion
    composite = CompositeCriterion(
        criterion_id=criterion_id,
        protocol_id=protocol_id,
        inclusion_exclusion=inclusion_exclusion,
        logic_operator=node.node_type,
    )
    session.add(composite)
    session.flush()

    children_nodes: list[ExpressionNode] = []
    for seq, child in enumerate(node.children or []):
        child_expr = _build_tree_from_logic(
            child,
            field_mappings,
            atomic_records,
            criterion_id,
            protocol_id,
            inclusion_exclusion,
            session,
        )
        children_nodes.append(child_expr)

        # Create relationship edge
        if child.node_type == "ATOMIC":
            child_id = child_expr.atomic_criterion_id or ""
            child_type = "atomic"
        else:
            # For composite children, the CompositeCriterion was just
            # created in the recursive call — we need its ID.
            # We stored it in the ExpressionNode via a convention:
            # non-ATOMIC nodes don't have atomic_criterion_id set.
            # Query the last composite created for this criterion.
            child_id = _find_last_composite_id(session, criterion_id, child.node_type)
            child_type = "composite"

        rel = CriterionRelationship(
            parent_criterion_id=composite.id,
            child_criterion_id=child_id,
            child_type=child_type,
            child_sequence=seq,
        )
        session.add(rel)

    return ExpressionNode(
        type=node.node_type,
        children=children_nodes,
    )


def _find_last_composite_id(
    session: Session, criterion_id: str, logic_operator: str
) -> str:
    """Find the most recently added composite criterion ID.

    This is used during recursive tree building to link parent→child
    composite relationships.

    Args:
        session: Active SQLModel session.
        criterion_id: FK to criteria table.
        logic_operator: Logic operator of the child composite.

    Returns:
        ID of the most recent CompositeCriterion matching the criteria.
    """
    from sqlmodel import select

    stmt = (
        select(CompositeCriterion)
        .where(CompositeCriterion.criterion_id == criterion_id)
        .where(CompositeCriterion.logic_operator == logic_operator)
        .order_by(CompositeCriterion.created_at.desc())  # type: ignore[attr-defined]
    )
    result = session.exec(stmt).first()
    return result.id if result else ""


async def build_expression_tree(
    criterion_text: str,
    field_mappings: list[dict[str, Any]],
    criterion_id: str,
    protocol_id: str,
    inclusion_exclusion: str,
    session: Session,
) -> StructuredCriterionTree:
    """Build an expression tree from criterion field_mappings.

    Two-pass approach:
    1. LLM pass: call detect_logic_structure() for AND/OR/NOT detection
    2. Fallback: if LLM fails or single mapping, AND-of-all-atomics

    Creates AtomicCriterion records for each field_mapping, plus
    CompositeCriterion + CriterionRelationship for tree structure.

    Args:
        criterion_text: Full criterion text.
        field_mappings: List of field_mapping dicts from conditions.
        criterion_id: FK to criteria table.
        protocol_id: FK to protocol table.
        inclusion_exclusion: "inclusion" or "exclusion".
        session: Active SQLModel session (records are added but not committed).

    Returns:
        StructuredCriterionTree for JSONB storage in criteria.structured_criterion.
    """
    gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    # Create AtomicCriterion records for each field_mapping
    atomic_records: list[AtomicCriterion] = []
    for fm in field_mappings:
        atomic = _create_atomic_from_mapping(
            fm, criterion_id, protocol_id, inclusion_exclusion, criterion_text
        )
        session.add(atomic)
        session.flush()
        atomic_records.append(atomic)

    # Pass 1: LLM logic detection
    logic_response = await detect_logic_structure(criterion_text, field_mappings)

    if logic_response is not None:
        # Build tree from LLM-detected structure
        root_expr = _build_tree_from_logic(
            logic_response.root,
            field_mappings,
            atomic_records,
            criterion_id,
            protocol_id,
            inclusion_exclusion,
            session,
        )
        return StructuredCriterionTree(
            root=root_expr,
            structure_confidence="llm",
            structure_model=gemini_model_name,
        )

    # Pass 2: Fallback — AND-of-all-atomics (or single ATOMIC)
    if len(atomic_records) == 1:
        fm = field_mappings[0]
        root_expr = ExpressionNode(
            type="ATOMIC",
            atomic_criterion_id=atomic_records[0].id,
            entity=fm.get("entity"),
            relation=fm.get("relation"),
            value=fm.get("value"),
            unit=fm.get("unit"),
            omop_concept_id=fm.get("omop_concept_id"),
        )
        return StructuredCriterionTree(
            root=root_expr,
            structure_confidence="fallback",
            structure_model=None,
        )

    # Multiple mappings, LLM failed → wrap in AND
    composite = CompositeCriterion(
        criterion_id=criterion_id,
        protocol_id=protocol_id,
        inclusion_exclusion=inclusion_exclusion,
        logic_operator="AND",
        original_text=criterion_text,
    )
    session.add(composite)
    session.flush()

    children: list[ExpressionNode] = []
    for seq, (atomic, fm) in enumerate(zip(atomic_records, field_mappings)):
        children.append(
            ExpressionNode(
                type="ATOMIC",
                atomic_criterion_id=atomic.id,
                entity=fm.get("entity"),
                relation=fm.get("relation"),
                value=fm.get("value"),
                unit=fm.get("unit"),
                omop_concept_id=fm.get("omop_concept_id"),
            )
        )
        rel = CriterionRelationship(
            parent_criterion_id=composite.id,
            child_criterion_id=atomic.id,
            child_type="atomic",
            child_sequence=seq,
        )
        session.add(rel)

    root_expr = ExpressionNode(type="AND", children=children)
    return StructuredCriterionTree(
        root=root_expr,
        structure_confidence="fallback",
        structure_model=None,
    )
