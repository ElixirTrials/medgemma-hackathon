"""Entity Grounding Agent Service.

This agent handles entity extraction and UMLS/SNOMED grounding
using a LangGraph workflow triggered by CriteriaExtracted events.
"""

from .graph import create_graph, get_graph
from .state import GroundingState
from .trigger import handle_criteria_extracted

__all__ = [
    "GroundingState",
    "create_graph",
    "get_graph",
    "handle_criteria_extracted",
]
