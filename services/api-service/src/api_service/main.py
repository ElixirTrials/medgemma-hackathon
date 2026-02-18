import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Set

from dotenv import load_dotenv

load_dotenv(override=True)

from events_py.outbox import OutboxProcessor  # noqa: E402
from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from protocol_processor.trigger import handle_protocol_uploaded  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import Session  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from api_service.auth import router as auth_router  # noqa: E402
from api_service.batch_compare import router as batch_compare_router  # noqa: E402
from api_service.criterion_rerun import router as criterion_rerun_router  # noqa: E402
from api_service.dependencies import get_current_user, get_db  # noqa: E402
from api_service.entities import router as entities_router  # noqa: E402
from api_service.integrity import router as integrity_router  # noqa: E402
from api_service.middleware import MLflowRequestMiddleware  # noqa: E402
from api_service.protocols import router as protocols_router  # noqa: E402
from api_service.reviews import router as reviews_router  # noqa: E402
from api_service.search import router as search_router  # noqa: E402
from api_service.storage import create_db_and_tables, engine  # noqa: E402
from api_service.terminology_search import (  # noqa: E402
    router as terminology_search_router,
)

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track running background tasks
_running_tasks: Set[asyncio.Task] = set()  # noqa: UP006


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application."""
    # Startup
    logger.info("Starting up API service...")
    logger.info("Initializing database...")
    create_db_and_tables()
    logger.info("Database initialized successfully")

    # Initialize MLflow
    try:
        import mlflow

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment("protocol-processing")
            # Enable LangChain autolog for extraction/grounding agent traces
            try:
                mlflow.langchain.autolog()
                logger.info("MLflow LangChain autolog enabled")
            except Exception:
                logger.debug("MLflow LangChain autolog failed", exc_info=True)
            logger.info(
                "MLflow initialized: tracking_uri=%s, experiment=protocol-processing",
                tracking_uri,
            )
        else:
            logger.info("MLFLOW_TRACKING_URI not set, skipping MLflow initialization")
    except ImportError:
        logger.info("mlflow not installed, skipping initialization")
    except Exception:
        logger.warning(
            "MLflow initialization failed, continuing without tracing",
            exc_info=True,
        )

    # Start outbox processor as background task
    # Per PIPE-03: criteria_extracted outbox removed. protocol_uploaded retained.
    # protocol_processor.trigger.handle_protocol_uploaded replaces both the
    # old extraction_service.trigger and grounding_service.trigger handlers.
    processor = OutboxProcessor(
        engine=engine,
        handlers={
            "protocol_uploaded": [handle_protocol_uploaded],
        },
    )
    task = asyncio.create_task(processor.start())
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)

    yield

    # Shutdown - stop outbox processor first
    await processor.stop()

    # Wait for background tasks to complete
    if _running_tasks:
        logger.info(f"Waiting for {len(_running_tasks)} tasks to complete...")
        await asyncio.gather(*_running_tasks, return_exceptions=True)
    logger.info("Shutdown complete")


app = FastAPI(lifespan=lifespan)

# Add SessionMiddleware for OAuth state (must be before CORS)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-session-secret"),
)

# Configure CORS
# In production, restrict origins to specific domains
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003,http://localhost:5173,http://localhost:5174",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add MLflow request tracing middleware
app.add_middleware(MLflowRequestMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return JSON so CORS headers are preserved."""
    logger.error(
        "Unhandled exception on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Mount auth router (public endpoints - no auth required)
app.include_router(auth_router)

# Mount protected routers (all endpoints require auth)
app.include_router(protocols_router, dependencies=[Depends(get_current_user)])
app.include_router(reviews_router, dependencies=[Depends(get_current_user)])
app.include_router(entities_router, dependencies=[Depends(get_current_user)])
app.include_router(search_router, dependencies=[Depends(get_current_user)])
app.include_router(terminology_search_router, dependencies=[Depends(get_current_user)])
app.include_router(integrity_router, dependencies=[Depends(get_current_user)])
app.include_router(criterion_rerun_router, dependencies=[Depends(get_current_user)])
app.include_router(batch_compare_router, dependencies=[Depends(get_current_user)])


@app.get("/health")
async def health_check():
    """Liveness probe - is the service running?"""
    return {"status": "healthy"}


@app.get("/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe - can the service handle requests?"""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "error": "Database unavailable",
            },
        )


@app.get("/")
async def root():
    """Returns a welcome message for the API."""
    return {"message": "Welcome to the API Service"}


# --- Local file storage endpoints (dev only) ---


@app.put("/local-upload/{blob_path:path}")
async def local_upload(blob_path: str, request: Request):
    """Receive a file upload and store it locally (dev mode)."""
    from api_service.gcs import local_save_file

    body = await request.body()
    local_save_file(blob_path, body)
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.get("/local-files/{blob_path:path}")
async def local_files(blob_path: str):
    """Serve a locally stored file (dev mode)."""
    from api_service.gcs import local_get_file_path

    file_path = local_get_file_path(blob_path)
    if file_path is None:
        return JSONResponse(status_code=404, content={"detail": "File not found"})
    return FileResponse(str(file_path), media_type="application/pdf")
