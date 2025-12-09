"""
Admin endpoints for database management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import delete
from app.database import get_db
from app.models import (
    User, Task, AttributeAnswer, AlignmentEdge, QuestionLog,
    SimilarityScore, ChatThread, ChatMessage, TaskDependency,
    AttributeDefinition, EntityType
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
    return {"message": "This endpoint is not available. Please use the command line instead."}
    
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


@router.api_route("/update-schema", methods=["GET", "POST"])
async def update_schema(db: Session = Depends(get_db)):
    """
    Update database schema: Remove old attributes and add new ones
    
    Removes: value_type, is_blocked, blocking_reason, direction_confidence, perceived_dependencies
    Adds: resources (if not exists)
    """
    try:
        logger.info("🔧 Updating database schema...")
        
        # Attributes to remove
        attrs_to_remove = [
            'value_type',
            'is_blocked',
            'blocking_reason',
            'direction_confidence',
            'perceived_dependencies'
        ]
        
        removed = {}
        
        for attr_name in attrs_to_remove:
            # Find the attribute
            attr_def = db.query(AttributeDefinition).filter(
                AttributeDefinition.name == attr_name
            ).first()
            
            if attr_def:
                logger.info(f"  Removing {attr_name}...")
                
                # Delete all similarity scores for answers of this attribute
                answer_ids_result = db.query(AttributeAnswer.id).filter(
                    AttributeAnswer.attribute_id == attr_def.id
                ).all()
                answer_ids = [row[0] for row in answer_ids_result]
                
                if answer_ids:
                    db.execute(
                        delete(SimilarityScore).where(
                            (SimilarityScore.answer_a_id.in_(answer_ids)) |
                            (SimilarityScore.answer_b_id.in_(answer_ids))
                        )
                    )
                
                # Delete all answers for this attribute
                answers_deleted = db.query(AttributeAnswer).filter(
                    AttributeAnswer.attribute_id == attr_def.id
                ).delete()
                
                # Delete all question logs for this attribute
                logs_deleted = db.query(QuestionLog).filter(
                    QuestionLog.attribute_id == attr_def.id
                ).delete()
                
                # Delete the attribute definition
                db.delete(attr_def)
                
                removed[attr_name] = {
                    "answers": answers_deleted,
                    "logs": logs_deleted
                }
            else:
                removed[attr_name] = "not_found"
        
        # Add new attribute: Resources
        logger.info("  Adding 'resources' attribute...")
        existing = db.query(AttributeDefinition).filter(
            AttributeDefinition.name == "resources",
            AttributeDefinition.entity_type == EntityType.TASK
        ).first()
        
        added = {}
        if not existing:
            from app.models import AttributeType
            resources_attr = AttributeDefinition(
                entity_type=EntityType.TASK,
                name="resources",
                label="Resources",
                type=AttributeType.STRING,
                description="Links, documents, or resources related to this task",
                allowed_values=None,
                is_required=False
            )
            db.add(resources_attr)
            added["resources"] = "created"
        else:
            added["resources"] = "already_exists"
        
        db.commit()
        logger.info("✅ Schema update complete!")
        
        # Get current task attributes
        current_attrs = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.TASK
        ).order_by(AttributeDefinition.name).all()
        
        return {
            "success": True,
            "message": "Schema updated successfully",
            "removed": removed,
            "added": added,
            "current_task_attributes": [
                {
                    "name": attr.name,
                    "label": attr.label,
                    "type": attr.type.value
                }
                for attr in current_attrs
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Error updating schema: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating schema: {str(e)}")

