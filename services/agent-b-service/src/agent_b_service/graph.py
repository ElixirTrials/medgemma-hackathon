"""LangGraph workflow definition for the entity grounding agent.

Placeholder graph (process -> finalize) will be replaced with the
4-node grounding workflow in Plan 05-03:
extract_entities -> ground_to_umls -> map_to_snomed -> validate_confidence
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import finalize_node, process_node
from .state import GroundingState


def create_graph() -> Any:
    """Create and compile the agent workflow graph.

    The graph follows this flow:
    START -> process -> finalize -> END

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(GroundingState)

    # Add nodes
    workflow.add_node("process", process_node)
    workflow.add_node("finalize", finalize_node)

    # Define edges
    workflow.add_edge(START, "process")
    workflow.add_edge("process", "finalize")
    workflow.add_edge("finalize", END)

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
