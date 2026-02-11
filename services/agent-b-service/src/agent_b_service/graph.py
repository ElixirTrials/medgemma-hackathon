"""LangGraph workflow definition for the entity grounding agent.

Defines a 4-node StateGraph for the grounding workflow:
START -> extract_entities -> ground_to_umls ->
         map_to_snomed -> validate_confidence -> END

Conditional error routing after extract_entities and ground_to_umls:
if state["error"] is set, routes directly to END.
map_to_snomed -> validate_confidence is unconditional.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import (
    extract_entities_node,
    ground_to_umls_node,
    map_to_snomed_node,
    validate_confidence_node,
)
from .state import GroundingState


def should_continue(state: GroundingState) -> str:
    """Route to error END or continue to next node.

    Args:
        state: Current grounding state.

    Returns:
        'error' if state has an error, 'continue' otherwise.
    """
    return "error" if state.get("error") else "continue"


def create_graph() -> Any:
    """Create and compile the 4-node grounding workflow graph.

    The graph follows this flow:
    START -> extract_entities -> ground_to_umls -> map_to_snomed
          -> validate_confidence -> END

    After extract_entities and ground_to_umls, conditional edges check
    for errors and route to END if any are found. map_to_snomed and
    validate_confidence always proceed to the next step.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(GroundingState)

    # Add nodes
    workflow.add_node("extract_entities", extract_entities_node)
    workflow.add_node("ground_to_umls", ground_to_umls_node)
    workflow.add_node("map_to_snomed", map_to_snomed_node)
    workflow.add_node("validate_confidence", validate_confidence_node)

    # Define edges with conditional error routing
    workflow.add_edge(START, "extract_entities")
    workflow.add_conditional_edges(
        "extract_entities",
        should_continue,
        {
            "continue": "ground_to_umls",
            "error": END,
        },
    )
    workflow.add_conditional_edges(
        "ground_to_umls",
        should_continue,
        {
            "continue": "map_to_snomed",
            "error": END,
        },
    )
    workflow.add_edge("map_to_snomed", "validate_confidence")
    workflow.add_edge("validate_confidence", END)

    return workflow.compile()


# Singleton instance for reuse
_graph = None


def get_graph() -> Any:
    """Get or create the compiled graph instance.

    Returns:
        Compiled StateGraph instance.
    """
    global _graph  # noqa: PLW0603
    if _graph is None:
        _graph = create_graph()
    return _graph
