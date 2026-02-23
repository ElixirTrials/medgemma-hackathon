#!/bin/bash

# Kill FastAPI/Uvicorn
pkill -f "uvicorn api_service.main:app" || true

# Kill MLflow server and its child workers (huey consumers, job runner)
pkill -f "mlflow server" || true
pkill -f "mlflow.server.jobs" || true
pkill -f "huey_consumer.py mlflow" || true
# Job runner ignores SIGTERM — force kill any survivors
sleep 0.5
pkill -9 -f "mlflow.server.jobs" 2>/dev/null || true
pkill -9 -f "huey_consumer.py mlflow" 2>/dev/null || true

# Kill Python http server (docs)
pkill -f "python -m http.server 8000" || true

# Kill any node processes (vite)
pkill -f "vite" || true

echo "Killed common development processes."
