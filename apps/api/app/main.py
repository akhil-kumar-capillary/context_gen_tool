from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.websocket import websocket_endpoint
from app.routers import auth, contexts, databricks, confluence, config_apis, llm, admin, chat

app = FastAPI(
    title="aiRA Context Management API",
    description="Backend API for aiRA Context Management Tool",
    version="1.0.0",
)

# CORS
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

# WebSocket — general purpose
app.add_api_websocket_route("/ws", websocket_endpoint)

# WebSocket — chat (handled by chat router itself at /api/chat/ws/chat)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aira-context-gen"}
