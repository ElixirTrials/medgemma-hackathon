# Session Context

## User Prompts

### Prompt 1

My tests take a long time to complete and should be more limited than an entire extraction-grounding loop (like only a few criteria). Also, we want to investigate, using the mlflow tracing, why the process is so time consuming. Where are the bottlenecks. Write me a root cause and comprehensive but concise report.

### Prompt 2

Let's proceed to make a branch which we'll merge to this branch for this improvement. Then create a written plan where the first phase is investigation and the following phases are implementation.

### Prompt 3

What about the investigation into:   - MedGemma cold start: Determine if there's a keep-warm or provisioned-throughput option on Vertex AI Model Garden; the 308s outlier is unacceptable
  - Agentic retry trigger rate: Add logging/tracing for what % of entities hit the retry loop; if >30%, the threshold (confidence < 0.5) may be too aggressive. Let's do all the investigation in phase 1.

