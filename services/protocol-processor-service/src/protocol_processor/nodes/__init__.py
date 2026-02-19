"""LangGraph nodes for the 6-node protocol processing pipeline.

Nodes:
    ingest    - Fetch PDF bytes from GCS/local
    extract   - Gemini structured extraction of eligibility criteria
    parse     - Parse extraction JSON into DB records
    ground    - Entity-type-aware terminology grounding via TerminologyRouter
    persist   - Commit grounded results, update protocol status
    structure - Build expression trees from persisted criteria (Phase 2)
"""
