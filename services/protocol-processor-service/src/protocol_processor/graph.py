"""LangGraph workflow definition for the consolidated protocol processor.

Defines a 5-node StateGraph for the unified protocol processing pipeline:
START -> ingest -> extract -> parse -> ground -> persist -> END

Error routing:
- After ingest, extract, parse: conditional edges route to END on error
- After ground: always proceeds to persist (ground uses error accumulation)
- Persist handles partial/total failures internally

Per user decision (v2.0 Architecture): "Flat 5-node LangGraph pipeline"
"""

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


def create_graph() -> Any:
    """Create and compile the 5-node protocol processing workflow graph.

    The graph follows this flow:
    START -> ingest -> extract -> parse -> ground -> persist -> END

    Conditional error routing after ingest, extract, and parse.
    Ground always proceeds to persist (ground uses error accumulation).

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

    return workflow.compile()


# Singleton instance for reuse across outbox handler invocations
_graph = None


def get_graph() -> Any:
    """Get or create the compiled graph singleton.

    Returns:
        Compiled StateGraph instance.
    """
    global _graph  # noqa: PLW0603
    if _graph is None:
        _graph = create_graph()
    return _graph
