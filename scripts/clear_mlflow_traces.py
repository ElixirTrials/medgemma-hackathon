"""Delete all runs and traces from the MLflow tracking server.

Uses MLFLOW_TRACKING_URI from the environment (e.g. http://localhost:5001).
Requires mlflow (run with: uv run --group dev python scripts/clear_mlflow_traces.py).
"""

from __future__ import annotations

import os
import sys


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

    deleted = 0
    for exp in experiments:
        runs = client.search_runs(experiment_ids=[exp.experiment_id])
        for run in runs:
            client.delete_run(run.info.run_id)
            deleted += 1
    print(f"Deleted {deleted} MLflow run(s) from {tracking_uri}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
