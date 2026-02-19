# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Plan: Dual-mode MLflow (Docker for prod, local for dev+Assistant)

## Context

MLflow was moved out of Docker to enable the MLflow Assistant beta (which requires a local server process to connect to Claude Code). However, for production deployments we need MLflow running in Docker alongside the rest of the stack. The Makefile also has stale references to a `mlflow` Docker service that no longer exists.

**Goal:** Support both modes via Docker Compose profiles —...

