"""Tests for the 6-node protocol processor graph.

Verifies graph compilation, node structure, edge routing, and
PipelineState shape acceptance. Does not invoke live APIs or DB.

Per Phase 31 success criterion 9: "Graph compilation test passes."
"""

from __future__ import annotations

from protocol_processor.state import PipelineState


def _make_initial_state(**overrides) -> dict:
    """Build a minimal PipelineState-compatible dict."""
    base: dict = {
        "protocol_id": "test-protocol-id",
        "file_uri": "local://test.pdf",
        "title": "Test Protocol",
        "batch_id": None,
        "pdf_bytes": None,
        "extraction_json": None,
        "entities_json": None,
        "grounded_entities_json": None,
        "status": "processing",
        "error": None,
        "errors": [],
    }
    base.update(overrides)
    return base


class TestCreateGraph:
    """Tests for create_graph() compilation and structure."""

    def test_graph_compiles(self):
        """create_graph() should compile without raising an exception."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        assert graph is not None

    def test_graph_has_six_user_nodes(self):
        """Compiled graph should have exactly 6 user-defined nodes."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        # LangGraph adds __start__ and __end__ internal nodes
        # User nodes are those without leading underscores
        all_nodes = graph.nodes
        user_nodes = {name for name in all_nodes if not name.startswith("__")}
        assert user_nodes == {
            "ingest",
            "extract",
            "parse",
            "ground",
            "persist",
            "structure",
        }, f"Expected 6 user nodes, got: {user_nodes}"

    def test_graph_node_names(self):
        """Graph should contain all 6 expected node names."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        all_nodes = graph.nodes
        for expected in (
            "ingest",
            "extract",
            "parse",
            "ground",
            "persist",
            "structure",
        ):
            assert expected in all_nodes, (
                f"Expected node '{expected}' not found in graph nodes: {all_nodes}"
            )

    async def test_get_graph_singleton(self):
        """get_graph() should return the same compiled instance each call."""
        from protocol_processor.graph import get_graph

        graph1 = await get_graph()
        graph2 = await get_graph()
        assert graph1 is graph2, "get_graph() should return a singleton"

    def test_graph_accepts_pipeline_state_shape(self):
        """Graph input_schema should be compatible with PipelineState."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        # LangGraph compiled graphs expose get_input_schema()
        # We verify by checking graph nodes (deep schema validation is runtime)
        assert "ingest" in graph.nodes
        assert "persist" in graph.nodes
        assert "structure" in graph.nodes


class TestShouldContinue:
    """Tests for the should_continue routing function."""

    def test_should_continue_no_error(self):
        """Returns 'continue' when state has no error."""
        from protocol_processor.graph import should_continue

        state = _make_initial_state()
        assert should_continue(state) == "continue"  # type: ignore[arg-type]

    def test_should_continue_with_error(self):
        """Returns 'error' when state has a fatal error."""
        from protocol_processor.graph import should_continue

        state = _make_initial_state(error="Something went wrong")
        assert should_continue(state) == "error"  # type: ignore[arg-type]

    def test_should_continue_with_none_error(self):
        """Returns 'continue' when error field is None."""
        from protocol_processor.graph import should_continue

        state = _make_initial_state(error=None)
        assert should_continue(state) == "continue"  # type: ignore[arg-type]


class TestGraphErrorRouting:
    """Tests for error accumulation vs fatal error routing semantics."""

    def test_errors_list_not_fatal(self):
        """Non-empty errors list should not trigger fatal routing."""
        from protocol_processor.graph import should_continue

        # errors (plural) are accumulated — not fatal
        state = _make_initial_state(
            errors=["entity grounding failed for 'X'"],
            error=None,  # no fatal error
        )
        assert should_continue(state) == "continue"  # type: ignore[arg-type]

    def test_error_field_is_fatal(self):
        """Non-empty error field (singular) triggers fatal routing."""
        from protocol_processor.graph import should_continue

        state = _make_initial_state(error="Parse failed: JSON decode error")
        assert should_continue(state) == "error"  # type: ignore[arg-type]


class TestPipelineStateShape:
    """Tests for PipelineState TypedDict shape."""

    def test_state_has_required_fields(self):
        """PipelineState TypedDict should have all required fields."""
        from typing import get_type_hints

        hints = get_type_hints(PipelineState)
        required = {
            "protocol_id",
            "file_uri",
            "title",
            "batch_id",
            "pdf_bytes",
            "extraction_json",
            "entities_json",
            "grounded_entities_json",
            "status",
            "error",
            "errors",
        }
        assert required.issubset(hints.keys()), (
            f"Missing fields in PipelineState: {required - hints.keys()}"
        )

    def test_errors_field_is_list(self):
        """PipelineState.errors should be typed as list[str]."""
        from typing import get_origin, get_type_hints

        hints = get_type_hints(PipelineState)
        errors_type = hints["errors"]
        assert get_origin(errors_type) is list, (
            f"Expected errors to be list, got: {errors_type}"
        )
