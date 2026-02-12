"""Graph compilation tests for grounding-service grounding workflow."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


from grounding_service.graph import create_graph, get_graph, should_continue


def test_create_graph_returns_compiled() -> None:
    graph = create_graph()
    assert hasattr(graph, "get_graph")
    assert hasattr(graph, "invoke")
    assert "Compiled" in type(graph).__name__ or "StateGraph" in type(graph).__name__


def test_graph_has_two_nodes() -> None:
    graph = create_graph()
    g = graph.get_graph()
    nodes = list(g.nodes) if hasattr(g, "nodes") else list(g.nodes())
    node_names = set(nodes)
    assert "medgemma_ground" in node_names
    assert "validate_confidence" in node_names
    # Old nodes should NOT be present
    assert "extract_entities" not in node_names
    assert "ground_to_umls" not in node_names
    assert "map_to_snomed" not in node_names


def test_should_continue_returns_error_when_state_has_error() -> None:
    assert should_continue({"error": "fail"}) == "error"


def test_should_continue_returns_continue_when_no_error() -> None:
    assert should_continue({}) == "continue"


def test_get_graph_singleton() -> None:
    g1 = get_graph()
    g2 = get_graph()
    assert g1 is g2
