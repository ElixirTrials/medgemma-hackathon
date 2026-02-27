# Session Context

## User Prompts

### Prompt 1

<context>
**Flags:**
- `--auto` — Automatic mode. After config questions, runs research → requirements → roadmap without further interaction. Expects idea document via @ reference.
</context>

<objective>
Initialize a new project through unified flow: questioning → research (optional) → requirements → roadmap.

**Creates:**
- `.planning/PROJECT.md` — project context
- `.planning/config.json` — workflow preferences
- `.planning/research/` — domain research (optional)
- `.plannin...

### Prompt 2

<objective>
Extract implementation decisions that downstream agents need — researcher and planner will use CONTEXT.md to know what to investigate and what choices are locked.

**How it works:**
1. Analyze the phase to identify gray areas (UI, UX, behavior, etc.)
2. Present gray areas — user selects which to discuss
3. Deep-dive each selected area until satisfied
4. Create CONTEXT.md with decisions that guide research and planning

**Output:** `{phase_num}-CONTEXT.md` — decisions clear enou...

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

<objective>
Create executable phase prompts (PLAN.md files) for a roadmap phase with integrated research and verification.

**Default flow:** Research (if needed) → Plan → Verify → Done

**Orchestrator role:** Parse arguments, validate phase, research domain (unless skipped), spawn gsd-planner, verify with gsd-plan-checker, iterate until pass or max iterations, present results.
</objective>

<execution_context>
@/Users/noahdolevelixir/.claude-elixirtrials/get-shit-done/workflows/plan-phase...

### Prompt 5

<objective>
Execute all plans in a phase using wave-based parallel execution.

Orchestrator stays lean: discover plans, analyze dependencies, group into waves, spawn subagents, collect results. Each subagent loads the full execute-plan context and handles its own plan.

Context budget: ~15% orchestrator, 100% fresh per subagent.
</objective>

<execution_context>
@/Users/noahdolevelixir/.claude-elixirtrials/get-shit-done/workflows/execute-phase.md
@/Users/noahdolevelixir/.claude-elixirtrials/get-...

### Prompt 6

<objective>
Extract implementation decisions that downstream agents need — researcher and planner will use CONTEXT.md to know what to investigate and what choices are locked.

**How it works:**
1. Analyze the phase to identify gray areas (UI, UX, behavior, etc.)
2. Present gray areas — user selects which to discuss
3. Deep-dive each selected area until satisfied
4. Create CONTEXT.md with decisions that guide research and planning

**Output:** `{phase_num}-CONTEXT.md` — decisions clear enou...

### Prompt 7

This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Analysis:
Let me chronologically analyze the conversation:

1. **Initial Request**: User invoked `/gsd:new-project` with `--auto` flag, providing a deployment issues report and the directive: "Bottomline, we want to deploy this app without breaking the fact that it works locally. Get it done"

2. **Setup Phase**: Ran `gsd-tools.cjs init new-proj...

### Prompt 8

This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Analysis:
Let me chronologically analyze the conversation:

1. **Session Start**: This is a continuation session from a previous conversation that ran out of context. The previous session completed Phases 1-2 of a 3-phase MedGemma deployment fix project, and was about to start Phase 3 discuss-phase.

2. **Phase 3 Context Creation**: I created `....

### Prompt 9

This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Analysis:
Let me chronologically analyze the conversation:

1. **Session Start**: This is a continuation from a previous conversation that ran out of context. The previous session completed Phases 1-3 of a deployment fix project. The summary tells us two critical bugs remained:
   - `psycopg.OperationalError: the connection is closed` - LangGrap...

### Prompt 10

This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Analysis:
Let me chronologically analyze the conversation:

1. **Session Start**: This is a continuation from a previous conversation that ran out of context. The previous session completed Phases 1-3 of a deployment fix project. Key bugs were fixed:
   - Gemini API key missing in production → Vertex AI ADC fallback
   - LangGraph checkpoint c...

### Prompt 11

This is completly wrong. It creates silent failures and unneccary fallbacks. We want the gemini client to work and for the api key to be set not to fallback to something we didn't design. We want to use the file API which is why we use the gemini client. We want to use UMLS and not just continue if for some reason the key isn't set. CRITICAL: NO SILENT FAILURES. CRITICAL: NO FALLBACKS. CRITICAL: Working deployed code. CRITICAL: No changes to logic, models, etc. The deployed should work the same ...

### Prompt 12

I see this error in the review page: "Failed to load PDF: Setting up fake worker failed: "Failed to fetch dynamically imported module: https://frontend-1074735463071.europe-west4.run.app/assets/pdf.worker.min-qwK7q_zL.mjs"."

