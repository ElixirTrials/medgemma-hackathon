"""Delete all runs and traces from the MLflow tracking server.

Uses MLFLOW_TRACKING_URI from the environment (e.g. http://localhost:5001).
Requires mlflow (run with: uv run --group dev python scripts/clear_mlflow_traces.py).
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mlflow.tracking import MlflowClient


def _delete_traces_for_experiment(
    client: MlflowClient, experiment_id: str, max_results: int = 1000
) -> int:
    """Delete all traces in an experiment. Returns number of traces deleted."""
    total_deleted = 0
    page_token: str | None = None
    while True:
        result = client.search_traces(
            experiment_ids=[experiment_id],
            max_results=max_results,
            page_token=page_token,
        )
        trace_ids = [t.info.request_id for t in result]
        if not trace_ids:
            break
        try:
            n = client.delete_traces(
                experiment_id=experiment_id,
                trace_ids=trace_ids,
            )
            total_deleted += n
        except (AttributeError, TypeError) as e:
            print(
                f"  delete_traces not available: {e}",
                file=sys.stderr,
            )
            break
        page_token = getattr(result, "token", None)
        if not page_token:
            break
    return total_deleted


def main() -> int:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        print(
            "mlflow is not installed. Run: uv run --group dev python scripts/clear_mlflow_traces.py",
            file=sys.stderr,
        )
        return 1

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    try:
        experiments = client.search_experiments()
    except Exception as e:
        print(f"Cannot reach MLflow at {tracking_uri}: {e}", file=sys.stderr)
        return 1

    runs_deleted = 0
    traces_deleted = 0
    for exp in experiments:
        # Delete classic MLflow runs
        runs = client.search_runs(experiment_ids=[exp.experiment_id])
        for run in runs:
            client.delete_run(run.info.run_id)
            runs_deleted += 1

        # Delete traces (MLflow 3.x tracing; each node/request creates a trace)
        try:
            n = _delete_traces_for_experiment(client, exp.experiment_id)
            traces_deleted += n
        except Exception as e:
            print(
                f"  Could not delete traces for experiment {exp.experiment_id}: {e}",
                file=sys.stderr,
            )

    print(
        f"Deleted {runs_deleted} MLflow run(s) and {traces_deleted} trace(s) from {tracking_uri}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
