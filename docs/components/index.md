# Components Overview

This page provides an overview of all microservices and shared libraries in this monorepo.

## Available Components

| Component | Description |
| :--- | :--- |
| **extraction-service** | Criteria extraction workflow using Gemini to extract structured inclusion/exclusion criteria from protocol PDFs. |
| **grounding-service** | Entity grounding workflow using MedGemma and UMLS MCP to map medical entities to SNOMED codes. |
| **api-service** | The API Service is the central orchestrator for the application. It provides HTTP endpoints for the frontend, manages database persistence, and triggers background extraction and grounding workflows. |
| **data-pipeline** | This component handles data ingestion (ETL), normalization, and preparation for the API or training. |
| **evaluation** | This component runs offline evaluation benchmarks against your agents. |
| **events-py** | Shared event envelope shapes and helpers used by Python services that publish or consume events. |
| **events-ts** | Shared event shapes and helpers used by TypeScript services that publish or consume events. |
| **hitl-ui** | React/Vite application for Human-in-the-Loop review workflows. Clinical researchers review, approve, edit, or reject AI-extracted criteria and grounded entities. |
| **inference** | This component acts as the "Standard Library" for AI in this repository. It centralizes model loading, prompt rendering, and agent construction to ensure consistency across all services. |
| **model-training** | This component handles fine-tuning (LoRA), distillation, or training of custom models. |
| **shared** | This component holds code that is strictly **common** to multiple components. |
| **shared-ts** | This library provides common types (e.g. `Result`) and small utilities used across TypeScript services and apps. |

API reference documentation for individual components will be added in subsequent documentation phases.
