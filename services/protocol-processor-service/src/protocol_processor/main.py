"""Protocol Processor Service entrypoint.

Exposes get_graph() for import by api-service and provides a minimal
module for standalone graph inspection.
"""

from protocol_processor.graph import create_graph, get_graph

__all__ = ["create_graph", "get_graph"]
