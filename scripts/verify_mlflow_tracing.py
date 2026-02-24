"""Verify MLflow per-node tracing: independent traces, grouping tags,
and real-time appearance (traces show up as nodes complete, not batched).

Run:  uv run python scripts/verify_mlflow_tracing.py
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import operator
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

# ---- Setup ----
tmpdir = tempfile.mkdtemp(prefix="mlflow_trace_test_")
tracking_uri = f"file://{tmpdir}"
os.environ["MLFLOW_TRACKING_URI"] = tracking_uri

import mlflow  # noqa: E402 — must set MLFLOW_TRACKING_URI before importing

mlflow.set_tracking_uri(tracking_uri)
mlflow.set_experiment("trace-test")

# ---- tracing.py mirror ----
_run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pipeline_run_id", default=""
)


@contextmanager
def pipeline_span(name: str, protocol_id: str = ""):
    with mlflow.start_span(name=name, span_type="CHAIN") as span:
        tags: dict[str, str] = {"node": name}
        if protocol_id:
            tags["protocol_id"] = protocol_id
        rid = _run_id_var.get()
        if rid:
            tags["run_id"] = rid
        try:
            mlflow.update_current_trace(tags=tags)
        except Exception as e:
            # Non-fatal: tag updates failing shouldn't break verification runs
            logging.getLogger(__name__).debug("Trace tag update failed: %s", e)
        yield span


def count_traces() -> int:
    client = mlflow.MlflowClient()
    exp = client.get_experiment_by_name("trace-test")
    if not exp:
        return 0
    return len(client.search_traces(experiment_ids=[exp.experiment_id]))


def get_traces() -> list[dict]:
    client = mlflow.MlflowClient()
    exp = client.get_experiment_by_name("trace-test")
    if not exp:
        return []
    traces = client.search_traces(experiment_ids=[exp.experiment_id])
    out = []
    for t in traces:
        root = t.data.spans[0] if t.data.spans else None
        out.append(
            {
                "name": root.name if root else "?",
                "tags": {
                    k: v
                    for k, v in (t.info.tags or {}).items()
                    if not k.startswith("mlflow.")
                },
            }
        )
    return sorted(out, key=lambda x: x["name"])


# ---- Graph with delay to observe real-time behavior ----
class S(TypedDict):
    value: int
    trace_counts: Annotated[list[int], operator.add]  # accumulates across nodes


async def node_a(state: S) -> dict[str, Any]:
    with pipeline_span("node_a", protocol_id="proto-X") as sp:
        sp.set_inputs({"v": state["value"]})
        await asyncio.sleep(0.1)
        sp.set_outputs({"r": state["value"] + 1})
    # After span closes, trace should be flushed — check count
    n = count_traces()
    return {"value": state["value"] + 1, "trace_counts": [n]}


async def node_b(state: S) -> dict[str, Any]:
    with pipeline_span("node_b", protocol_id="proto-X") as sp:
        sp.set_inputs({"v": state["value"]})
        await asyncio.sleep(0.1)
        sp.set_outputs({"r": state["value"] * 2})
    n = count_traces()
    return {"value": state["value"] * 2, "trace_counts": [n]}


async def node_c(state: S) -> dict[str, Any]:
    with pipeline_span("node_c", protocol_id="proto-X") as sp:
        sp.set_inputs({"v": state["value"]})
        await asyncio.sleep(0.1)
        sp.set_outputs({"r": state["value"] + 10})
    n = count_traces()
    return {"value": state["value"] + 10, "trace_counts": [n]}


def build():
    g = StateGraph(S)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_node("c", node_c)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", END)
    return g.compile()


async def _run(graph: Any) -> dict:
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("trace-test")
    _run_id_var.set("proto-X:run-42")
    return await graph.ainvoke({"value": 1, "trace_counts": []})


def sync_handler(graph: Any) -> dict:
    return asyncio.run(_run(graph))


def main():
    print(f"MLflow tracking: {tracking_uri}\n")

    graph = build()

    # Run in thread executor (mirrors production outbox pattern)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="outbox")
    ctx = contextvars.copy_context()
    future = executor.submit(ctx.run, sync_handler, graph)
    result = future.result(timeout=30)
    executor.shutdown(wait=True)

    trace_counts = result["trace_counts"]
    traces = get_traces()

    # ---- Real-time check ----
    print("1. REAL-TIME TRACE APPEARANCE")
    print(f"   Traces visible after node_a: {trace_counts[0]}")
    print(f"   Traces visible after node_b: {trace_counts[1]}")
    print(f"   Traces visible after node_c: {trace_counts[2]}")
    realtime_ok = trace_counts[0] >= 1 and trace_counts[1] >= 2 and trace_counts[2] >= 3
    print(f"   Incremental: {'YES' if realtime_ok else 'NO'}")
    print()

    # ---- Independent traces check ----
    print("2. INDEPENDENT TRACES")
    print(f"   Total: {len(traces)}")
    for t in traces:
        print(f"     {t['name']:15s}  {t['tags']}")
    independent_ok = len(traces) == 3 and sorted(t["name"] for t in traces) == [
        "node_a",
        "node_b",
        "node_c",
    ]
    print(f"   3 separate traces: {'YES' if independent_ok else 'NO'}")
    print()

    # ---- Grouping tags check ----
    print("3. GROUPING TAGS")
    tags = [t["tags"] for t in traces]
    run_ids = {t.get("run_id") for t in tags}
    proto_ids = {t.get("protocol_id") for t in tags}
    nodes = sorted(t.get("node", "") for t in tags)
    tags_ok = (
        run_ids == {"proto-X:run-42"}
        and proto_ids == {"proto-X"}
        and nodes == ["node_a", "node_b", "node_c"]
    )
    print(f"   Shared run_id:      {run_ids}")
    print(f"   Shared protocol_id: {proto_ids}")
    print(f"   Distinct node tags: {nodes}")
    print(f"   Consistent: {'YES' if tags_ok else 'NO'}")
    print()

    # ---- Verdict ----
    print("=" * 50)
    if realtime_ok and independent_ok and tags_ok:
        print("ALL CHECKS PASSED")
    else:
        failures = []
        if not realtime_ok:
            failures.append("real-time")
        if not independent_ok:
            failures.append("independence")
        if not tags_ok:
            failures.append("tags")
        print(f"FAILED: {', '.join(failures)}")
    print("=" * 50)

    del os.environ["MLFLOW_TRACKING_URI"]
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
