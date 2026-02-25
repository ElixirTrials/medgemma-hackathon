# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Extract All Hardcoded Prompts to Jinja2 Templates

## Context

7 LLM prompts are hardcoded as Python f-strings across 4 tool files. The rest of the codebase uses Jinja2 templates from `prompts/`. This inconsistency makes prompt iteration harder (as we just experienced with field_mapper A/B testing) and scatters prompt logic across tool code. There are also 3 redundant template-loading mechanisms that should be consolidated into one.

---

## Step 1: Consolidate T...

### Prompt 2

Can you help me resolve any mypy or pytest failures? Currently I see "tests/e2e/run_prompt_variants.py:38: error: Cannot find implementation or library stub for module named "prompt_variants"  [import-not-found]
tests/e2e/run_prompt_variants.py:38: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
Found 1 error in 1 file (checked 117 source files)"

