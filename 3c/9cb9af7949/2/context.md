# Session Context

## User Prompts

### Prompt 1

<objective>
Check project progress, summarize recent work and what's ahead, then intelligently route to the next action - either executing an existing plan or creating the next one.

Provides situational awareness before continuing work.
</objective>

<execution_context>
@/Users/noahdolevelixir/.claude-elixirtrials/get-shit-done/workflows/progress.md
</execution_context>

<process>
Execute the progress workflow from @/Users/noahdolevelixir/.claude-elixirtrials/get-shit-done/workflows/progress.md...

### Prompt 2

/gsd:discuss-phase 42

### Prompt 3

<objective>
Extract implementation decisions that downstream agents need — researcher and planner will use CONTEXT.md to know what to investigate and what choices are locked.

**How it works:**
1. Analyze the phase to identify gray areas (UI, UX, behavior, etc.)
2. Present gray areas — user selects which to discuss
3. Deep-dive each selected area until satisfied
4. Create CONTEXT.md with decisions that guide research and planning

**Output:** `{phase_num}-CONTEXT.md` — decisions clear enou...

### Prompt 4

Where are these queries coming from? The user?

### Prompt 5

<objective>
Create executable phase prompts (PLAN.md files) for a roadmap phase with integrated research and verification.

**Default flow:** Research (if needed) → Plan → Verify → Done

**Orchestrator role:** Parse arguments, validate phase, research domain (unless skipped), spawn gsd-planner, verify with gsd-plan-checker, iterate until pass or max iterations, present results.
</objective>

<execution_context>
@/Users/noahdolevelixir/.claude-elixirtrials/get-shit-done/workflows/plan-phase...

