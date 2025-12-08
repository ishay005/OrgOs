"""
Main FastAPI application for OrgOs - Perception Alignment System
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os

from app.database import init_db, SessionLocal
from app.seed import seed_database
from app.routers import (
    users, tasks, questions, misalignments, debug, users_orgchart, alignment_stats
)

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
app.include_router(users.alignment_router)
app.include_router(users_orgchart.router)
app.include_router(tasks.router)
app.include_router(tasks.attributes_router)
app.include_router(questions.router)
app.include_router(questions.answers_router)
app.include_router(misalignments.router)
app.include_router(debug.router)
app.include_router(alignment_stats.router)


# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """
    Serve the web UI or API info
    """
    static_index = os.path.join(static_dir, "index.html")
    if os.path.exists(static_index):
        return FileResponse(static_index)
    
    return {
        "status": "ok",
        "service": "OrgOs - Perception Alignment System",
        "version": "1.0.0",
        "documentation": "/docs",
        "web_ui": "/"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy"}

