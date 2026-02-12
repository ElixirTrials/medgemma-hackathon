# User Journeys

This section documents the key user workflows in the Clinical Trial Criteria Extraction System through narrative walkthroughs with runtime sequence diagrams.

Each journey focuses on the **happy path** and links to error handling documentation for failure scenarios.

## Journeys

| Journey | Description | Primary Actor |
|---------|-------------|---------------|
| [Upload & Extraction](./upload-extraction.md) | From PDF upload to structured criteria extraction | Clinical Researcher |
| [Grounding & HITL Review](./grounding-review.md) | From entity identification to human-approved UMLS codes | Clinical Researcher |

## How to Read These Journeys

Each journey follows a consistent structure:

1. **User Story** — Who is doing what, and why it matters
2. **Runtime Flow** — Mermaid sequence diagram showing service interactions
3. **Narrative Explanation** — Three-act walkthrough (setup, action, resolution) explaining the "why" behind each step
4. **Error Handling** — Links to component-specific error documentation

## Related Documentation

- [System Architecture](../architecture/system-architecture.md) — C4 Container diagram showing system structure
- [Data Models](../architecture/data-models.md) — Database schema and LangGraph state structures
- [HITL Flow Diagram](../diagrams/hitl-flow.md) — Combined end-to-end sequence diagram (overview)
