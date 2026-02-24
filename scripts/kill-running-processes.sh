#!/bin/bash

# Kill by process name first (so we get workers and reload children)
pkill -f "uvicorn api_service.main:app" || true
pkill -f "mlflow server" || true
pkill -f "mlflow.server.jobs" || true
pkill -f "huey_consumer.py mlflow" || true
pkill -f "python -m http.server 8000" || true
pkill -f "vite" || true

sleep 0.5
pkill -9 -f "mlflow.server.jobs" 2>/dev/null || true
pkill -9 -f "huey_consumer.py mlflow" 2>/dev/null || true
pkill -9 -f "mlflow server" 2>/dev/null || true
pkill -9 -f "uvicorn api_service.main:app" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true

# Kill anything still bound to dev ports (orphans, different invocations)
for port in 5001 5002 8000 8001 3000 5173; do
	pid=$(lsof -ti :"$port" 2>/dev/null)
	if [ -n "$pid" ]; then
		kill -9 $pid 2>/dev/null || true
	fi
done

echo "Killed common development processes."
