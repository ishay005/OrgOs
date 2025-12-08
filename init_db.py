#!/usr/bin/env python3
"""
Initialize database tables and run migrations
"""
import sys
sys.path.insert(0, '/app')

from app.database import engine, SessionLocal, init_db
from app.models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Initialize database"""
    try:
        logger.info("🔧 Initializing database...")
        
        # Create all tables
        logger.info("📊 Creating tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created successfully")
        
        # Run SQL migrations if needed
        db = SessionLocal()
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            # Migration 1: Similarity scores table
            if 'similarity_scores' not in tables:
                logger.info("📝 Running similarity_scores migration...")
                with open('/app/migrations/add_similarity_scores_table.sql', 'r') as f:
                    sql = f.read()
                    for statement in sql.split(';'):
                        statement = statement.strip()
                        if statement and not statement.startswith('--'):
                            db.execute(text(statement))
                    db.commit()
                logger.info("✅ Similarity scores migration complete")
            
            # Migration 2: Performance indexes (always run - idempotent)
            logger.info("📝 Ensuring performance indexes are in place...")
            with open('/app/migrations/add_performance_indexes.sql', 'r') as f:
                sql = f.read()
                for statement in sql.split(';'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        try:
                            db.execute(text(statement))
                        except Exception as e:
                            # Index might already exist, that's OK
                            if 'already exists' not in str(e):
                                logger.warning(f"Index creation warning: {e}")
                db.commit()
            logger.info("✅ Performance indexes migration complete")
            
        finally:
            db.close()
        
        logger.info("✅ Database initialization complete")
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

