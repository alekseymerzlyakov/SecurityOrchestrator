"""AISO — AI-Driven Security Orchestrator. FastAPI application entry point."""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.config import CORS_ORIGINS, DEFAULT_TOOLS
from backend.database import init_db, async_session
from backend.models.settings import ToolConfig
from backend.websocket.manager import ws_manager

from backend.routers import projects, scans, findings, settings, prompts, reports, jira


async def seed_default_tools():
    """Insert default tool configurations if not present."""
    async with async_session() as session:
        result = await session.execute(select(ToolConfig))
        if result.scalars().first() is None:
            for tool in DEFAULT_TOOLS:
                session.add(ToolConfig(**tool))
            await session.commit()


async def seed_default_prompts():
    """Upsert built-in prompts on every startup (insert if name not found).

    This lets us add new built-in prompts without wiping user data.
    Existing prompts with matching names are NOT overwritten.
    """
    from backend.models.prompt import Prompt
    from backend.config import PROMPTS_DIR

    prompts_to_seed = [
        {
            "name": "AI-Only: Полный аудит без SAST",
            "category": "ai_only",
            "filename": "ai_only_deep_scan.txt",
        },
        {
            "name": "Hybrid: Углублённый анализ находок SAST",
            "category": "hybrid",
            "filename": "hybrid_focused.txt",
        },
        {
            "name": "Report: AI Executive Summary",
            "category": "general",
            "filename": "report_summary.txt",
        },
    ]

    async with async_session() as session:
        for p in prompts_to_seed:
            # Skip if already exists (don't overwrite user edits)
            existing = await session.execute(
                select(Prompt).where(Prompt.name == p["name"])
            )
            if existing.scalars().first() is not None:
                continue

            prompt_file = PROMPTS_DIR / p["filename"]
            if not prompt_file.exists():
                continue
            content = prompt_file.read_text(encoding="utf-8")
            if content.strip():
                session.add(Prompt(
                    name=p["name"],
                    category=p["category"],
                    content=content,
                    is_default=False,
                    version=1,
                ))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    await seed_default_tools()
    await seed_default_prompts()
    yield


app = FastAPI(
    title="AISO — AI-Driven Security Orchestrator",
    description="Security audit orchestration platform for Git repositories",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(scans.router, prefix="/api/scans", tags=["Scans"])
app.include_router(findings.router, prefix="/api/findings", tags=["Findings"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["Prompts"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(jira.router, prefix="/api/jira", tags=["Jira"])


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time scan progress."""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send commands (e.g., stop scan)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "AISO"}
