#!/usr/bin/env python3
"""Run full grounding pipeline on a single snippet: decompose → route → units."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "services"
        / "protocol-processor-service"
        / "src"
    ),
)
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "services" / "api-service" / "src")
)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "libs" / "shared" / "src"))

SNIPPET = (
    "Female subjects must be surgically sterile; or at least 2 years postmenopausal; "
    "or have a monogamous partner who is surgically sterile; or practicing double-barrier "
    "contraception; or practicing abstinence (must agree to use double-barrier contraception "
    "in the event of sexual activity); or using an insertable, injectable, transdermal, or "
    "combination oral contraceptive approved by the FDA for greater than 2 months prior to "
    "screening and commit to the use of an acceptable form of birth control for the duration "
    "of the study and for 30 days after completion of the study."
)


async def main() -> None:
    from protocol_processor.tools.entity_decomposer import (
        decompose_entities_from_criterion,
    )
    from protocol_processor.tools.terminology_router import TerminologyRouter
    from protocol_processor.tools.unit_normalizer import normalize_unit

    print(f"SNIPPET: {SNIPPET[:100]}...\n")

    # Phase 1: Entity decomposition (Gemini)
    print("=" * 70)
    print("PHASE 1: ENTITY DECOMPOSITION (Gemini)")
    print("=" * 70)
    entities = await decompose_entities_from_criterion(SNIPPET, category="demographics")
    print(f"\nDecomposed into {len(entities)} entities:\n")
    for i, ent in enumerate(entities):
        print(f"  {i + 1}. [{ent['entity_type']}] {ent['text']}")

    # Phase 2: Terminology routing (UMLS/SNOMED)
    print(f"\n{'=' * 70}")
    print("PHASE 2: TERMINOLOGY ROUTING")
    print("=" * 70)
    router = TerminologyRouter()

    for i, ent in enumerate(entities):
        text = ent["text"]
        etype = ent["entity_type"]
        candidates = await router.route_entity(text, etype)

        print(f"\n  Entity {i + 1}: '{text}' (type={etype})")
        if candidates:
            best = candidates[0]
            print(
                f"    TOP: {best.source_api}:{best.code} — {best.preferred_term} (score={best.score:.3f})"
            )
            if len(candidates) > 1:
                print(f"    ({len(candidates)} total candidates)")
        else:
            print("    NO CANDIDATES")

    # Phase 3: Unit normalization (for any entities that might have units)
    print(f"\n{'=' * 70}")
    print("PHASE 3: UNIT NORMALIZATION")
    print("=" * 70)
    test_units = ["years", "months", "days"]
    for u in test_units:
        ucum, omop_id = normalize_unit(u)
        print(f"  '{u}' -> UCUM={ucum}, OMOP={omop_id}")


if __name__ == "__main__":
    asyncio.run(main())
