import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.websocket import websocket_endpoint
from app.core.task_registry import task_registry
from app.routers import auth, contexts, databricks, confluence, config_apis, llm, admin, chat

logger = logging.getLogger(__name__)

app = FastAPI(
    title="aiRA Context Management API",
    description="Backend API for aiRA Context Management Tool",
    version="1.0.0",
)

# Startup info
_db_host = settings.database_url.split("@")[1].split("/")[0] if "@" in settings.database_url else "default"
logger.info(f"Environment: {settings.env}")
logger.info(f"Database host: {_db_host}")
logger.info(f"CORS allowed origins: {settings.cors_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(contexts.router, prefix="/api/contexts", tags=["contexts"])
app.include_router(databricks.router, prefix="/api/sources/databricks", tags=["databricks"])
app.include_router(confluence.router, prefix="/api/sources/confluence", tags=["confluence"])
app.include_router(config_apis.router, prefix="/api/sources/config-apis", tags=["config-apis"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

# WebSocket — general purpose (used by Databricks pipeline progress etc.)
app.add_api_websocket_route("/api/ws", websocket_endpoint)

# WebSocket — chat (handled by chat router itself at /api/chat/ws/chat)


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel all running background tasks on server shutdown."""
    await task_registry.cancel_all(timeout=10.0)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aira-context-gen"}
