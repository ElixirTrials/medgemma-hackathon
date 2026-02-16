# Pitfalls Research

**Domain:** Clinical NLP HITL System - Corpus Building and Editor Polish
**Researched:** 2026-02-13
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Form Pre-loading with react-hook-form useFieldArray - Database ID Conflicts

**What goes wrong:**
The `useFieldArray` hook generates its own UUID as `id` for each field, which overwrites database IDs when pre-populating from saved data. This breaks the connection between UI state and persisted records, causing update/delete operations to target the wrong records or fail silently.

**Why it happens:**
Developers assume they can pass database objects directly to `append()` or set as `defaultValues`, but `useFieldArray` mandates using its generated `field.id` (not index) as the React key. When database records have an `id` field, it gets replaced, severing the link to the backend.

**How to avoid:**
- Store database IDs in a separate field (e.g., `database_id`, `criterion_id`) in the form state, never as `id`
- Use `field.id` from `useFieldArray` exclusively for React keys
- Create a mapping layer that translates between `field.id` (UI) and `database_id` (persistence) when submitting
- When pre-populating, restructure data: `{ database_id: record.id, entity: record.entity, ... }` not `{ id: record.id, ... }`

**Warning signs:**
- Criteria or entities update but appear to create new records instead
- Delete operations fail with "record not found" errors
- Form state contains UUIDs that don't match database primary keys
- Multiple form submissions create duplicate records with different IDs

**Phase to address:**
Phase 28-03 (Read Mode Display) and Phase 28-04 (Form Pre-loading from Database)

---

### Pitfall 2: Async Data Pre-loading with defaultValues Instead of values

**What goes wrong:**
Using `defaultValues` in `useForm()` to populate data fetched asynchronously (from API) only initializes the form on first render. When data arrives after mount, form fields remain empty or stale. Subsequent data changes don't update the form, breaking edit-existing-record workflows.

**Why it happens:**
`defaultValues` is a one-time initialization prop evaluated at mount. Developers expect it to update when the query resolves, but React Hook Form explicitly ignores later changes to `defaultValues` for performance. The correct pattern (`values` prop or `reset()` method) is less documented and non-obvious.

**How to avoid:**
- Use the `values` prop in `useForm()` for data that changes: `useForm({ values: fetchedData })`
- Alternatively, call `reset(fetchedData)` in a `useEffect` when data loads
- Never set `defaultValues` to undefined/empty object and expect it to update later
- Pattern: `useForm({ values: criterion ?? DEFAULT_FIELD_VALUES })`

**Warning signs:**
- Form fields are blank when editing existing records
- Console shows data loaded but form doesn't populate
- Form only works when creating new records, not editing
- Refreshing page works, but navigating to edit page doesn't

**Phase to address:**
Phase 28-04 (Form Pre-loading from Database)

---

### Pitfall 3: JSONB Schema Evolution Without Versioning Strategy

**What goes wrong:**
Field mappings stored in `conditions` JSONB column evolve schema over time (e.g., adding `upper_value` for ranges, adding `field_mappings` array). Old records with schema v1 break when code expects v2 structure, causing runtime errors, data loss on edit, or silent field drops.

**Why it happens:**
JSONB's schema-less flexibility encourages "just add the field" thinking. Developers update write path with new structure but forget to migrate existing records or add read-time schema adapters. Code assumes latest schema, crashes on old data.

**How to avoid:**
- Add `schema_version` field to every JSONB document: `{ schema_version: "v1.5-multi", field_mappings: [...] }`
- Write migration scripts when schema changes: convert v1 → v2 in database
- Add read-time adapter layer that normalizes all versions to latest schema for UI
- Document schema changes in audit logs so corpus evaluation can account for version differences
- Never assume field presence; use optional chaining and defaults: `conditions?.field_mappings ?? []`

**Warning signs:**
- TypeError: "Cannot read property X of undefined" when loading old criteria
- Some criteria load correctly, others throw errors (indicates mixed schema versions)
- Edit-then-save drops fields that were present in original record
- Corpus evaluation metrics change dramatically after code deployment (schema mismatch)

**Phase to address:**
Phase 28-05 (JSONB Migration Strategy) and Phase 29-02 (Corpus Versioning)

---

### Pitfall 4: Re-extraction Overwrites Human Corrections Without Corpus Capture

**What goes wrong:**
Running extraction on same protocol again (to test prompt improvements) overwrites criteria records that have human corrections, destroying gold-standard data. Corpus building fails because corrected versions are lost before being flagged for corpus inclusion.

**Why it happens:**
Re-extraction logic uses `protocol_id` to find existing batches and replaces criteria in-place to avoid duplicates. But it doesn't distinguish between "AI-only" and "human-reviewed" records. Developers assume re-extraction is safe since "we can always re-review," forgetting that reviews *are the corpus*.

**How to avoid:**
- Add `is_locked` flag to criteria that have human reviews (`review_status IS NOT NULL`)
- Re-extraction creates new batch, never updates criteria with `is_locked = true`
- Implement "export to corpus" step that copies reviewed criteria to separate `gold_corpus` table before allowing re-extraction
- Add database constraint: prevent DELETE/UPDATE on criteria if `review_status IS NOT NULL` without explicit `override_lock` flag
- UI shows clear warning: "5 criteria have reviews. Re-extraction will create new batch, not overwrite."

**Warning signs:**
- Corpus size decreases instead of growing over time
- Reviewers report "I already corrected this but it's back to the AI version"
- Audit log shows DELETE followed by INSERT for same criterion text
- Evaluation metrics can't reproduce because gold data was overwritten

**Phase to address:**
Phase 29-01 (Re-extraction Strategy) and Phase 29-02 (Corpus Versioning)

---

### Pitfall 5: PDF Scroll-to-Source Without Fuzzy Text Matching

**What goes wrong:**
`highlightText` prop uses exact string match to find criterion text in PDF. OCR artifacts (extra spaces, line breaks, encoding issues) cause match failures. PDF displays correct page but no highlight, confusing reviewers about evidence location.

**Why it happens:**
PDFs contain unpredictable whitespace and formatting. Criterion text extracted from `page_number` metadata might say "Age >= 18 years" but PDF has "Age  ≥ 18\nyears" (double space, Unicode ≥, line break). Exact match fails silently.

**How to avoid:**
- Normalize both criterion text and PDF text: lowercase, collapse whitespace, normalize Unicode
- Use fuzzy matching with Levenshtein distance threshold (90% similarity)
- Fallback strategy: if exact match fails, search ±1 page with fuzzy match
- Store extraction metadata: `{ text, normalized_text, page_number, bbox }` where `bbox` gives coordinates
- If using PDF coordinates, prefer bounding box over text search entirely

**Warning signs:**
- "Click to view source" navigates to correct page but nothing highlights
- Works for some criteria, fails for others with similar text (indicates inconsistent formatting)
- Criteria with special characters (≥, ≤, μ) never highlight
- Multiline criteria don't highlight but single-line ones do

**Phase to address:**
Phase 28-02 (Evidence Linking - PDF Scroll and Highlight)

---

### Pitfall 6: Read Mode Display Assumes Structured Fields Exist

**What goes wrong:**
Code renders "read mode" display of field mappings without checking if data is structured. Criteria extracted before structured editing feature was added have `conditions = null` or `conditions = ["if patient is diabetic"]` (string array, not field mappings). Renderer crashes or shows "undefined" everywhere.

**Why it happens:**
Incremental feature development means data has multiple shapes. Old criteria have text-only, new ones have structured fields. Developers test against recent data, miss edge cases of legacy data.

**How to avoid:**
- Always check data shape before rendering: `if (Array.isArray(conditions?.field_mappings))`
- Add TypeScript type guards: `function isFieldMappings(data): data is { field_mappings: FieldMapping[] }`
- Fallback to text-only display for unstructured criteria: "Entity: [not structured]"
- Add "Migrate to Structured" button for old criteria instead of crashing
- Document data shapes with examples in code comments

**Warning signs:**
- TypeError when loading old criteria: "Cannot read property 'map' of undefined"
- Some criteria show structured view, others show blank cards
- Criteria created before date X always fail to render
- Console shows data but UI is empty (rendering failed silently)

**Phase to address:**
Phase 28-03 (Read Mode Display)

---

### Pitfall 7: Corpus Evaluation Without Inter-Annotator Agreement Tracking

**What goes wrong:**
Building corpus from single reviewer per criterion produces unreliable gold standard. Evaluation metrics appear good but don't generalize because "gold" data reflects one reviewer's interpretation, which may be inconsistent or idiosyncratic.

**Why it happens:**
Corpus building treats any human review as gold truth. Research shows inter-annotator agreement (IAA) is critical for clinical NLP but tracking it requires multiple reviewers per item, which is expensive. Developers skip IAA to save time, discover later that corpus is noisy.

**How to avoid:**
- Sample 10-20% of criteria for dual review (two reviewers, compare results)
- Calculate Cohen's Kappa or similar IAA metric for sampled subset
- Flag criteria with reviewer disagreement for adjudication or exclusion from corpus
- Store `reviewer_id` in audit log and allow filtering corpus by reviewer to identify outliers
- Document acceptable IAA threshold (typically >0.7 for clinical tasks) and refuse corpus inclusion below threshold

**Warning signs:**
- Model evaluation shows high accuracy on corpus but low accuracy on new protocols
- Different reviewers produce wildly different corrections for similar criteria
- Prompt changes that should improve metrics have no effect or make them worse
- Corpus-based evaluation metrics don't correlate with expert judgment

**Phase to address:**
Phase 29-03 (Corpus Quality Assessment)

---

### Pitfall 8: Entity Disambiguation Without Context Propagation

**What goes wrong:**
UMLS grounding maps entity text to CUI without considering criterion context. "AD" maps to "Alzheimer's Disease" when protocol is about atopic dermatitis. Corpus captures incorrect grounding, polluting training data.

**Why it happens:**
Entity disambiguation is context-dependent. MedGemma agentic grounding uses UMLS MCP, which returns top matches by string similarity, not semantic fit. Agent doesn't pass protocol context or criterion category as constraints.

**How to avoid:**
- Pass protocol summary and criterion text as context to UMLS grounding agent
- Use semantic type filters: for demographics criteria, prefer semantic type "Age Group" over "Disease"
- Store grounding alternatives: `[{ cui: "C0002395", confidence: 0.8, semantic_type: "Disease" }, ...]`
- Allow reviewer to pick from alternatives in UI (disambiguation UI)
- Track grounding corrections in corpus: if reviewer changes CUI, log as training signal for disambiguation

**Warning signs:**
- Entity grounding confidence is high but obviously wrong (wrong domain)
- Reviewer repeatedly corrects same entity text to different CUI (indicates systematic error)
- Abbreviations ground incorrectly (AD, RA, MS mapped to wrong expansion)
- Corpus contains multiple CUIs for same text in similar contexts (inconsistent grounding)

**Phase to address:**
Phase 28-07 (Entity Disambiguation Polish) and Phase 29-04 (Grounding Corpus)

---

### Pitfall 9: Audit Log Query Performance Degrades with Corpus Growth

**What goes wrong:**
Audit log table grows unbounded as corpus expands (one log entry per review action). Queries for "all reviews for criterion X" or "all reviews by reviewer Y" become slow (>5s), blocking corpus export and evaluation workflows.

**Why it happens:**
`AuditLog` table has no composite indexes on common query patterns: `(target_type, target_id)` or `(actor_id, created_at)`. Full table scans occur for filtered queries. 50 protocols × 50 criteria × 3 reviews each = 7,500 rows minimum, grows to 100k+ with re-extractions.

**How to avoid:**
- Add database indexes:
  - `CREATE INDEX idx_audit_target ON audit_log(target_type, target_id, created_at DESC);`
  - `CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at DESC);`
  - `CREATE INDEX idx_audit_event ON audit_log(event_type, created_at DESC);`
- Implement audit log partitioning: archive logs older than 90 days to separate table
- Add pagination to audit log API with cursor-based navigation
- Cache frequently accessed audit queries (Redis, 5-minute TTL)

**Warning signs:**
- API endpoint `/reviews/audit-log` times out or returns 504
- Database CPU spikes when loading review page
- `EXPLAIN` shows "Seq Scan" on audit_log for filtered queries
- Corpus export script takes >10 minutes to collect review history

**Phase to address:**
Phase 29-05 (Corpus Export Performance)

---

### Pitfall 10: State Synchronization Between Edit Modes (Text vs. Structured)

**What goes wrong:**
Switching from "Modify Text" to "Modify Fields" mode loses unsaved changes. User edits text, decides to add structured fields, clicks "Modify Fields," and text edits disappear. Reverse also occurs: structured edits lost when switching to text mode.

**Why it happens:**
`editMode` state toggles between `'text'` and `'structured'`, each with separate form state. Toggling unmounts one component and mounts the other, discarding unsaved changes. No cross-mode state synchronization.

**How to avoid:**
- Persist unsaved changes in parent component state that survives mode switches
- Warn user before mode switch if unsaved changes exist: "You have unsaved text edits. Switch anyway?"
- Auto-save draft changes to localStorage on mode switch, restore on mount
- Implement unified edit mode with tabs: both text and structured editors visible, submit saves all
- Add "Cancel" button that reverts to last saved state regardless of mode

**Warning signs:**
- Users report "my changes disappeared when I clicked Modify Fields"
- Higher rate of accidental duplicate reviews (user re-enters lost changes)
- Support requests: "how do I edit both text and fields at once?"
- Audit log shows repeated modify actions for same criterion (user re-doing lost work)

**Phase to address:**
Phase 28-06 (State Management for Multi-Mode Editing)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing field_mappings in `conditions` JSONB without schema_version | Avoid database migration, fast iteration | Schema evolution breaks old data, requires manual data migration scripts | MVP only; must add versioning before multi-user pilot |
| Single reviewer per criterion for corpus | 50% faster corpus building (no dual review overhead) | Noisy gold standard, poor model generalization, unreliable evaluation | Never for production corpus; acceptable for initial prompt testing |
| Exact text match for PDF highlighting | Simple implementation, works for clean PDFs | Fails on 30-40% of criteria due to OCR artifacts, frustrates reviewers | Never; fuzzy matching is critical for usability |
| No re-extraction lock on reviewed criteria | Simpler re-extraction logic, no database constraints | Risk of destroying gold-standard data, corpus corruption | Never; lock mechanism is mandatory before corpus building |
| Mixing database IDs and useFieldArray IDs | Faster initial implementation, less mapping code | Silent data corruption, wrong records updated, impossible to debug | Never; separation is critical for data integrity |
| Loading async data with defaultValues | Seems like "default" is right, follows naming intuition | Form never populates, broken edit workflows | Never; must use `values` prop or `reset()` method |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| react-hook-form useFieldArray | Passing database objects with `id` field directly to `append()` | Rename database ID field to `database_id` or `criterion_id` before appending |
| UMLS MCP grounding | Sending entity text only, no context | Include criterion text, protocol summary, and semantic type hints in grounding request |
| PDF.js highlighting | Using `page.getTextContent()` raw output for search | Normalize whitespace, lowercase, and use fuzzy match with 90% threshold |
| JSONB field updates | Directly replacing entire JSONB column on edit | Read existing JSONB, merge changes, preserve unknown fields for forward compatibility |
| Audit log queries | Filtering by `target_id` without indexes | Add composite index `(target_type, target_id, created_at)` before launching |
| Structured editor initialization | Using hardcoded `DEFAULT_FIELD_VALUES` as fallback | Call `buildInitialValues(criterion)` to populate from AI extraction before defaulting to empty |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N+1 queries loading entities for each criterion | Review page load time >5s, database connection pool exhaustion | Batch-load all entities for batch in single query, build `entities_by_criteria` map | 20+ criteria per batch (typical is 40-60) |
| PDF.js loading full document for single-page highlight | PDF viewer initialization delay >10s for large protocols | Use PDF.js range requests with `Range` header to load target page only | Protocols >100 pages (common for phase 3 trials) |
| Audit log full table scan | `/reviews/audit-log` timeout, database CPU spike | Add composite indexes on `(target_type, target_id)`, `(actor_id, created_at)` | 5,000+ audit entries (reached after ~100 protocols reviewed) |
| Rendering 100+ field mappings in structured editor | UI freezes, React DevTools shows >5s reconciliation | Virtualize field array with `react-window`, limit visible fields to 20 at once | >50 field mappings per criterion (rare but possible for complex multi-condition criteria) |
| useFieldArray re-renders on every keystroke | Input lag, typing feels sluggish | Debounce controlled inputs, use `shouldUnregister: false` to preserve values on unmount | >10 mappings in array (noticeable lag at 20+) |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No visual feedback when PDF highlight fails | User clicks criterion, page changes, but no highlight appears. User confused: "Where is it?" | Show toast notification: "Text not found on page, showing approximate location" |
| Mode switch without save warning | User loses 5 minutes of edits, has to re-enter data | Modal confirmation: "Unsaved changes will be lost. Continue?" with "Save and Switch" option |
| Structured fields pre-populated from AI appear editable before correction | User assumes fields are human-verified, doesn't review carefully, approves with errors | Add visual indicator: "AI-extracted fields (unverified)" banner until first human edit |
| No indication which criteria need dual review for IAA | Reviewers waste time on criteria already reviewed twice | Show badge: "Needs 2nd opinion" on criteria selected for IAA sampling |
| PDF viewer reloads from page 1 on every criterion click | User has to scroll through 80-page PDF repeatedly | Cache PDF scroll position per criterion, restore on re-visit |
| Corpus export has no progress indicator | User waits 10 minutes not knowing if script is frozen or running | Stream progress: "Processing criterion 45/120... Exported 38 to corpus" |

---

## "Looks Done But Isn't" Checklist

- [ ] **Form Pre-loading:** Often missing `values` prop usage — verify form populates when navigating directly to edit page (not just from list)
- [ ] **Field Array Initialization:** Often missing database ID separation — verify updating record doesn't create duplicate or update wrong record
- [ ] **JSONB Schema Handling:** Often missing version check — verify old criteria (pre-structured-fields) load without errors
- [ ] **Re-extraction Protection:** Often missing `is_locked` flag — verify re-running extraction doesn't overwrite reviewed criteria
- [ ] **PDF Highlighting:** Often missing fuzzy match — verify highlighting works on criteria with special characters (≥, μ, line breaks)
- [ ] **Entity Context:** Often missing protocol context in grounding — verify "AD" in dermatology protocol doesn't map to Alzheimer's
- [ ] **Audit Log Performance:** Often missing composite indexes — verify `/reviews/audit-log?target_id=X` returns in <500ms with 10k+ log entries
- [ ] **Read Mode Fallback:** Often missing null checks on `field_mappings` — verify criteria created before structured feature still render
- [ ] **State Persistence:** Often missing mode-switch warning — verify unsaved changes don't vanish when toggling text/structured edit
- [ ] **Corpus Versioning:** Often missing `schema_version` in exports — verify corpus JSON includes version metadata for all records

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Database IDs overwritten by useFieldArray | HIGH | 1. Restore database from backup before corruption. 2. Implement ID separation (rename to `database_id`). 3. Add integration test: create criterion, edit, verify same ID. 4. Re-review all criteria submitted during corruption window. |
| Re-extraction overwrote reviewed criteria | HIGH | 1. Query audit log for all `review_status != NULL` criteria modified by extraction job. 2. Flag protocols needing re-review. 3. Implement `is_locked` flag and constraint. 4. Re-run reviews for affected criteria (estimate: 10 criteria × 10 min = 100 min per protocol). |
| JSONB schema mismatch breaks old criteria | MEDIUM | 1. Write migration script: `UPDATE criteria SET conditions = jsonb_set(conditions, '{schema_version}', '"v1"') WHERE conditions IS NOT NULL`. 2. Add read-time adapter in `buildInitialValues()`. 3. Test against pre-migration backup data. Deploy adapter first, then run migration. |
| PDF highlights never work | LOW | 1. Implement fuzzy text matching with Levenshtein distance (library: `fuzzysort`). 2. Add normalization: `text.toLowerCase().replace(/\s+/g, ' ')`. 3. Add fallback: search ±1 page if exact page fails. 4. No data recovery needed, purely code fix. |
| Corpus has low IAA, unreliable metrics | HIGH | 1. Sample 20 criteria, assign to 2nd reviewer. 2. Calculate IAA (Cohen's Kappa). If <0.7, increase to 50 criteria dual review. 3. Adjudicate disagreements, document rules. 4. Re-review entire corpus with updated guidelines (expensive: 50 protocols × 50 criteria × 10 min = 416 hours). |
| Audit log queries timeout | LOW | 1. Add indexes: `CREATE INDEX idx_audit_target ON audit_log(target_type, target_id);`. 2. Reindex existing data (`REINDEX TABLE audit_log`). 3. Add pagination with cursor-based API. No data recovery needed. |
| Mode switch lost unsaved changes | LOW | 1. Add localStorage persistence: save draft on mode switch, restore on mount. 2. Add warning modal with "Save and Switch" option. 3. No data recovery (changes were never persisted). Notify affected users to re-enter if recent. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Database ID conflicts (useFieldArray) | Phase 28-04 | Integration test: create criterion with 3 mappings, edit entity text, verify same database record updated (no duplicate created) |
| Async data with defaultValues | Phase 28-04 | Unit test: mock API response delayed 500ms, verify form fields populate after delay (not blank) |
| JSONB schema evolution | Phase 28-05 & 29-02 | Migration test: load pre-v1.5 criterion, verify no errors, verify all fields present after edit-save cycle |
| Re-extraction overwrites reviews | Phase 29-01 | E2E test: review criterion, re-run extraction, verify original criterion unchanged and new batch created |
| PDF highlight fuzzy matching | Phase 28-02 | Manual test: 10 criteria with special chars (≥, μ), multiline, verify all highlight on correct page |
| Read mode assumes structured | Phase 28-03 | Unit test: render criterion with `conditions = null`, verify no crash, shows fallback display |
| IAA tracking missing | Phase 29-03 | Corpus export includes `reviewer_count` field, script to calculate Kappa on dual-reviewed subset |
| Entity context missing | Phase 28-07 | Integration test: mock UMLS MCP, verify grounding request includes criterion text and protocol summary |
| Audit log slow queries | Phase 29-05 | Load test: insert 10k audit entries, query by `target_id`, verify <500ms response time |
| Mode switch loses state | Phase 28-06 | E2E test: enter text edit, switch to structured without saving, verify unsaved changes warning modal appears |

---

## Sources

### HITL and Corpus Building
- [Human-in-the-Loop AI in Document Workflows - Best Practices & Common Pitfalls](https://parseur.com/blog/hitl-best-practices)
- [Human-in-the-Loop AI (HITL) - Complete Guide to Benefits, Best Practices & Trends for 2026](https://parseur.com/blog/human-in-the-loop-ai)
- [Building and Evaluating Annotated Corpora for Medical NLP Systems - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC1839264/)
- [Building Gold Standard Corpora for Medical Natural Language Processing Tasks - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3540456/)

### React Hook Form and Form Pre-loading
- [useFieldArray | React Hook Form - Simple React forms validation](https://www.react-hook-form.com/api/usefieldarray/)
- [How do I implement useFieldArray() with prefilled/fetched data? · React Hook Form Discussion #4144](https://github.com/orgs/react-hook-form/discussions/4144)
- [React Hook Form Best Practices #1: Loading Async Data with values (Not defaultValues)](https://medium.com/@seifelmejri/react-hook-form-best-practices-1-loading-async-data-with-values-not-defaultvalues-300ed851f227)

### JSONB and Database Schema Evolution
- [On migrations, JSONB and databases in general](https://www.amberbit.com/blog/2016/2/28/on-migrations-jsonb-and-databases-in-general/)
- [JSONB: PostgreSQL's Secret Weapon for Flexible Data Modeling](https://medium.com/@richardhightower/jsonb-postgresqls-secret-weapon-for-flexible-data-modeling-cf2f5087168f)
- [PostgreSQL JSONB - Powerful Storage for Semi-Structured Data](https://www.architecture-weekly.com/p/postgresql-jsonb-powerful-storage)

### Clinical NLP and Entity Grounding
- [Improving broad-coverage medical entity linking with semantic type prediction and large-scale datasets - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8952339/)
- [UMLS Content Views Appropriate for NLP Processing of the Biomedical Literature vs. Clinical Text - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2890296/)
- [A Comprehensive Evaluation of Biomedical Entity Linking Models - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11097978/)

### Clinical Trials and Corpus Quality
- [The reporting standards of randomised controlled trials in leading medical journals between 2019 and 2020](https://link.springer.com/article/10.1007/s11845-022-02955-6)
- [Building gold standard corpora for medical natural language processing tasks - PubMed](https://pubmed.ncbi.nlm.nih.gov/23304283/)

### PDF Annotation and Evidence Linking
- [Analysis of Errors in Dictated Clinical Documents Assisted by Speech Recognition Software - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6203313/)
- [HOW TO SECURELY REDACT PDF DOCUMENTS IN 2026: MISTAKES TO AVOID](https://www.nymiz.com/how-to-securely-redact-pdf-documents-in-2026/)

### Codebase-Specific Context
- Current implementation: `/Users/noahdolevelixir/Code/medgemma-hackathon/apps/hitl-ui/src/components/CriterionCard.tsx` (lines 186-302: buildInitialValues function showing priority handling)
- Current implementation: `/Users/noahdolevelixir/Code/medgemma-hackathon/services/api-service/src/api_service/reviews.py` (lines 314-331: schema versioning strategy)
- Current implementation: `/Users/noahdolevelixir/Code/medgemma-hackathon/.planning/codebase/CONCERNS.md` (existing known issues and tech debt)

---

*Pitfalls research for: Clinical NLP HITL System - Corpus Building and Editor Polish*
*Researched: 2026-02-13*
*Confidence: HIGH - Based on official documentation, peer-reviewed research, and codebase analysis*
