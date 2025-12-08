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
            # Check if similarity_scores table exists
            from sqlalchemy import inspect
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if 'similarity_scores' not in tables:
                logger.info("📝 Running similarity_scores migration...")
                from sqlalchemy import text
                with open('/app/migrations/add_similarity_scores_table.sql', 'r') as f:
                    sql = f.read()
                    # Split by statement and execute
                    for statement in sql.split(';'):
                        statement = statement.strip()
                        if statement and not statement.startswith('--'):
                            db.execute(text(statement))
                    db.commit()
                logger.info("✅ Similarity scores migration complete")
            
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

