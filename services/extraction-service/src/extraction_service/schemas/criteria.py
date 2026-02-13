"""Pydantic models for Gemini structured output of criteria extraction.

These models define the schema that ChatVertexAI.with_structured_output()
uses to constrain Gemini's JSON response. Every field includes a
Field(description=...) to guide the LLM's output generation.

Nesting is kept to max 2 levels to avoid serialization issues with
ChatVertexAI (per research pitfall #3).
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AssertionStatus(str, Enum):
    """Assertion status for a clinical trial criterion.

    Determines whether the criterion describes a condition that must be
    present, absent, hypothetical, historical, or conditional.
    """

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HYPOTHETICAL = "HYPOTHETICAL"
    HISTORICAL = "HISTORICAL"
    CONDITIONAL = "CONDITIONAL"


class TemporalConstraint(BaseModel):
    """Temporal constraint on a criterion.

    Captures time-based requirements such as "within 6 months of screening"
    or "at least 4 weeks before enrollment".
    """

    duration: str | None = Field(
        default=None,
        description="Duration value, e.g., '6 months', '4 weeks', '30 days'",
    )
    relation: str | None = Field(
        default=None,
        description=("Temporal relation: 'within', 'before', 'after', or 'at_least'"),
    )
    reference_point: str | None = Field(
        default=None,
        description=(
            "Reference point for the temporal constraint: "
            "'screening', 'enrollment', 'diagnosis', or other timepoint"
        ),
    )


class NumericThreshold(BaseModel):
    """Numeric threshold for a criterion.

    Captures lab values, age ranges, dosages, and other measurable
    requirements such as "HbA1c < 8%" or "Age >= 18 years".
    """

    value: float = Field(
        description=(
            "The primary numeric value of the threshold "
            "(e.g., 40 for 'age 40-85', 8 for 'HbA1c <8%', 150 for '>=150mg')"
        ),
    )
    unit: str = Field(
        description=(
            "Unit of measurement, e.g., 'years', 'mg/dL', '%', "
            "'kg/m2', 'WOMAC', 'ECOG', 'mg', 'mmol/L'"
        ),
    )
    comparator: str = Field(
        description=(
            "Comparison operator: '>=' (greater than or equal), "
            "'<=' (less than or equal), '>' (greater than), "
            "'<' (less than), '==' (equals), or "
            "'range' (between two values, requires upper_value)"
        ),
    )
    upper_value: float | None = Field(
        default=None,
        description=(
            "Upper bound value when comparator is 'range'. "
            "Example: 'age 18-65 years' results in value=18, "
            "upper_value=65, comparator='range'. "
            "Only set when comparator='range'."
        ),
    )


class ExtractedCriterion(BaseModel):
    """A single extracted criterion from a clinical trial protocol.

    Contains the full structured representation of one inclusion or
    exclusion criterion, including temporal constraints, numeric
    thresholds, assertion status, and confidence scoring.
    """

    text: str = Field(
        description="The original criterion text as written in the protocol",
    )
    criteria_type: Literal["inclusion", "exclusion"] = Field(
        description="Whether this is an inclusion or exclusion criterion",
    )
    category: str | None = Field(
        default=None,
        description=(
            "Category of the criterion: 'demographics', 'medical_history', "
            "'lab_values', 'medications', 'procedures', or 'other'"
        ),
    )
    temporal_constraint: TemporalConstraint | None = Field(
        default=None,
        description="Any temporal constraint on this criterion, if applicable",
    )
    conditions: list[str] = Field(
        default_factory=list,
        description=(
            "Conditional dependencies extracted as complete natural language phrases. "
            "Look for markers: 'if', 'for patients who/with', 'when', "
            "'in case of', 'provided that', 'unless'. "
            "Extract the full conditional clause, not just the keyword. "
            "Examples: 'if female of childbearing potential', "
            "'for patients with diabetes'. "
            "Leave empty [] if the criterion has no conditional dependency."
        ),
    )
    numeric_thresholds: list[NumericThreshold] = Field(
        default_factory=list,
        description=(
            "List of ALL numeric thresholds mentioned in the criterion. "
            "Extract ALL numeric values with their units and comparison operators. "
            "Common patterns: age ranges ('40 to 85 years' -> comparator='range'), "
            "lab values ('HbA1c <8%' -> comparator='<'), "
            "dosages ('>=150mg' -> comparator='>='), "
            "scores ('WOMAC >=1.5' -> comparator='>='). "
            "A single criterion may have multiple thresholds."
        ),
    )
    assertion_status: AssertionStatus = Field(
        description=(
            "Assertion status: PRESENT means the condition must be true, "
            "ABSENT means it must not be true, HYPOTHETICAL for future "
            "conditions, HISTORICAL for past history, CONDITIONAL for "
            "dependent conditions"
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score for this extraction (0.0 = very uncertain, "
            "1.0 = very confident)"
        ),
    )
    source_section: str | None = Field(
        default=None,
        description="Section header where this criterion was found in the protocol",
    )
    page_number: int | None = Field(
        default=None,
        description=(
            "The 1-based page number in the PDF where this criterion appears. "
            "Report the page where the criterion text begins. "
            "If the criterion spans multiple pages, report the first page."
        ),
    )


class ExtractionResult(BaseModel):
    """Complete extraction result from a clinical trial protocol.

    Contains all extracted inclusion and exclusion criteria along with
    a brief summary of the protocol's purpose.
    """

    criteria: list[ExtractedCriterion] = Field(
        description="All extracted inclusion and exclusion criteria",
    )
    protocol_summary: str = Field(
        description=(
            "Brief 1-2 sentence summary of the clinical trial's purpose "
            "and target population"
        ),
    )
