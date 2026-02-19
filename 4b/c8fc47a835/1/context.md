# Session Context

## User Prompts

### Prompt 1

You have mypy errors. Check that you don't have pytest failures.

### Prompt 2

In dev, we should be using a local mlflow rather from the docker so we can use claude mlflow assistant.

### Prompt 3

[Request interrupted by user]

### Prompt 4

Make run-dev is for local. when are we supposed to use make-infra? And for prod, how do we end up with the mlflow docker?

### Prompt 5

Make sure the local mlflow is using sql. Also, it seems like the whole graph is being traced as one one trace so we can't see the tool calls, gemini and medgemma traces as they come in. Is there a way to log each of these as seperate traces but group them by session?

### Prompt 6

Can you confirm we are running grounding in parallel and in batches?

