"""
Admin endpoints for database management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import delete, text
from app.database import get_db
from app.models import (
    User, Task, AttributeAnswer, QuestionLog,
    SimilarityScore, ChatThread, ChatMessage, TaskDependency,
    AttributeDefinition, EntityType, DailySyncSession, PromptTemplate,
    TaskRelevantUser, QuestionsSession
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
        
        # Try to delete questions_sessions (may not exist yet)
        try:
            deleted_counts["questions_sessions"] = db.query(QuestionsSession).delete()
        except:
            deleted_counts["questions_sessions"] = 0
        
        deleted_counts["attribute_answers"] = db.query(AttributeAnswer).delete()
        deleted_counts["question_logs"] = db.query(QuestionLog).delete()
        deleted_counts["chat_messages"] = db.query(ChatMessage).delete()
        deleted_counts["chat_threads"] = db.query(ChatThread).delete()
        deleted_counts["task_dependencies"] = db.query(TaskDependency).delete()
        deleted_counts["task_relevant_users"] = db.query(TaskRelevantUser).delete()
        deleted_counts["tasks"] = db.query(Task).delete()
        deleted_counts["users"] = db.query(User).delete()
        
        # Also try to delete alignment_edges table if it exists (legacy)
        try:
            db.execute(text("DELETE FROM alignment_edges"))
            deleted_counts["alignment_edges_legacy"] = "cleared"
        except:
            pass
        
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
    - Add team and role columns to users
    - Add conversation_id to daily_sync_sessions
    - Create questions_sessions table
    - Drop alignment_edges table (deprecated)
    """
    results = {"actions": []}
    
    try:
        # Add team column to users table if not exists
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS team VARCHAR"))
            results["actions"].append("Added 'team' column to users table")
        except Exception as e:
            results["actions"].append(f"Team column: {str(e)}")
        
        # Add role column to users table if not exists
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR"))
            results["actions"].append("Added 'role' column to users table")
        except Exception as e:
            results["actions"].append(f"Role column: {str(e)}")
        
        # Add last_response_id to daily_sync_sessions (for OpenAI conversation threading)
        try:
            db.execute(text("ALTER TABLE daily_sync_sessions ADD COLUMN IF NOT EXISTS last_response_id VARCHAR"))
            results["actions"].append("Added 'last_response_id' column to daily_sync_sessions")
        except Exception as e:
            results["actions"].append(f"Last response ID column (daily): {str(e)}")
        
        # Create questions_sessions table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS questions_sessions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    thread_id UUID NOT NULL REFERENCES chat_threads(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    last_response_id VARCHAR
                )
            """))
            results["actions"].append("Created 'questions_sessions' table")
        except Exception as e:
            results["actions"].append(f"Questions sessions table: {str(e)}")
        
        # Add last_response_id to questions_sessions if it exists but doesn't have the column
        try:
            db.execute(text("ALTER TABLE questions_sessions ADD COLUMN IF NOT EXISTS last_response_id VARCHAR"))
            results["actions"].append("Added 'last_response_id' column to questions_sessions")
        except Exception as e:
            results["actions"].append(f"Last response ID column (questions): {str(e)}")
        
        # Create index for questions sessions
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_questions_session_active 
                ON questions_sessions(user_id, is_active)
            """))
            results["actions"].append("Created index on questions_sessions")
        except Exception as e:
            results["actions"].append(f"Questions sessions index: {str(e)}")
        
        # Drop deprecated alignment_edges table
        try:
            db.execute(text("DROP TABLE IF EXISTS alignment_edges CASCADE"))
            results["actions"].append("Dropped deprecated 'alignment_edges' table")
        except Exception as e:
            results["actions"].append(f"Drop alignment_edges: {str(e)}")
        
        db.commit()
        
        return {
            "message": "Schema updated successfully",
            "results": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Schema update failed: {str(e)}")


@router.api_route("/recalculate-relevant-users", methods=["GET", "POST"])
async def recalculate_relevant_users(db: Session = Depends(get_db)):
    """
    Recalculate ALL relevant users for all tasks.
    
    Relevant users rules:
    1. Manager of task owner
    2. Employees of task owner
    3. Owners of dependent tasks
    
    Also recalculates similarity scores.
    """
    results = {"actions": []}
    
    try:
        # Step 1: Clear existing relevant users and recalculate
        try:
            from populate_relevant_users import populate_all_tasks
            count = populate_all_tasks(db, clear_existing=True)
            results["actions"].append(f"Created {count} relevant user associations")
        except Exception as e:
            results["actions"].append(f"Relevant users error: {str(e)}")
        
        # Step 2: Recalculate similarity scores
        try:
            from app.services.similarity_cache import recalculate_all_similarity_scores
            scores_count = recalculate_all_similarity_scores(db)
            results["actions"].append(f"Calculated {scores_count} similarity scores")
        except Exception as e:
            results["actions"].append(f"Similarity scores error: {str(e)}")
        
        return {
            "success": True,
            "message": "Relevant users and similarity scores recalculated!",
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
