"""LangGraph workflow definition for the entity grounding agent.

Defines a 2-node StateGraph for the agentic grounding workflow:
START -> medgemma_ground -> validate_confidence -> END

The medgemma_ground node implements an iterative agentic loop where
MedGemma extracts entities, searches UMLS via MCP concept_search,
and evaluates results (max 3 iterations per criterion batch).

Conditional error routing after medgemma_ground:
if state["error"] is set, routes directly to END.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import medgemma_ground_node, validate_confidence_node
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
    """Create and compile the 2-node grounding workflow graph.

    The graph follows this flow:
    START -> medgemma_ground -> validate_confidence -> END

    After medgemma_ground, conditional edges check for errors
    and route to END if any are found.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(GroundingState)

    workflow.add_node("medgemma_ground", medgemma_ground_node)
    workflow.add_node("validate_confidence", validate_confidence_node)

    workflow.add_edge(START, "medgemma_ground")
    workflow.add_conditional_edges(
        "medgemma_ground",
        should_continue,
        {"continue": "validate_confidence", "error": END},
    )
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
