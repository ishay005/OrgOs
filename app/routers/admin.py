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


@router.api_route("/recalculate-alignments", methods=["GET", "POST"])
async def recalculate_alignments(db: Session = Depends(get_db)):
    """
    Recalculate ALL alignment edges and similarity scores.
    
    Alignment rules:
    1. Manager ↔ Employee (bidirectional)
    2. Teammates (same manager)
    3. Task dependency owners (if task A depends on task B, owner of A aligns with owner of B)
    """
    from app.models import Task, TaskDependency
    
    results = {"actions": []}
    
    try:
        # Step 1: Clear existing alignment edges
        deleted = db.query(AlignmentEdge).delete()
        results["actions"].append(f"Deleted {deleted} old alignment edges")
        
        # Get all users
        all_users = db.query(User).all()
        
        # Track created edges to avoid duplicates
        created_edges = set()
        edges_created = 0
        
        def add_edge(source_id, target_id):
            nonlocal edges_created
            key = (str(source_id), str(target_id))
            if key not in created_edges and source_id != target_id:
                db.add(AlignmentEdge(source_user_id=source_id, target_user_id=target_id))
                created_edges.add(key)
                edges_created += 1
        
        # 1. Manager-Employee relationships (bidirectional)
        for user in all_users:
            if user.manager_id:
                add_edge(user.id, user.manager_id)
                add_edge(user.manager_id, user.id)
        
        # 2. Employees (direct reports)
        for user in all_users:
            employees = [u for u in all_users if u.manager_id == user.id]
            for emp in employees:
                add_edge(user.id, emp.id)
                add_edge(emp.id, user.id)
        
        # 3. Teammates (same manager)
        for user in all_users:
            if user.manager_id:
                teammates = [u for u in all_users if u.manager_id == user.manager_id and u.id != user.id]
                for teammate in teammates:
                    add_edge(user.id, teammate.id)
        
        # 4. Task dependency connections
        all_dependencies = db.query(TaskDependency).all()
        for dep in all_dependencies:
            task = db.query(Task).filter(Task.id == dep.task_id).first()
            depends_on = db.query(Task).filter(Task.id == dep.depends_on_task_id).first()
            
            if task and depends_on and task.owner_user_id and depends_on.owner_user_id:
                if task.owner_user_id != depends_on.owner_user_id:
                    add_edge(task.owner_user_id, depends_on.owner_user_id)
                    add_edge(depends_on.owner_user_id, task.owner_user_id)
        
        db.commit()
        results["actions"].append(f"Created {edges_created} alignment edges")
        
        # Step 2: Recalculate similarity scores
        from app.services.similarity_cache import recalculate_all_similarity_scores
        scores_count = recalculate_all_similarity_scores(db)
        results["actions"].append(f"Calculated {scores_count} similarity scores")
        
        return {
            "success": True,
            "message": "Alignments and similarity scores recalculated!",
            "results": results
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {str(e)}")


@router.api_route("/fix-daily-sync-enum", methods=["GET", "POST"])
async def fix_daily_sync_enum(db: Session = Depends(get_db)):
    """
    Fix the DailySyncPhase enum in PostgreSQL.
    This drops and recreates the daily_sync_sessions table with the correct enum values.
    
    New enum values: opening_brief, questions, summary, done
    """
    results = {"actions": []}
    
    try:
        # Step 1: Drop the existing daily_sync_sessions table
        try:
            db.execute(text("DROP TABLE IF EXISTS daily_sync_sessions CASCADE"))
            results["actions"].append("Dropped daily_sync_sessions table")
        except Exception as e:
            results["actions"].append(f"Drop table error: {str(e)}")
        
        # Step 2: Drop the old enum type
        try:
            db.execute(text("DROP TYPE IF EXISTS dailysyncphase CASCADE"))
            results["actions"].append("Dropped old dailysyncphase enum")
        except Exception as e:
            results["actions"].append(f"Drop enum error: {str(e)}")
        
        # Step 3: Create the new enum type
        try:
            db.execute(text("""
                CREATE TYPE dailysyncphase AS ENUM ('opening_brief', 'questions', 'summary', 'done')
            """))
            results["actions"].append("Created new dailysyncphase enum")
        except Exception as e:
            results["actions"].append(f"Create enum error: {str(e)}")
        
        # Step 4: Recreate the daily_sync_sessions table
        try:
            db.execute(text("""
                CREATE TABLE daily_sync_sessions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    thread_id UUID NOT NULL REFERENCES chat_threads(id),
                    phase dailysyncphase NOT NULL DEFAULT 'opening_brief',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    insight_questions JSON NOT NULL DEFAULT '[]',
                    asked_question_ids JSON NOT NULL DEFAULT '[]',
                    answered_question_ids JSON NOT NULL DEFAULT '[]'
                )
            """))
            results["actions"].append("Recreated daily_sync_sessions table")
        except Exception as e:
            results["actions"].append(f"Create table error: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "message": "DailySyncPhase enum fixed successfully!",
            "results": results,
            "note": "All existing Daily Sync sessions were cleared. Users can start new sessions now."
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Enum fix failed: {str(e)}")
