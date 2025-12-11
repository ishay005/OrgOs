"""
Admin endpoints for database management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import delete, text
from app.database import get_db
from app.models import (
    User, Task, AttributeAnswer, AlignmentEdge, QuestionLog,
    SimilarityScore, ChatThread, ChatMessage, TaskDependency,
    AttributeDefinition, EntityType, DailySyncSession, PromptTemplate
)
import logging

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.api_route("/clear-all-data", methods=["GET", "POST"])
async def clear_all_data(db: Session = Depends(get_db)):
    """
    ⚠️ WARNING: Deletes ALL user data (preserves schema and attribute definitions)
    Works with both GET (browser) and POST (API)
    """
    try:
        logger.info("🗑️  Clearing all user data from database...")
        
        # Delete in order to respect foreign key constraints
        deleted_counts = {}
        
        deleted_counts["similarity_scores"] = db.query(SimilarityScore).delete()
        deleted_counts["daily_sync_sessions"] = db.query(DailySyncSession).delete()
        deleted_counts["attribute_answers"] = db.query(AttributeAnswer).delete()
        deleted_counts["question_logs"] = db.query(QuestionLog).delete()
        deleted_counts["chat_messages"] = db.query(ChatMessage).delete()
        deleted_counts["chat_threads"] = db.query(ChatThread).delete()
        deleted_counts["task_dependencies"] = db.query(TaskDependency).delete()
        deleted_counts["tasks"] = db.query(Task).delete()
        deleted_counts["alignment_edges"] = db.query(AlignmentEdge).delete()
        deleted_counts["users"] = db.query(User).delete()
        
        db.commit()
        
        logger.info("✅ All user data cleared successfully!")
        
        return {
            "success": True,
            "message": "All user data cleared successfully",
            "deleted": deleted_counts,
            "preserved": "Attribute definitions, Prompt templates"
        }
        
    except Exception as e:
        logger.error(f"❌ Error clearing data: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")


@router.api_route("/update-schema", methods=["GET", "POST"])
async def update_schema(db: Session = Depends(get_db)):
    """
    Update database schema:
    - Add team column to users
    """
    results = {"actions": []}
    
    try:
        # Add team column to users table if not exists
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS team VARCHAR"))
            results["actions"].append("Added 'team' column to users table")
        except Exception as e:
            results["actions"].append(f"Team column: {str(e)}")
        
        db.commit()
        
        return {
            "message": "Schema updated successfully",
            "results": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Schema update failed: {str(e)}")
