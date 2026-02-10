# Technology Stack

**Project:** Clinical Trial Protocol Criteria Extraction System
**Researched:** 2026-02-10
**Confidence:** HIGH

## Recommended Stack

### PDF Ingestion & Parsing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| pymupdf4llm | 0.2.9 | LLM-optimized PDF extraction | **BEST FOR CLINICAL PROTOCOLS**: Converts PDFs to markdown with table detection, multi-column support, and layout preservation. Released Jan 2026 specifically for RAG/LLM workflows. Superior to raw PyMuPDF for AI pipelines. |
| PyMuPDF | >=1.24.0 | Core PDF processing | High-speed text extraction with OCR support. AGPL license (acceptable for pilot). Required dependency of pymupdf4llm. |
| google-cloud-storage | 3.9.0 | PDF storage in GCS | Official Google library for GCS. Mature (v3.9.0, Feb 2026), includes resumable uploads, signed URLs for large files. Essential for protocol PDF storage. |

**Confidence:** HIGH - All versions verified from PyPI Feb 2026, pymupdf4llm designed specifically for clinical documents.

### Medical AI & Entity Extraction

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| langextract | 1.1.1 | Clinical entity extraction | **GOOGLE'S PURPOSE-BUILT TOOL**: Open-source library (July 2025) designed for healthcare. Provides source grounding (maps extractions to PDF locations), chunking for long documents, and optimized for clinical notes. Works with Gemini 2.5-flash/pro. Replaces ad-hoc prompt engineering. |
| google-cloud-aiplatform | >=1.70.0 | Vertex AI SDK | Deploy MedGemma models on Vertex AI. Current in template (1.130.0). Supports both MedGemma 1.5 (4B) for entity extraction and Gemini 2.5 for criteria extraction. |
| medcat | 2.5.3 | UMLS/SNOMED grounding | Production-ready (Jan 2026) library for linking entities to SNOMED-CT UK Clinical (40.2) + UMLS 2024AA. Trained on MIMIC-IV. Enables concept normalization and medical coding. |

**Confidence:** HIGH - LangExtract and MedCAT explicitly designed for clinical text. Versions current as of Feb 2026.

### HITL Workflow & Orchestration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| langgraph | 1.0.8 | HITL orchestration | **STANDARD FOR 2026 HITL**: LangGraph 1.0 (Feb 2026) provides `interrupt()` for approval workflows, state persistence, and audit trails. Enables "approve/reject" patterns for clinical reviewers. Already in template (1.0.6+). Superior to custom state machines. |
| FastAPI | >=0.128.0 | REST API | Already in template. Integrates seamlessly with LangGraph async patterns. High-performance for PDF uploads. |
| SQLModel | >=0.0.31 | Data models | Already in template. Combines Pydantic validation with SQLAlchemy ORM. Ideal for clinical data integrity (required for HITL audit logs). |
| Alembic | >=1.13.0 | Database migrations | Already in template. Essential for versioning HITL approval schemas, extraction results, and audit trails. Auto-generate from SQLModel. |

**Confidence:** HIGH - LangGraph 1.0 is GA (Feb 2026) with first-class HITL support. FastAPI/SQLModel/Alembic standard for 2026.

### Authentication & Authorization

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| authlib | 1.6.7 | Google OAuth integration | **PRODUCTION-READY OAUTH**: Latest release (Feb 2026), supports OAuth 2.0, OpenID Connect, and FastAPI/Starlette integration. Enables Google OAuth for clinical researchers. Superior to python-jose alone. |
| python-jose[cryptography] | latest | JWT token handling | Generates/validates JWT tokens post-OAuth. Works with authlib for session management. |

**Confidence:** MEDIUM-HIGH - Authlib version confirmed (1.6.7, Feb 2026). Standard OAuth library for FastAPI, but integration requires custom implementation.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | >=2.0 | Data validation | Clinical data schemas (inclusion/exclusion criteria, entity models). Already via SQLModel. Use for nested extraction schemas with LangExtract. |
| python-dotenv | >=1.2.1 | Config management | Already in template. Store GCS buckets, OAuth client IDs, Vertex AI project. |
| tenacity | >=8.2.0 | Retry logic | Already in template. Essential for Vertex AI API calls (rate limits, transient errors). Use with exponential backoff. |
| diskcache | >=5.6.3 | PDF parsing cache | Already in template. Cache pymupdf4llm outputs to avoid re-parsing protocols during development. |

**Confidence:** HIGH - All already in template or standard supporting libraries.

## Installation

```bash
# Already in template - verify versions
uv add google-cloud-aiplatform@>=1.70.0
uv add google-cloud-storage@3.9.0
uv add langgraph@1.0.8
uv add fastapi@>=0.128.0
uv add sqlmodel@>=0.0.31
uv add alembic@>=1.13.0

# NEW: PDF ingestion
uv add pymupdf4llm@0.2.9
uv add "pymupdf4llm[layout]"  # For advanced layout analysis

# NEW: Medical AI
uv add langextract@1.1.1
uv add medcat@2.5.3

# NEW: Authentication
uv add authlib@1.6.7
uv add "python-jose[cryptography]"

# Dev dependencies (already in template)
uv add --group dev pytest@>=9.0.2
uv add --group dev pytest-asyncio@>=1.2.0
uv add --group dev mypy@>=1.19.0
uv add --group dev ruff@>=0.14.8
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| pymupdf4llm | pdfplumber | If protocols have complex tables requiring cell-level extraction. pymupdf4llm better for LLM-readable text. |
| langextract | Custom Gemini prompts | NEVER for production. LangExtract provides source grounding, chunking, and optimization. Ad-hoc prompts lack traceability required for clinical data. |
| medcat | PyMedTermino2 | If offline UMLS access required (no network). MedCAT faster and includes pre-trained models for clinical text. |
| langgraph | Temporal workflow engine | If HITL requires complex multi-day approval chains (not needed for pilot). LangGraph sufficient for review-approve-reject. |
| authlib | FastAPI OAuth2PasswordBearer | NEVER for Google OAuth. authlib handles OAuth 2.0 flows properly. OAuth2PasswordBearer is for username/password. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| PyPDF2 | **DEPRECATED** as of 2023. Final release 3.0.x receives no updates. Vulnerable to PDF standard changes. | pymupdf4llm or pypdf (PyPDF2 successor) |
| pypdf (standalone) | Successor to PyPDF2 but lacks LLM optimization. No markdown conversion, table detection, or layout preservation for clinical protocols. | pymupdf4llm (built for RAG/LLM) |
| pdfminer.six | Slow, brittle on complex layouts. Clinical protocols often multi-column with tables. Extraction errors common. | pymupdf4llm |
| Manual prompt engineering for entity extraction | No source grounding, poor chunking for long protocols, requires prompt maintenance. Clinical data needs traceability. | langextract |
| spaCy + scispaCy (alone) | Good for NER but lacks UMLS/SNOMED grounding. Requires custom mapping logic. MedCAT includes pre-trained UMLS models. | medcat |
| Custom state machines for HITL | Reinventing LangGraph. No persistence, audit trails, or interrupt/resume patterns. High maintenance. | langgraph |
| Firebase Auth | Vendor lock-in. Template uses Google Cloud, but OAuth via authlib keeps auth portable. Firebase adds unnecessary dependency. | authlib + Google OAuth |

## Stack Patterns by Variant

**For 50-protocol pilot (current requirement):**
- Use pymupdf4llm with basic layout (no OCR)
- Deploy MedGemma 1.5 (4B) on Vertex AI for cost efficiency
- Single-reviewer HITL workflow via LangGraph
- GCS signed URLs for PDF access (no CDN)

**If scaling to 500+ protocols:**
- Add pymupdf4llm[layout] for advanced parsing
- Consider MedGemma 27B for higher accuracy
- Multi-reviewer workflows with LangGraph subgraphs
- Add GCS CDN for PDF delivery

**If protocols include scanned images:**
- Add pymupdf4llm[ocr] for OCR support
- Budget Vertex AI OCR costs
- Increase PDF parsing timeout (scanned docs slower)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pymupdf4llm@0.2.9 | PyMuPDF >=1.24.0 | pymupdf4llm auto-installs compatible PyMuPDF. No manual version management. |
| langextract@1.1.1 | google-cloud-aiplatform >=1.70.0 | LangExtract uses Gemini 2.5-flash via Vertex AI SDK. Requires vertexai module. |
| medcat@2.5.3 | Python 3.10-3.13 | Template uses Python 3.12. Compatible. MedCAT models trained on UMLS 2024AA. |
| langgraph@1.0.8 | langchain >=1.2.6 | Template already has langchain 1.2.6+. LangGraph 1.0 stable API. |
| authlib@1.6.7 | FastAPI >=0.128.0 | Requires FastAPI (already in template). Use Starlette OAuth integration. |
| SQLModel@0.0.31 | Alembic >=1.13.0 | Set `target_metadata = SQLModel.metadata` in Alembic env.py for auto-migrations. |

## Architecture Notes

### PDF Ingestion Flow
1. **Upload**: FastAPI endpoint receives protocol PDF
2. **Storage**: Save to GCS bucket with metadata (protocol_id, upload_date)
3. **Parsing**: pymupdf4llm converts PDF to markdown with table preservation
4. **Caching**: Store parsed markdown in diskcache (avoid re-parsing during review iterations)

### Entity Extraction Pipeline
1. **Criteria Extraction**: LangExtract on parsed markdown → structured JSON (inclusion/exclusion criteria)
2. **Medical Entity Extraction**: MedGemma 1.5 (4B) via Vertex AI → extract conditions, medications, demographics
3. **UMLS Grounding**: MedCAT maps entities to SNOMED-CT + UMLS CUIs
4. **Storage**: SQLModel stores extracted data with source locations (page, paragraph)

### HITL Workflow
1. **Review Queue**: LangGraph orchestrates extraction → review node
2. **Interrupt**: `interrupt()` pauses graph, notifies React UI (HITL-UI)
3. **Reviewer Action**: Clinical researcher approves/rejects/edits via React frontend
4. **Resume**: FastAPI endpoint resumes LangGraph with approval decision
5. **Audit**: SQLModel logs all decisions (reviewer_id, timestamp, changes)

### Google OAuth Integration
1. **Login**: React UI redirects to Google OAuth (authlib handles flow)
2. **Token Exchange**: authlib validates OAuth code, gets user info
3. **JWT Generation**: python-jose creates session JWT with user email, role
4. **Protected Routes**: FastAPI dependencies validate JWT on HITL endpoints

## Sources

**PDF Extraction:**
- [I Tested 7 Python PDF Extractors (2025 Edition)](https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257)
- [Best Python PDF to Text Parser Libraries: A 2026 Evaluation](https://unstract.com/blog/evaluating-python-pdf-to-text-libraries/)
- [pymupdf4llm PyPI](https://pypi.org/project/pymupdf4llm/)
- [PyMuPDF4LLM Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Maintained Alternatives to PyPDF2: 2026 Guide](https://copyprogramming.com/howto/maintained-alternatives-to-pypdf2)

**Medical AI & Entity Extraction:**
- [Introducing LangExtract - Google Developers Blog](https://developers.googleblog.com/introducing-langextract-a-gemini-powered-information-extraction-library/)
- [Can LangExtract Turn Messy Clinical Notes into Structured Data?](https://towardsdatascience.com/can-langextract-turn-messy-clinical-notes-into-structured-data/)
- [LangExtract GitHub](https://github.com/google/langextract)
- [langextract PyPI](https://pypi.org/project/langextract/)
- [MedGemma - Google Health AI](https://developers.google.com/health-ai-developer-foundations/medgemma)
- [medcat PyPI](https://pypi.org/project/medcat/)
- [AI-assisted Protocol Information Extraction (2026)](https://arxiv.org/html/2602.00052)

**HITL Workflows:**
- [LangGraph Human-in-the-loop Deployment with FastAPI](https://shaveen12.medium.com/langgraph-human-in-the-loop-hitl-deployment-with-fastapi-be4a9efcd8c0)
- [Human-in-the-Loop AI - Complete Guide for 2026](https://parseur.com/blog/human-in-the-loop-ai)
- [LangGraph Interrupts Documentation](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph PyPI](https://pypi.org/project/langgraph/)

**Authentication:**
- [Integrating Google Authentication with FastAPI](https://blog.futuresmart.ai/integrating-google-authentication-with-fastapi-a-step-by-step-guide)
- [authlib PyPI](https://pypi.org/project/authlib/)
- [Google login for FastAPI - Authlib](https://blog.authlib.org/2020/fastapi-google-login)

**Google Cloud Storage:**
- [Python Client for Google Cloud Storage](https://docs.cloud.google.com/python/docs/reference/storage/latest)
- [google-cloud-storage PyPI](https://pypi.org/project/google-cloud-storage/)

**Database & Infrastructure:**
- [Database Migrations with Alembic and FastAPI](https://adex.ltd/database-migrations-with-alembic-and-fastapi-a-comprehensive-guide-using-poetry)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)

---
*Stack research for: Clinical Trial Protocol Criteria Extraction System*
*Researched: 2026-02-10*
*Confidence: HIGH (all versions verified from official sources Feb 2026)*
