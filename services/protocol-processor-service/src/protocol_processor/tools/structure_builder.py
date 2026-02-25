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

from protocol_processor.prompts import render_template
from protocol_processor.schemas.structure import (
    ExpressionNode,
    LogicDetectionResponse,
    LogicNode,
    StructuredCriterionTree,
)
from protocol_processor.tools.gemini_utils import (
    create_structured_llm,
    parse_structured_output,
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


def _extract_value_fields(fm: dict[str, Any]) -> tuple[str, str | None]:
    """Extract flat value string and unit from a field mapping.

    Handles both legacy flat strings and typed value dicts produced by
    ``FieldMappingValue.model_dump(exclude_none=True)``.

    Args:
        fm: Field mapping dict with ``value`` (str or dict) and optional ``unit``.

    Returns:
        Tuple of (value_str, unit) where value_str is always a string
        (possibly empty) and unit is the resolved unit string or None.
    """
    raw_value = fm.get("value", "")
    top_unit = fm.get("unit")

    if isinstance(raw_value, dict):
        vtype = raw_value.get("type", "standard")
        unit = raw_value.get("unit") or top_unit

        if vtype == "range":
            v_min = raw_value.get("min", "")
            v_max = raw_value.get("max", "")
            if v_min and v_max:
                return f"{v_min}-{v_max}", unit
            return v_min or v_max or "", unit
        elif vtype == "temporal":
            return raw_value.get("duration", ""), unit
        else:  # standard
            return raw_value.get("value", ""), unit

    # Legacy: flat string
    if not isinstance(raw_value, str):
        raw_value = str(raw_value) if raw_value is not None else ""
    return raw_value, top_unit


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

    structured_llm = create_structured_llm(LogicDetectionResponse)
    if structured_llm is None:
        return None

    try:
        # Build field mapping descriptions for context
        mapping_lines = []
        for i, fm in enumerate(field_mappings):
            entity = fm.get("entity", "?")
            relation = fm.get("relation", "?")
            val_str, unit_str = _extract_value_fields(fm)
            value = val_str or "?"
            unit_suffix = f" {unit_str}" if unit_str else ""
            mapping_lines.append(f"  [{i}] {entity} {relation} {value}{unit_suffix}")
        mappings_text = "\n".join(mapping_lines)

        prompt = render_template(
            "logic_detection.jinja2",
            criterion_text=criterion_text,
            mappings_text=mappings_text,
            max_index=len(field_mappings) - 1,
        )

        from protocol_processor.tracing import llm_span

        with llm_span("gemini_logic_detection") as llm:
            llm.set_request(prompt)
            result = await structured_llm.ainvoke(prompt)
            llm.set_response(str(result))

        response = parse_structured_output(result, LogicDetectionResponse)

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
    value_str, raw_unit = _extract_value_fields(fm)
    value_numeric, value_text = _parse_value(value_str)

    relation = fm.get("relation", "has")
    negation = relation.upper() == "NOT" if relation else False

    ucum_code, unit_concept_id = normalize_unit(raw_unit)

    value_concept_id: int | None = None
    entity_text = fm.get("entity")

    # Ordinal-first: check if entity is an ordinal scale
    ordinal_result = normalize_ordinal_value(value_str, entity_text)
    if ordinal_result is not None:
        ordinal_value_cid, ordinal_unit_cid = ordinal_result
        value_concept_id = ordinal_value_cid
        if ordinal_unit_cid is not None:
            unit_concept_id = ordinal_unit_cid
            ucum_code = "{score}"
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
        unit_ucum_code=ucum_code,
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
) -> tuple[ExpressionNode, str]:
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
        Tuple of (ExpressionNode for JSONB storage, node's DB record ID).
    """
    if node.node_type == "ATOMIC":
        idx = node.field_mapping_index or 0
        atomic = atomic_records[idx]
        fm = field_mappings[idx]
        val_str, unit_str = _extract_value_fields(fm)
        expr = ExpressionNode(
            type="ATOMIC",
            atomic_criterion_id=atomic.id,
            entity=fm.get("entity"),
            relation=fm.get("relation"),
            value=val_str or None,
            unit=unit_str,
            omop_concept_id=fm.get("omop_concept_id"),
        )
        return expr, atomic.id

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
        child_expr, child_db_id = _build_tree_from_logic(
            child,
            field_mappings,
            atomic_records,
            criterion_id,
            protocol_id,
            inclusion_exclusion,
            session,
        )
        children_nodes.append(child_expr)

        child_type = "atomic" if child.node_type == "ATOMIC" else "composite"
        rel = CriterionRelationship(
            parent_criterion_id=composite.id,
            child_criterion_id=child_db_id,
            child_type=child_type,
            child_sequence=seq,
        )
        session.add(rel)

    expr = ExpressionNode(
        type=node.node_type,
        children=children_nodes,
    )
    return expr, composite.id


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
        root_expr, _ = _build_tree_from_logic(
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
        val_str, unit_str = _extract_value_fields(fm)
        root_expr = ExpressionNode(
            type="ATOMIC",
            atomic_criterion_id=atomic_records[0].id,
            entity=fm.get("entity"),
            relation=fm.get("relation"),
            value=val_str or None,
            unit=unit_str,
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
        val_str, unit_str = _extract_value_fields(fm)
        children.append(
            ExpressionNode(
                type="ATOMIC",
                atomic_criterion_id=atomic.id,
                entity=fm.get("entity"),
                relation=fm.get("relation"),
                value=val_str or None,
                unit=unit_str,
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
