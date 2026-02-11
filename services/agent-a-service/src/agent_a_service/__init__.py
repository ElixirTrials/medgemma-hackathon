"""Criteria Extraction Agent Service.

This agent handles clinical trial protocol criteria extraction
workflows using LangGraph.
"""

from .graph import create_graph, get_graph
from .state import ExtractionState

__all__ = ["ExtractionState", "create_graph", "get_graph"]
