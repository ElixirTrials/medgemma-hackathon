"""Prompt variant definitions for A/B testing grounding failures.

Pure data module — no side effects, no imports beyond stdlib.

Each MedGemma variant has:
- name: short label
- grounding_system: extra text to append to grounding_system.jinja2 output (or None)
- grounding_evaluate: extra text to append to grounding_evaluate.jinja2 output (or None)

Each field mapper variant has:
- name: short label
- field_mapper_rules_extra: extra rules to inject before </rules> in prompt (or None)
"""

# ── MedGemma variant fragments ──────────────────────────────────────────────

_SPECIFICITY_GUARD_SYSTEM = (
    "\n9. When the entity text contains no qualifier (e.g., no age, stage, "
    "site, or laterality modifier), prefer the PARENT concept over "
    "subspecific variants. For example, 'Ankylosing Spondylitis' maps to "
    "the general concept (C0038013), not 'Juvenile Ankylosing Spondylitis'."
    "\n10. When multiple candidates share near-identical preferred terms "
    "(differing only by version, alternate CUI, or source), prefer the "
    "PRIMARY CUI — the one whose preferred term is the most concise and "
    "canonical match for the entity text."
)

_CONTEXT_EMPHASIS_EVALUATE = (
    "\n\n## Cross-check\n"
    "Before making your final selection, verify:\n"
    "- If the candidate's preferred term adds a qualifier NOT present in "
    "the entity text (e.g., 'Juvenile', 'Ectopic', 'Chronic', 'Bilateral'), "
    "it is OVER-SPECIFIC — prefer the unqualified parent concept.\n"
    "- If two candidates have near-identical preferred terms, prefer the "
    "one whose CUI is the primary/canonical entry, not an alternate or "
    "version-specific code."
)

# Diagnosis from MLflow traces: the `combined` variant fails because stacking
# rules in BOTH system + evaluate overloads the model — it acknowledges the
# rules then ignores them. The `exact_match_first` variant puts ONE concise
# procedural instruction in the evaluate template: scan for exact matches
# first, only fall through to subspecific candidates if none found.
_EXACT_MATCH_FIRST_EVALUATE = (
    "\n\n## MANDATORY — Exact-Match-First Protocol\n"
    "BEFORE analyzing candidates, follow this procedure:\n"
    "1. Scan the candidate list for any entry whose preferred_term matches "
    "the entity text exactly (case-insensitive, ignoring minor word order).\n"
    "2. If one or more exact matches exist, select the one with the highest "
    "score. Do NOT consider subspecific variants that add qualifiers "
    "(e.g., 'Juvenile', 'Chronic', region-specific) when an exact match "
    "is available.\n"
    "3. Only if NO exact match exists, proceed to analyze close synonyms."
)

# ── Field mapper variant fragments ──────────────────────────────────────────

_OPERATOR_RULES_EXTRA = (
    "\n- Extract comparison operators VERBATIM from the criterion text. "
    "Never invert the operator direction. If the text says \">44\", "
    "the relation is \">\", not \"<\"."
    "\n- Use \"within\" ONLY for numeric min/max ranges (e.g., \"between "
    "18 and 65\"). Do NOT use \"within\" for discrete categorical lists "
    "like \"1, 2, or 3\" — use \"=\" instead."
    "\n- Negation patterns: \"non-\", \"not \", \"no \" preceding an entity "
    "indicate ABSENCE. Map to relation='!=' with value='True'. "
    "For example, \"non-pregnant\" means Pregnancy relation='!=' value='True'."
)

# v2: adds an explicit worked example for the BMI inversion failure.
# Trace analysis showed the LLM reads "body mass index >44" and generates
# relation='<' — interpreting it as an upper-bound exclusion rather than
# reading the operator literally. A concrete example forces the right parse.
_OPERATOR_RULES_V2_EXTRA = (
    "\n- CRITICAL: Read the mathematical operator from the criterion text "
    "LITERALLY. The relation MUST match the symbol in the text. "
    "Example: 'body mass index >44 kg/m2' → relation='>', value='44'. "
    "Do NOT interpret clinical intent (e.g., upper-limit exclusion). "
    "Just read the symbol."
    "\n- Use \"within\" ONLY for numeric min/max ranges (e.g., \"between "
    "18 and 65\"). Do NOT use \"within\" for discrete categorical lists "
    "like \"1, 2, or 3\" — use \"=\" instead."
    "\n- Negation patterns: \"non-\", \"not \", \"no \" preceding an entity "
    "indicate ABSENCE. Map to relation='!=' with value='True'. "
    "For example, \"non-pregnant\" means Pregnancy relation='!=' value='True'."
)

# ── Variant lists ───────────────────────────────────────────────────────────

MEDGEMMA_VARIANTS: list[dict] = [
    {
        "name": "baseline",
        "grounding_system": None,
        "grounding_evaluate": None,
    },
    {
        "name": "specificity_guard",
        "grounding_system": _SPECIFICITY_GUARD_SYSTEM,
        "grounding_evaluate": None,
    },
    {
        "name": "context_emphasis",
        "grounding_system": None,
        "grounding_evaluate": _CONTEXT_EMPHASIS_EVALUATE,
    },
    {
        "name": "combined",
        "grounding_system": _SPECIFICITY_GUARD_SYSTEM,
        "grounding_evaluate": _CONTEXT_EMPHASIS_EVALUATE,
    },
    {
        "name": "exact_match_first",
        "grounding_system": None,
        "grounding_evaluate": _EXACT_MATCH_FIRST_EVALUATE,
    },
]

FIELD_MAPPER_VARIANTS: list[dict] = [
    {
        "name": "baseline",
        "field_mapper_rules_extra": None,
    },
    {
        "name": "operator_rules",
        "field_mapper_rules_extra": _OPERATOR_RULES_EXTRA,
    },
    {
        "name": "operator_rules_v2",
        "field_mapper_rules_extra": _OPERATOR_RULES_V2_EXTRA,
    },
]
