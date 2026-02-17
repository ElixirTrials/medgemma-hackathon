"""LangGraph workflow definition for the consolidated protocol processor.

Defines a 5-node StateGraph for the unified protocol processing pipeline:
START -> ingest -> extract -> parse -> ground -> persist -> END

Error routing:
- After ingest, extract, parse: conditional edges route to END on error
- After ground: always proceeds to persist (ground uses error accumulation)
- Persist handles partial/total failures internally

Per user decision (v2.0 Architecture): "Flat 5-node LangGraph pipeline"
"""

import os
from typing import Any

from langgraph.graph import END, START, StateGraph

from protocol_processor.nodes.extract import extract_node
from protocol_processor.nodes.ground import ground_node
from protocol_processor.nodes.ingest import ingest_node
from protocol_processor.nodes.parse import parse_node
from protocol_processor.nodes.persist import persist_node
from protocol_processor.state import PipelineState


def should_continue(state: PipelineState) -> str:
    """Route to error END or continue to next node.

    Args:
        state: Current pipeline state.

    Returns:
        'error' if state has a fatal error, 'continue' otherwise.
    """
    return "error" if state.get("error") else "continue"


def create_graph(checkpointer: Any = None) -> Any:
    """Create and compile the 5-node protocol processing workflow graph.

    The graph follows this flow:
    START -> ingest -> extract -> parse -> ground -> persist -> END

    Conditional error routing after ingest, extract, and parse.
    Ground always proceeds to persist (ground uses error accumulation).

    Args:
        checkpointer: Optional LangGraph checkpointer for fault-tolerant execution.
            When provided, state is persisted after each node, enabling retry-from-
            checkpoint. Use PostgresSaver for production. Defaults to None (no
            checkpointing).

    Returns:
        Compiled StateGraph ready for async execution.
    """
    workflow = StateGraph(PipelineState)

    # Add all 5 nodes
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("ground", ground_node)
    workflow.add_node("persist", persist_node)

    # Entry point
    workflow.add_edge(START, "ingest")

    # Conditional error routing after ingest, extract, parse
    for source, target in [
        ("ingest", "extract"),
        ("extract", "parse"),
        ("parse", "ground"),
    ]:
        workflow.add_conditional_edges(
            source,
            should_continue,
            {"continue": target, "error": END},
        )

    # Ground always proceeds to persist (error accumulation handles partials)
    workflow.add_edge("ground", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile(checkpointer=checkpointer)


# Singleton instances for reuse across outbox handler invocations.
# Per Pitfall 1 from research: checkpointer is singleton, created once,
# reused across all invocations. Do NOT create per-invocation.
_graph = None
_checkpointer = None


def _get_checkpointer() -> Any:
    """Get or create the PostgresSaver checkpointer singleton.

    Creates a PostgresSaver using DATABASE_URL from the environment.
    Calls setup() on first creation to ensure checkpoint tables exist.

    Returns:
        PostgresSaver instance configured with the application database.

    Raises:
        KeyError: If DATABASE_URL environment variable is not set.
    """
    global _checkpointer  # noqa: PLW0603
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver

        db_url = os.environ["DATABASE_URL"]
        _checkpointer = PostgresSaver.from_conn_string(db_url)
        _checkpointer.setup()  # Create checkpoint tables if they don't exist
    return _checkpointer


def get_graph() -> Any:
    """Get or create the compiled graph singleton.

    Compiles the graph with a PostgresSaver checkpointer if DATABASE_URL
    is available. Falls back to no checkpointer if DATABASE_URL is not set
    (e.g. in unit tests).

    Returns:
        Compiled StateGraph instance.
    """
    global _graph  # noqa: PLW0603
    if _graph is None:
        try:
            checkpointer = _get_checkpointer()
        except (KeyError, Exception):
            # DATABASE_URL not set (e.g. unit tests) — compile without checkpointer
            checkpointer = None
        _graph = create_graph(checkpointer=checkpointer)
    return _graph
