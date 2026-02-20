"""Tests for protocol export endpoints and builder functions.

Covers CIRCE, FHIR Group, and evaluation SQL export builders (unit)
and their FastAPI endpoints (integration).
"""

from uuid import uuid4

from shared.models import (
    AtomicCriterion,
    CompositeCriterion,
    Criteria,
    CriteriaBatch,
    CriterionRelationship,
    Protocol,
)

from api_service.exporters import ProtocolExportData
from api_service.exporters.circe_builder import build_circe_export
from api_service.exporters.evaluation_sql_builder import build_evaluation_sql
from api_service.exporters.fhir_group_builder import build_fhir_group_export

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_protocol(db_session, **overrides):
    """Create a test Protocol."""
    defaults = {
        "id": str(uuid4()),
        "title": "Test Protocol",
        "file_uri": "local://test.pdf",
        "status": "complete",
    }
    defaults.update(overrides)
    p = Protocol(**defaults)
    db_session.add(p)
    db_session.flush()
    return p


def _make_batch(db_session, protocol_id, **overrides):
    """Create a test CriteriaBatch."""
    defaults = {
        "id": str(uuid4()),
        "protocol_id": protocol_id,
        "status": "pending_review",
        "is_archived": False,
    }
    defaults.update(overrides)
    b = CriteriaBatch(**defaults)
    db_session.add(b)
    db_session.flush()
    return b


def _make_criterion(db_session, batch_id, **overrides):
    """Create a test Criteria record."""
    defaults = {
        "id": str(uuid4()),
        "batch_id": batch_id,
        "criteria_type": "inclusion",
        "text": "HbA1c >= 7%",
    }
    defaults.update(overrides)
    c = Criteria(**defaults)
    db_session.add(c)
    db_session.flush()
    return c


def _make_atomic(db_session, criterion_id, protocol_id, **overrides):
    """Create a test AtomicCriterion."""
    defaults = {
        "id": str(uuid4()),
        "criterion_id": criterion_id,
        "protocol_id": protocol_id,
        "inclusion_exclusion": "inclusion",
        "entity_concept_id": "4532345",
        "entity_concept_system": "snomed",
        "omop_concept_id": "3004410",
        "entity_domain": "measurement",
        "relation_operator": ">=",
        "value_numeric": 7.0,
        "unit_text": "%",
        "unit_concept_id": 8554,
        "original_text": "HbA1c >= 7%",
        "negation": False,
    }
    defaults.update(overrides)
    a = AtomicCriterion(**defaults)
    db_session.add(a)
    db_session.flush()
    return a


def _make_composite(db_session, criterion_id, protocol_id, **overrides):
    """Create a test CompositeCriterion."""
    defaults = {
        "id": str(uuid4()),
        "criterion_id": criterion_id,
        "protocol_id": protocol_id,
        "inclusion_exclusion": "inclusion",
        "logic_operator": "AND",
    }
    defaults.update(overrides)
    c = CompositeCriterion(**defaults)
    db_session.add(c)
    db_session.flush()
    return c


def _make_relationship(db_session, parent_id, child_id, child_type, seq=0):
    """Create a test CriterionRelationship."""
    r = CriterionRelationship(
        parent_criterion_id=parent_id,
        child_criterion_id=child_id,
        child_type=child_type,
        child_sequence=seq,
    )
    db_session.add(r)
    db_session.flush()
    return r


def _build_simple_export_data(
    db_session,
    criteria_type="inclusion",
    negation=False,
    entity_domain="measurement",
    with_tree=True,
):
    """Build a simple ProtocolExportData with one criterion and one atomic."""
    proto = _make_protocol(db_session)
    batch = _make_batch(db_session, proto.id)
    atomic_id = str(uuid4())

    tree = None
    if with_tree:
        tree = {
            "type": "ATOMIC",
            "atomic_criterion_id": atomic_id,
        }

    crit = _make_criterion(
        db_session,
        batch.id,
        criteria_type=criteria_type,
        structured_criterion=tree,
    )
    atomic = _make_atomic(
        db_session,
        crit.id,
        proto.id,
        id=atomic_id,
        inclusion_exclusion=criteria_type,
        negation=negation,
        entity_domain=entity_domain,
    )
    db_session.commit()

    return ProtocolExportData(
        protocol=proto,
        criteria=[crit],
        atomics=[atomic],
        composites=[],
        relationships=[],
        atomics_by_id={atomic.id: atomic},
        criteria_by_id={crit.id: crit},
    )


def _build_and_or_export_data(db_session):
    """Build export data with AND containing two atomics and an OR group."""
    proto = _make_protocol(db_session)
    batch = _make_batch(db_session, proto.id)

    a1_id = str(uuid4())
    a2_id = str(uuid4())
    a3_id = str(uuid4())

    tree = {
        "type": "AND",
        "children": [
            {"type": "ATOMIC", "atomic_criterion_id": a1_id},
            {
                "type": "OR",
                "children": [
                    {"type": "ATOMIC", "atomic_criterion_id": a2_id},
                    {"type": "ATOMIC", "atomic_criterion_id": a3_id},
                ],
            },
        ],
    }

    crit = _make_criterion(db_session, batch.id, structured_criterion=tree)

    a1 = _make_atomic(
        db_session,
        crit.id,
        proto.id,
        id=a1_id,
        omop_concept_id="201826",
        entity_domain="condition",
        relation_operator=None,
        value_numeric=None,
        unit_concept_id=None,
        original_text="Type 2 diabetes",
    )
    a2 = _make_atomic(
        db_session,
        crit.id,
        proto.id,
        id=a2_id,
        omop_concept_id="3004410",
        entity_domain="measurement",
        relation_operator=">=",
        value_numeric=7.0,
        original_text="HbA1c >= 7%",
    )
    a3 = _make_atomic(
        db_session,
        crit.id,
        proto.id,
        id=a3_id,
        omop_concept_id="3000963",
        entity_domain="measurement",
        relation_operator=">=",
        value_numeric=126.0,
        original_text="FPG >= 126 mg/dL",
    )
    db_session.commit()

    return ProtocolExportData(
        protocol=proto,
        criteria=[crit],
        atomics=[a1, a2, a3],
        composites=[],
        relationships=[],
        atomics_by_id={a1.id: a1, a2.id: a2, a3.id: a3},
        criteria_by_id={crit.id: crit},
    )


# ---------------------------------------------------------------------------
# CIRCE Builder Unit Tests
# ---------------------------------------------------------------------------


class TestCirceBuilder:
    """Unit tests for the CIRCE CohortExpression builder."""

    def test_concept_sets_created(self, db_session):
        data = _build_simple_export_data(db_session)
        result = build_circe_export(data)
        assert len(result["ConceptSets"]) == 1
        cs = result["ConceptSets"][0]
        assert cs["expression"]["items"][0]["concept"]["CONCEPT_ID"] == 3004410
        assert cs["expression"]["items"][0]["includeDescendants"] is True

    def test_domain_mapping_measurement(self, db_session):
        data = _build_simple_export_data(db_session, entity_domain="measurement")
        result = build_circe_export(data)
        criteria_list = result["AdditionalCriteria"]["CriteriaList"]
        assert len(criteria_list) == 1
        assert "Measurement" in criteria_list[0]["Criteria"]

    def test_domain_mapping_condition(self, db_session):
        data = _build_simple_export_data(db_session, entity_domain="condition")
        result = build_circe_export(data)
        criteria_list = result["AdditionalCriteria"]["CriteriaList"]
        assert "ConditionOccurrence" in criteria_list[0]["Criteria"]

    def test_value_and_unit_filter(self, db_session):
        data = _build_simple_export_data(db_session)
        result = build_circe_export(data)
        criteria_entry = result["AdditionalCriteria"]["CriteriaList"][0]
        val = criteria_entry["Criteria"]["ValueAsNumber"]
        assert val["Value"] == 7.0
        assert val["Op"] == "gte"
        assert val["UnitConceptId"] == 8554

    def test_negation_sets_occurrence_zero(self, db_session):
        data = _build_simple_export_data(db_session, negation=True)
        result = build_circe_export(data)
        criteria_entry = result["AdditionalCriteria"]["CriteriaList"][0]
        occ = criteria_entry["Criteria"]["OccurrenceCount"]
        assert occ["Value"] == 0
        assert occ["Op"] == "eq"

    def test_exclusion_goes_to_censoring(self, db_session):
        data = _build_simple_export_data(db_session, criteria_type="exclusion")
        result = build_circe_export(data)
        assert len(result["CensoringCriteria"]) == 1
        assert len(result["AdditionalCriteria"]["CriteriaList"]) == 0

    def test_and_or_groups(self, db_session):
        data = _build_and_or_export_data(db_session)
        result = build_circe_export(data)
        criteria_list = result["AdditionalCriteria"]["CriteriaList"]
        assert len(criteria_list) == 1
        group = criteria_list[0]
        assert group["Type"] == "ALL"
        # AND group: first child is atomic, second is OR group
        assert len(group["CriteriaList"]) == 2
        or_group = group["CriteriaList"][1]
        assert or_group["Type"] == "ANY"
        assert len(or_group["CriteriaList"]) == 2

    def test_omop_concept_id_precedence(self, db_session):
        """omop_concept_id should be preferred over entity_concept_id."""
        data = _build_simple_export_data(db_session)
        result = build_circe_export(data)
        # omop_concept_id is 3004410, entity_concept_id is 4532345
        concept = result["ConceptSets"][0]["expression"]["items"][0]["concept"]
        assert concept["CONCEPT_ID"] == 3004410

    def test_demographics_uses_demographic_criteria(self, db_session):
        """Demographics domain should produce DemographicCriteria, not a ConceptSet."""
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            entity_domain="demographics",
            relation_operator=">=",
            value_numeric=18.0,
            unit_text="years",
            unit_concept_id=None,
            original_text="Age >= 18 years",
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[db_session.get(AtomicCriterion, a_id)],
            composites=[],
            relationships=[],
            atomics_by_id={a_id: db_session.get(AtomicCriterion, a_id)},
            criteria_by_id={crit.id: crit},
        )
        result = build_circe_export(data)
        # No ConceptSets for demographics
        assert len(result["ConceptSets"]) == 0
        criteria_list = result["AdditionalCriteria"]["CriteriaList"]
        assert len(criteria_list) == 1
        entry = criteria_list[0]
        assert "DemographicCriteria" in entry["Criteria"]
        age = entry["Criteria"]["DemographicCriteria"]["Age"]
        assert age["Value"] == 18
        assert age["Op"] == "gte"

    def test_empty_protocol_no_crash(self, db_session):
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        crit = _make_criterion(db_session, batch.id, structured_criterion=None)
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[],
            composites=[],
            relationships=[],
            atomics_by_id={},
            criteria_by_id={crit.id: crit},
        )
        result = build_circe_export(data)
        assert result["ConceptSets"] == []


# ---------------------------------------------------------------------------
# FHIR Group Builder Unit Tests
# ---------------------------------------------------------------------------


class TestFhirGroupBuilder:
    """Unit tests for the FHIR Group resource builder."""

    def test_characteristics_created(self, db_session):
        data = _build_simple_export_data(db_session)
        result = build_fhir_group_export(data)
        assert result["resourceType"] == "Group"
        assert result["type"] == "person"
        assert len(result["characteristic"]) == 1

    def test_quantity_value(self, db_session):
        data = _build_simple_export_data(db_session)
        result = build_fhir_group_export(data)
        char = result["characteristic"][0]
        assert "valueQuantity" in char
        assert char["valueQuantity"]["value"] == 7.0
        assert char["valueQuantity"]["unit"] == "%"
        assert char["valueQuantity"]["comparator"] == "ge"

    def test_text_value(self, db_session):
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        atomic = _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            value_numeric=None,
            value_text="positive",
            relation_operator=None,
            unit_text=None,
            unit_concept_id=None,
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[atomic],
            composites=[],
            relationships=[],
            atomics_by_id={atomic.id: atomic},
            criteria_by_id={crit.id: crit},
        )
        result = build_fhir_group_export(data)
        char = result["characteristic"][0]
        assert "valueCodeableConcept" in char
        assert char["valueCodeableConcept"]["text"] == "positive"

    def test_exclusion_flag(self, db_session):
        data = _build_simple_export_data(db_session, criteria_type="exclusion")
        result = build_fhir_group_export(data)
        char = result["characteristic"][0]
        assert char["exclude"] is True

    def test_or_nesting(self, db_session):
        data = _build_and_or_export_data(db_session)
        result = build_fhir_group_export(data)
        chars = result["characteristic"]
        # AND at top: first child is flat atomic, second is OR nested group
        assert len(chars) == 2
        or_char = chars[1]
        assert "_contained" in or_char
        nested = or_char["_contained"]
        assert nested["resourceType"] == "Group"
        assert any(e["valueCode"] == "any-of" for e in nested.get("extension", []))

    def test_not_inverts_exclude(self, db_session):
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {
            "type": "NOT",
            "children": [
                {"type": "ATOMIC", "atomic_criterion_id": a_id},
            ],
        }
        crit = _make_criterion(
            db_session,
            batch.id,
            criteria_type="inclusion",
            structured_criterion=tree,
        )
        atomic = _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            negation=False,
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[atomic],
            composites=[],
            relationships=[],
            atomics_by_id={atomic.id: atomic},
            criteria_by_id={crit.id: crit},
        )
        result = build_fhir_group_export(data)
        # NOT on an inclusion criterion -> exclude=True
        char = result["characteristic"][0]
        assert char["exclude"] is True

    def test_system_uri_snomed(self, db_session):
        data = _build_simple_export_data(db_session)
        result = build_fhir_group_export(data)
        char = result["characteristic"][0]
        coding = char["code"]["coding"][0]
        assert coding["system"] == "http://snomed.info/sct"

    def test_demographics_uses_age_context_type(self, db_session):
        """Demographics domain should use usage-context-type|age, not SNOMED."""
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            entity_domain="demographics",
            relation_operator=">=",
            value_numeric=18.0,
            unit_text="years",
            unit_concept_id=None,
            original_text="Age >= 18 years",
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[db_session.get(AtomicCriterion, a_id)],
            composites=[],
            relationships=[],
            atomics_by_id={a_id: db_session.get(AtomicCriterion, a_id)},
            criteria_by_id={crit.id: crit},
        )
        result = build_fhir_group_export(data)
        char = result["characteristic"][0]
        coding = char["code"]["coding"][0]
        assert coding["system"] == (
            "http://terminology.hl7.org/CodeSystem/usage-context-type"
        )
        assert coding["code"] == "age"
        assert "valueQuantity" in char
        q = char["valueQuantity"]
        assert q["value"] == 18.0
        assert q["unit"] == "years"
        assert q["system"] == "http://unitsofmeasure.org"
        assert q["comparator"] == "ge"

    def test_system_uri_loinc(self, db_session):
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        atomic = _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            entity_concept_system="loinc",
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[atomic],
            composites=[],
            relationships=[],
            atomics_by_id={atomic.id: atomic},
            criteria_by_id={crit.id: crit},
        )
        result = build_fhir_group_export(data)
        coding = result["characteristic"][0]["code"]["coding"][0]
        assert coding["system"] == "http://loinc.org"


# ---------------------------------------------------------------------------
# Evaluation SQL Builder Unit Tests
# ---------------------------------------------------------------------------


class TestEvaluationSqlBuilder:
    """Unit tests for the OMOP CDM evaluation SQL generator."""

    def test_measurement_cte(self, db_session):
        data = _build_simple_export_data(db_session)
        sql = build_evaluation_sql(data)
        assert "measurement" in sql.lower()
        assert "value_as_number >= 7.0" in sql
        assert "unit_concept_id = 8554" in sql

    def test_condition_cte(self, db_session):
        data = _build_simple_export_data(db_session, entity_domain="condition")
        sql = build_evaluation_sql(data)
        assert "condition_occurrence" in sql
        assert "condition_concept_id" in sql

    def test_demographics_age_calc(self, db_session):
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        atomic = _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a_id,
            entity_domain="demographics",
            relation_operator=">=",
            value_numeric=18.0,
            unit_text=None,
            unit_concept_id=None,
        )
        db_session.commit()
        data = ProtocolExportData(
            protocol=proto,
            criteria=[crit],
            atomics=[atomic],
            composites=[],
            relationships=[],
            atomics_by_id={atomic.id: atomic},
            criteria_by_id={crit.id: crit},
        )
        sql = build_evaluation_sql(data)
        assert "year_of_birth" in sql
        assert ">= 18" in sql

    def test_exclusion_not_exists(self, db_session):
        data = _build_simple_export_data(db_session, criteria_type="exclusion")
        sql = build_evaluation_sql(data)
        assert "NOT EXISTS" in sql

    def test_negation_not_exists(self, db_session):
        data = _build_simple_export_data(db_session, negation=True)
        sql = build_evaluation_sql(data)
        assert "NOT EXISTS" in sql

    def test_eligibility_query_structure(self, db_session):
        data = _build_simple_export_data(db_session)
        sql = build_evaluation_sql(data)
        assert "SELECT p.person_id" in sql
        assert "FROM person p" in sql
        assert "WHERE EXISTS" in sql

    def test_concept_ancestor_join(self, db_session):
        data = _build_simple_export_data(db_session, entity_domain="condition")
        sql = build_evaluation_sql(data)
        assert "concept_ancestor" in sql
        assert "ancestor_concept_id" in sql
        assert "descendant_concept_id" in sql

    def test_empty_criteria_fallback(self, db_session):
        proto = _make_protocol(db_session)
        data = ProtocolExportData(
            protocol=proto,
            criteria=[],
            atomics=[],
            composites=[],
            relationships=[],
            atomics_by_id={},
            criteria_by_id={},
        )
        sql = build_evaluation_sql(data)
        assert "No structured criteria" in sql


# ---------------------------------------------------------------------------
# Integration Tests (via test_client)
# ---------------------------------------------------------------------------


class TestExportEndpoints:
    """Integration tests for export API endpoints."""

    def _setup_protocol_with_criteria(self, db_session):
        """Create a full protocol with structured criteria."""
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)
        a_id = str(uuid4())
        tree = {"type": "ATOMIC", "atomic_criterion_id": a_id}
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        _make_atomic(db_session, crit.id, proto.id, id=a_id)
        db_session.commit()
        return proto.id

    def test_circe_200(self, test_client, db_session):
        pid = self._setup_protocol_with_criteria(db_session)
        r = test_client.get(f"/protocols/{pid}/export/circe")
        assert r.status_code == 200
        data = r.json()
        assert "expression" in data
        assert "stats" in data
        assert data["stats"]["atomic_count"] == 1

    def test_fhir_group_200(self, test_client, db_session):
        pid = self._setup_protocol_with_criteria(db_session)
        r = test_client.get(f"/protocols/{pid}/export/fhir-group")
        assert r.status_code == 200
        data = r.json()
        assert "resource" in data
        assert data["resource"]["resourceType"] == "Group"
        assert data["stats"]["criteria_count"] == 1

    def test_evaluation_sql_200(self, test_client, db_session):
        pid = self._setup_protocol_with_criteria(db_session)
        r = test_client.get(f"/protocols/{pid}/export/evaluation-sql")
        assert r.status_code == 200
        assert "SELECT p.person_id" in r.text

    def test_circe_404_unknown_protocol(self, test_client):
        r = test_client.get(f"/protocols/{uuid4()}/export/circe")
        assert r.status_code == 404

    def test_fhir_404_unknown_protocol(self, test_client):
        r = test_client.get(f"/protocols/{uuid4()}/export/fhir-group")
        assert r.status_code == 404

    def test_sql_404_unknown_protocol(self, test_client):
        r = test_client.get(f"/protocols/{uuid4()}/export/evaluation-sql")
        assert r.status_code == 404

    def test_404_no_structured_criteria(self, test_client, db_session):
        """Protocol exists but batch has no criteria -> 404."""
        proto = _make_protocol(db_session)
        _make_batch(db_session, proto.id)
        db_session.commit()
        r = test_client.get(f"/protocols/{proto.id}/export/circe")
        assert r.status_code == 404

    def test_stats_match_data(self, test_client, db_session):
        """Response stats should reflect actual data counts."""
        proto = _make_protocol(db_session)
        batch = _make_batch(db_session, proto.id)

        a1_id = str(uuid4())
        a2_id = str(uuid4())
        tree = {
            "type": "AND",
            "children": [
                {"type": "ATOMIC", "atomic_criterion_id": a1_id},
                {"type": "ATOMIC", "atomic_criterion_id": a2_id},
            ],
        }
        crit = _make_criterion(db_session, batch.id, structured_criterion=tree)
        comp = _make_composite(db_session, crit.id, proto.id)
        _make_atomic(db_session, crit.id, proto.id, id=a1_id)
        _make_atomic(
            db_session,
            crit.id,
            proto.id,
            id=a2_id,
            omop_concept_id="201826",
            entity_domain="condition",
        )
        _make_relationship(db_session, comp.id, a1_id, "atomic", 0)
        _make_relationship(db_session, comp.id, a2_id, "atomic", 1)
        db_session.commit()

        r = test_client.get(f"/protocols/{proto.id}/export/circe")
        assert r.status_code == 200
        stats = r.json()["stats"]
        assert stats["criteria_count"] == 1
        assert stats["atomic_count"] == 2
        assert stats["composite_count"] == 1
        assert stats["relationship_count"] == 2

    def test_auth_required(self, unauthenticated_client, db_session):
        """Export endpoints require authentication."""
        proto = _make_protocol(db_session)
        db_session.commit()
        r = unauthenticated_client.get(f"/protocols/{proto.id}/export/circe")
        assert r.status_code == 401
