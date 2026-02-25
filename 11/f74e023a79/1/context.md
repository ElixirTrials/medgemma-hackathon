# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Fix Protocol Status & Review Page Visibility During Grounding

## Context

Two related bugs in the current pipeline:

1. **CriteriaBatch is created with `status="pending_review"` in `parse_node` (line 95)** — before grounding even starts. This makes the batch appear in the Review Queue immediately, with a misleading "pending review" status while entities are still being grounded.

2. **ProtocolDetail shows the "Review Criteria" button for any protocol that has ...

### Prompt 2

I see another issue that keeps sneeking back in. In the criteria page it seems like the easy age between 18 and 65 years is not grounding properly.

