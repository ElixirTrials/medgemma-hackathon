"""Shared data loader for protocol export builders.

Loads all structured criteria data for a protocol into a single
dataclass consumed by the CIRCE, FHIR Group, and evaluation SQL builders.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.models import (
    AtomicCriterion,
    CompositeCriterion,
    Criteria,
    CriteriaBatch,
    CriterionRelationship,
    Protocol,
)
from sqlmodel import Session, select


@dataclass
class ProtocolExportData:
    """All structured criteria data needed by export builders."""

    protocol: Protocol
    criteria: list[Criteria]
    atomics: list[AtomicCriterion]
    composites: list[CompositeCriterion]
    relationships: list[CriterionRelationship]
    atomics_by_id: dict[str, AtomicCriterion] = field(default_factory=dict)
    composites_by_id: dict[str, CompositeCriterion] = field(default_factory=dict)
    children_by_parent: dict[str, list[CriterionRelationship]] = field(
        default_factory=dict
    )
    criteria_by_id: dict[str, Criteria] = field(default_factory=dict)


def load_protocol_export_data(
    db: Session, protocol_id: str
) -> ProtocolExportData | None:
    """Load all export data for a protocol.

    Queries the active (non-archived) batch and all associated
    criteria, atomic criteria, composite criteria, and relationships.

    Returns:
        ProtocolExportData if the protocol exists and has structured
        criteria, None otherwise.
    """
    protocol = db.get(Protocol, protocol_id)
    if protocol is None:
        return None

    # Find the active (non-archived) batch
    batch = db.exec(
        select(CriteriaBatch)
        .where(CriteriaBatch.protocol_id == protocol_id)
        .where(CriteriaBatch.is_archived == False)  # noqa: E712
        .order_by(CriteriaBatch.created_at.desc())  # type: ignore[union-attr,attr-defined]
    ).first()
    if batch is None:
        return None

    # Load criteria from active batch
    criteria = list(
        db.exec(select(Criteria).where(Criteria.batch_id == batch.id)).all()
    )
    if not criteria:
        return None

    # Load atomics and composites for this protocol
    atomics = list(
        db.exec(
            select(AtomicCriterion).where(AtomicCriterion.protocol_id == protocol_id)
        ).all()
    )
    composites = list(
        db.exec(
            select(CompositeCriterion).where(
                CompositeCriterion.protocol_id == protocol_id
            )
        ).all()
    )

    # Load relationships for all composites
    composite_ids = [c.id for c in composites]
    relationships: list[CriterionRelationship] = []
    if composite_ids:
        relationships = list(
            db.exec(
                select(CriterionRelationship).where(
                    CriterionRelationship.parent_criterion_id.in_(  # type: ignore[union-attr,attr-defined]
                        composite_ids
                    )
                )
            ).all()
        )

    # Build lookup dicts
    atomics_by_id = {a.id: a for a in atomics}
    composites_by_id = {c.id: c for c in composites}
    criteria_by_id = {c.id: c for c in criteria}

    children_by_parent: dict[str, list[CriterionRelationship]] = {}
    for rel in relationships:
        children_by_parent.setdefault(rel.parent_criterion_id, []).append(rel)
    # Sort children by child_sequence
    for children in children_by_parent.values():
        children.sort(key=lambda r: r.child_sequence)

    return ProtocolExportData(
        protocol=protocol,
        criteria=criteria,
        atomics=atomics,
        composites=composites,
        relationships=relationships,
        atomics_by_id=atomics_by_id,
        composites_by_id=composites_by_id,
        children_by_parent=children_by_parent,
        criteria_by_id=criteria_by_id,
    )
