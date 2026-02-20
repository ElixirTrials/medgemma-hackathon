# Testing Guide

## Running Tests

```bash
# All tests (parallel by default with pytest-xdist)
make test

# API service tests only
uv run pytest services/api-service/tests -q

# Specific test file
uv run pytest services/api-service/tests/test_exports.py -q

# With coverage
uv run pytest --cov services/api-service/tests

# Disable parallel execution (useful for debugging)
uv run pytest services/api-service/tests --override-ini="addopts=" -q
```

## Test Structure

```
services/api-service/tests/
├── conftest.py               # Shared fixtures (in-memory DB, test client)
├── test_auth_required.py     # Authentication middleware
├── test_exports.py           # CIRCE, FHIR, SQL export builders (36 tests)
├── test_integrity.py         # Data integrity checks
├── test_models.py            # SQLModel validation
├── test_protocol_api.py      # Protocol upload/list/detail endpoints
├── test_quality.py           # PDF quality scoring
├── test_review_api.py        # Review workflow endpoints
├── test_schemas.py           # Pydantic schema validation
└── test_umls_clients.py      # UMLS API client mocking

libs/events-py/tests/
└── test_outbox.py            # Outbox processor tests
```

## Test Fixtures

The `conftest.py` provides:

- **In-memory SQLite database** — tests don't need PostgreSQL running
- **SQLModel metadata creation** — all tables created per test session
- **FastAPI TestClient** — for HTTP endpoint testing
- **Mock authentication** — bypasses OAuth for test requests

## Writing New Tests

### API Endpoint Test

```python
def test_list_protocols(client, db_session):
    """Test paginated protocol listing."""
    # Arrange: seed a protocol
    protocol = Protocol(title="Test", file_uri="local://test.pdf", status="uploaded")
    db_session.add(protocol)
    db_session.commit()

    # Act
    response = client.get("/protocols")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
```

### Export Builder Test

```python
def test_circe_includes_age_filter(make_export_data, make_atomic):
    """Test that demographics criteria produce CIRCE age filters."""
    atomic = make_atomic(entity_domain="demographics", relation_operator=">=", value_numeric=18)
    data = make_export_data(atomics=[atomic])
    result = build_circe_export(data)
    assert any("Age" in str(g) for g in result.get("InclusionRules", []))
```

## Code Quality

```bash
make check        # Run all: lint + typecheck + test
make lint         # ruff (Python) + Biome (TypeScript)
make lint-fix     # Auto-fix lint issues
make typecheck    # mypy (Python) + tsc (TypeScript)
```

### Linting Configuration

- **Python**: ruff (configured in `pyproject.toml`)
- **TypeScript**: Biome (configured in `apps/hitl-ui/biome.json`)
- **Type checking**: mypy for Python, tsc for TypeScript

### Pre-existing mypy Issues

The following mypy errors are pre-existing and non-critical:

- `libs/events-py` import stubs (3 errors)
- These do not affect runtime behavior
