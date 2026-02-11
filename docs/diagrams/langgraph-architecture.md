# LangGraph Architecture

```mermaid
graph TB
    subgraph Presentation["UI Layer"]
        HITL[HITL Review UI]
    end

    subgraph Application["Application Layer"]
        API[API Service]
        ExtractSvc[Extraction Service]
        GroundSvc[Grounding Service]
        UMLS[UMLS MCP Server]
    end

    subgraph ExtractGraph["Extraction Graph (LangGraph)"]
        Ingest[Ingest Node] --> ExtractNode[Extract Node]
        ExtractNode --> Parse[Parse Node]
        Parse --> Queue[Queue Node]
    end

    subgraph GroundGraph["Grounding Graph (LangGraph)"]
        ExtEntities[Extract Entities] --> GroundUMLS[Ground to UMLS]
        GroundUMLS --> MapSNOMED[Map to SNOMED]
        MapSNOMED --> Validate[Validate Confidence]
    end

    subgraph Data["Data Layer"]
        DB[(PostgreSQL)]
        GCS[(GCS Bucket)]
    end

    subgraph AI["AI Services"]
        Gemini[Gemini API]
        MedGemma[MedGemma / Vertex AI]
        UMLSApi[UMLS REST API]
    end

    HITL --> API
    API --> ExtractSvc
    API --> GroundSvc

    ExtractSvc --> ExtractGraph
    GroundSvc --> GroundGraph
    GroundSvc --> UMLS

    ExtractNode --> Gemini
    ExtEntities --> MedGemma
    UMLS --> UMLSApi

    API --> DB
    API --> GCS

    classDef ui fill:#e1f5ff,stroke:#007acc,color:#000,stroke-width:2px;
    classDef service fill:#d4f1d4,stroke:#28a745,color:#000,stroke-width:2px;
    classDef graph fill:#ffe5cc,stroke:#fd7e14,color:#000,stroke-width:2px;
    classDef data fill:#fff3cd,stroke:#ffc107,color:#000,stroke-width:2px;
    classDef ai fill:#f0f0f0,stroke:#666,color:#000,stroke-width:2px;

    class Presentation ui;
    class Application service;
    class ExtractGraph,GroundGraph graph;
    class Data data;
    class AI ai;
```
