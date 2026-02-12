# Clinical Trial Criteria Extraction System

AI-powered system for extracting and grounding clinical trial eligibility criteria from protocol PDFs. Upload a protocol and get accurately extracted, UMLS-grounded criteria ready for clinical researcher review and approval.

## Quick Start

### Prerequisites
- **Python 3.12+**
- **Node.js 20+**
- **uv** (Python package manager)
- **Docker**

### Installation
```bash
# Sync dependencies
uv sync
```

## System Components

- **API Service**: FastAPI orchestrator providing HTTP endpoints for the frontend, managing database persistence, and triggering background workflows.
- **Extraction Service**: LangGraph workflow using Gemini to extract structured inclusion/exclusion criteria from protocol PDFs.
- **Grounding Service**: Entity grounding workflow using MedGemma and UMLS MCP to map medical entities to SNOMED codes.
- **HITL UI**: React/Vite application for clinical researchers to review, approve, edit, or reject AI-extracted criteria and grounded entities.

## Documentation

- **[Onboarding](onboarding.md)**: Getting started guide for new contributors.
- **[Components Overview](components/index.md)**: Detailed overview of all services and libraries.
- **[System Diagrams](diagrams/hitl-flow.md)**: Visual flows and architecture diagrams.
- **[Testing Guide](testing-guide.md)**: Testing patterns and guidelines.
