# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Plan: Failure Analysis & Test Snippet Generator

## Context

The extraction/grounding pipeline sometimes fails completely — protocols stuck in `extraction_failed` / `grounding_failed`, or entities that end up with **no code, no relation, or no value** at all. These are the "hard cases" that the pipeline couldn't handle. This script harvests only those total failures into `tests/e2e/test_snippets.json` so we build a regression suite of genuinely difficult cases....

### Prompt 2

Your recent changes have led to failure all around. Perform a thorough investigation and try to diagnose the problem: "instructions/SubmissionRequirements/grounding_failures/Screenshot 2026-02-24 at 17.07.45.png"

