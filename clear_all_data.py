#!/usr/bin/env python3
"""
Clear all user data from database (preserves schema and attribute definitions)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models import (
    User, Task, AttributeAnswer, AlignmentEdge, QuestionLog,
    SimilarityScore, ChatThread, ChatMessage, TaskDependency
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_all_data():
    """Delete all user data but preserve attribute definitions"""
    db = SessionLocal()
    
    try:
        logger.info("🗑️  Clearing all user data from database...")
        
        # Delete in order to respect foreign key constraints
        
        logger.info("  Deleting similarity scores...")
        deleted = db.query(SimilarityScore).delete()
        logger.info(f"    ✅ Deleted {deleted} similarity scores")
        
        logger.info("  Deleting attribute answers...")
        deleted = db.query(AttributeAnswer).delete()
        logger.info(f"    ✅ Deleted {deleted} attribute answers")
        
        logger.info("  Deleting question logs...")
        deleted = db.query(QuestionLog).delete()
        logger.info(f"    ✅ Deleted {deleted} question logs")
        
        logger.info("  Deleting chat messages...")
        deleted = db.query(ChatMessage).delete()
        logger.info(f"    ✅ Deleted {deleted} chat messages")
        
        logger.info("  Deleting chat threads...")
        deleted = db.query(ChatThread).delete()
        logger.info(f"    ✅ Deleted {deleted} chat threads")
        
        logger.info("  Deleting task dependencies...")
        deleted = db.query(TaskDependency).delete()
        logger.info(f"    ✅ Deleted {deleted} task dependencies")
        
        logger.info("  Deleting tasks...")
        deleted = db.query(Task).delete()
        logger.info(f"    ✅ Deleted {deleted} tasks")
        
        logger.info("  Deleting alignment edges...")
        deleted = db.query(AlignmentEdge).delete()
        logger.info(f"    ✅ Deleted {deleted} alignment edges")
        
        logger.info("  Deleting users...")
        deleted = db.query(User).delete()
        logger.info(f"    ✅ Deleted {deleted} users")
        
        db.commit()
        logger.info("\n✅ All user data cleared successfully!")
        logger.info("📋 Attribute definitions preserved (Priority, Status, etc.)")
        
    except Exception as e:
        logger.error(f"\n❌ Error clearing data: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    
    # Safety confirmation
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        clear_all_data()
    else:
        print("⚠️  WARNING: This will delete ALL user data from the database!")
        print("   (Attribute definitions like Priority, Status will be preserved)")
        print("")
        print("To proceed, run:")
        print("  python3 clear_all_data.py --confirm")
