"""Quick validation of repetition loop detection and sanitization."""

from __future__ import annotations

from pydantic import BaseModel, Field

from protocol_processor.tools.field_mapper import (
    FieldMappingItem,
    FieldMappingResponse,
    FieldMappingValue,
)
from protocol_processor.tools.gemini_utils import (
    check_model_for_repetition,
    is_repetition_loop,
)


class _RawValue(BaseModel):
    type: str = "standard"
    value: str | None = None


class _RawMapping(BaseModel):
    entity: str = ""
    mappings: list[_RawValue] = Field(default_factory=list)


def test_detection() -> None:
    """Test is_repetition_loop() against known patterns."""
    test_cases = [
        ("2202202020202020202020202020202020", True, "repeating digits"),
        (
            "8598739459392231e-3158739459392231e-3158739459392231e-315",
            True,
            "repeating sci notation",
        ),
        ("2Unit of measurement (e.g. years)", True, "schema leak"),
        ("Value for standard type", True, "schema leak 2"),
        ("Duration value for temporal type", True, "schema leak 3"),
        ("True", False, "normal boolean"),
        ("7", False, "normal number"),
        ("%", False, "normal unit"),
        ("mg/dL", False, "normal unit 2"),
        ("HbA1c", False, "normal entity"),
        ("44", False, "normal value"),
    ]

    print("=== is_repetition_loop() unit tests ===")
    all_pass = True
    for text, expected, label in test_cases:
        result = is_repetition_loop(text)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status}: {label:30s} | expected={expected}, got={result}")

    print()
    assert all_pass


def test_sanitization() -> None:
    """Test FieldMappingValue validator nulls out repetitive values."""
    print("=== FieldMappingValue sanitization ===")

    # Repetitive value + schema-leak unit should both be nulled
    val = FieldMappingValue(
        type="standard",
        value="2202202020202020202020202020202020",
        unit="Unit of measurement (e.g. years)",
        min=None,
        max=None,
        duration=None,
    )
    print(f"  value after sanitization: {val.value!r} (expected None)")
    print(f"  unit after sanitization:  {val.unit!r} (expected None)")
    assert val.value is None, f"Expected None, got {val.value!r}"
    assert val.unit is None, f"Expected None, got {val.unit!r}"

    # Normal values should be preserved
    val2 = FieldMappingValue(
        type="standard",
        value="7",
        unit="%",
        min=None,
        max=None,
        duration=None,
    )
    print(f"  normal value preserved:   {val2.value!r} (expected '7')")
    print(f"  normal unit preserved:    {val2.unit!r} (expected '%')")
    assert val2.value == "7"
    assert val2.unit == "%"

    print()


def test_model_check() -> None:
    """Test check_model_for_repetition() on a full response."""
    print("=== check_model_for_repetition() ===")

    # Response with one clean mapping and one repetitive mapping
    response = FieldMappingResponse(
        mappings=[
            FieldMappingItem(
                entity="HbA1c",
                relation="<",
                value=FieldMappingValue(
                    type="standard",
                    value="7",
                    unit="%",
                    min=None,
                    max=None,
                    duration=None,
                ),
                unit=None,
                value_concept_id=None,
                value_concept_system=None,
            ),
            FieldMappingItem(
                entity="Postmenopause",
                relation="=",
                value=FieldMappingValue(
                    type="standard",
                    value="2202202020202020202020202020202020",
                    unit=None,
                    min=None,
                    max=None,
                    duration=None,
                ),
                unit=None,
                value_concept_id=None,
                value_concept_system=None,
            ),
        ]
    )

    # Note: the validator will have already nulled out the repetitive value
    # during Pydantic construction. So check_model_for_repetition should
    # find nothing (since the validator cleaned it). Let's verify.
    bad = check_model_for_repetition(response)
    print(f"  Bad fields after Pydantic sanitization: {bad}")
    print("  (expected empty — validator already cleaned)")
    print(f"  Mapping[1] value.value = {response.mappings[1].value.value!r}")

    # Now test with a raw dict that bypasses the validator
    # (simulating what check_model_for_repetition would see BEFORE validation)
    raw = _RawMapping(
        mappings=[
            _RawValue(value="ok"),
            _RawValue(value="220220220220220220220220220220220220"),
        ]
    )
    bad2 = check_model_for_repetition(raw)
    print(f"  Raw model bad fields: {bad2}")
    assert len(bad2) == 1, f"Expected 1 bad field, got {bad2}"

    print()
