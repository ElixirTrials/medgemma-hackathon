"""LangGraph workflow definition for the criteria extraction agent.

Defines a 4-node StateGraph for the extraction workflow:
START -> ingest -> extract -> parse -> queue -> END

Each node has conditional error routing: if any node sets state["error"],
the graph routes directly to END, skipping downstream nodes.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import extract_node, ingest_node, parse_node, queue_node
from .state import ExtractionState


def should_continue(state: ExtractionState) -> str:
    """Route to error END or continue to next node.

    Args:
        state: Current extraction state.

    Returns:
        'error' if state has an error, 'continue' otherwise.
    """
    return "error" if state.get("error") else "continue"


def create_graph() -> Any:
    """Create and compile the 4-node extraction workflow graph.

    The graph follows this flow:
    START -> ingest -> extract -> parse -> queue -> END

    After ingest and extract, conditional edges check for errors
    and route to END if any are found. Parse and queue always
    proceed to the next step (they handle errors internally).

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExtractionState)

    # Add nodes
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("queue", queue_node)

    # Define edges with conditional error routing
    workflow.add_edge(START, "ingest")
    workflow.add_conditional_edges(
        "ingest",
        should_continue,
        {
            "continue": "extract",
            "error": END,
        },
    )
    workflow.add_conditional_edges(
        "extract",
        should_continue,
        {
            "continue": "parse",
            "error": END,
        },
    )
    workflow.add_edge("parse", "queue")
    workflow.add_edge("queue", END)

    return workflow.compile()


# Singleton instance for reuse
_graph = None


def get_graph() -> Any:
    """Get or create the compiled graph instance.

    Returns:
        Compiled StateGraph instance.
    """
    global _graph
    if _graph is None:
        _graph = create_graph()
    return _graph
