"""
Admin endpoints for database management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    User, Task, AttributeAnswer, AlignmentEdge, QuestionLog,
    SimilarityScore, ChatThread, ChatMessage, TaskDependency
)
import logging

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/clear-all-data")
async def clear_all_data(db: Session = Depends(get_db)):
    """
    ⚠️ WARNING: Deletes ALL user data (preserves schema and attribute definitions)
    """
    try:
        logger.info("🗑️  Clearing all user data from database...")
        
        # Delete in order to respect foreign key constraints
        deleted_counts = {}
        
        deleted_counts["similarity_scores"] = db.query(SimilarityScore).delete()
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
            "preserved": "Attribute definitions (Priority, Status, Resources, etc.)"
        }
        
    except Exception as e:
        logger.error(f"❌ Error clearing data: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")

