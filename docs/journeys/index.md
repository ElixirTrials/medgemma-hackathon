# User Journeys

End-to-end workflows through the system, from protocol upload to structured export.

## Journey Map

| Journey | Actors | Outcome |
|---------|--------|---------|
| [Upload & Extraction](upload-extraction.md) | Researcher → System | PDF becomes structured criteria in DB |
| [Grounding, Structuring & HITL Review](grounding-review.md) | System → Clinician | Criteria get coded, structured, and reviewed |

## The Big Picture

A protocol PDF moves through these stages:

```
Upload → Extract → Parse → Ground → Persist → Structure → Ordinal Resolve → Review → Export
 (UI)    (Gemini)   (DB)   (UMLS)    (DB)     (Gemini)     (Gemini)        (HITL)   (API)
```

Each stage is a LangGraph node in `protocol-processor-service`, except Upload (API endpoint), Review (UI), and Export (API endpoint).
