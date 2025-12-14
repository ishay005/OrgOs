from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Fix DATABASE_URL format for Railway (convert postgresql:// to postgresql+psycopg://)
database_url = settings.database_url
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# ============================================================================
# OPTIMIZED CONNECTION POOLING FOR RAILWAY/CLOUD DEPLOYMENTS
# ============================================================================
# These settings dramatically improve performance on cloud platforms with
# limited connections and network latency (Railway, Render, etc.)
# ============================================================================

engine = create_engine(
    database_url,
    
    # Connection Pool Settings
    pool_size=5,              # Keep 5 connections open (Railway free tier limit-friendly)
    max_overflow=10,          # Allow up to 10 extra connections during spikes
    pool_timeout=30,          # Wait max 30 seconds for a connection
    pool_recycle=1800,        # Recycle connections every 30 minutes (prevents stale connections)
    pool_pre_ping=True,       # Check if connection is alive before using (critical for Railway!)
    
    # Performance Settings
    echo=False,               # Don't log every SQL query (set to True for debugging)
    future=True,              # Use SQLAlchemy 2.0 style
    
    # Connection Arguments (psycopg-specific)
    connect_args={
        "connect_timeout": 10,           # 10 second connection timeout
        "keepalives": 1,                 # Enable TCP keepalives
        "keepalives_idle": 30,           # Start keepalives after 30s idle
        "keepalives_interval": 10,       # Send keepalive every 10s
        "keepalives_count": 5,           # Drop connection after 5 failed keepalives
    }
)

logger.info(
    f"Database engine initialized with connection pooling: "
    f"pool_size=5, max_overflow=10, pool_pre_ping=True"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    from app.models import User, Task, AttributeDefinition, AttributeAnswer, QuestionLog, TaskRelevantUser
    Base.metadata.create_all(bind=engine)

