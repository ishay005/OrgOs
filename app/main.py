"""
Main FastAPI application for OrgOs - Perception Alignment System
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from contextlib import asynccontextmanager
import logging
import os

from app.database import init_db, SessionLocal
from app.seed import seed_database
from app.routers import (
    users, tasks, questions, misalignments, debug, users_orgchart, alignment_stats, chat, pending_questions, admin, prompts, prompt_preview, daily_sync, import_export
)


class NoCacheStaticFiles(StarletteStaticFiles):
    """Static files handler that adds no-cache headers"""
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events for the application.
    """
    # Startup: Initialize database and seed data
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Seeding initial ontology...")
    db = SessionLocal()
    try:
        seed_database(db)
        logger.info("Database initialization complete")
    finally:
        db.close()
    
    yield
    
    # Shutdown
    logger.info("Application shutting down")


# Create FastAPI app
app = FastAPI(
    title="OrgOs - Perception Alignment System",
    description="Backend API for collecting and analyzing perception alignment across teams",
    version="1.0.0",
    lifespan=lifespan
)


# Include routers
app.include_router(users.router)
app.include_router(users_orgchart.router)
app.include_router(tasks.router)
app.include_router(tasks.attributes_router)
app.include_router(questions.router)
app.include_router(questions.answers_router)
app.include_router(misalignments.router)
app.include_router(debug.router)
app.include_router(alignment_stats.router)
app.include_router(chat.router)  # Robin chat assistant
app.include_router(daily_sync.router)  # Robin Daily Sync mode
app.include_router(pending_questions.router)  # Pending questions for data collection
app.include_router(admin.router)  # Admin endpoints
app.include_router(prompts.router)  # Prompt management
app.include_router(prompt_preview.router)  # Prompt preview with real data
app.include_router(import_export.router)  # Import/Export data


# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
logger.info(f"Static directory path: {static_dir}")
logger.info(f"Static directory exists: {os.path.exists(static_dir)}")

if os.path.exists(static_dir):
    app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")
    logger.info("✅ Static files mounted (no-cache)")
else:
    logger.warning("⚠️  Static directory not found")


@app.get("/")
async def root():
    """
    Serve the web UI or API info
    """
    static_index = os.path.join(static_dir, "index.html")
    if os.path.exists(static_index):
        logger.info("Serving index.html")
        return FileResponse(
            static_index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    
    logger.info("Serving API info (static files not found)")
    return {
        "status": "ok",
        "service": "OrgOs - Perception Alignment System",
        "version": "1.0.0",
        "documentation": "/docs",
        "web_ui": "/",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy"}

