# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Fix: Set max_output_tokens on All Gemini Calls

## Context

Two production symptoms — **repeated garbage strings** (`"51079815107981..."`) in field mappings and **empty decomposition returns** causing full-text entities — share a single root cause:

**Every `ChatGoogleGenerativeAI` instantiation in the pipeline is missing `max_output_tokens`.**

Without an output cap, Gemini can enter repetition loops producing unbounded garbage. This also increases latency, ...

### Prompt 2

check that ruff and mypy and all pytests pass.

### Prompt 3

Check against the golden test json and show me what you get.

### Prompt 4

We already managed earlier to get 5/5 UCUM and OMOP unit matches - what has changed?

