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
    TaskRelevantUser, QuestionsSession,
    TaskAlias, TaskMergeProposal, TaskDependencyV2, AlternativeDependencyProposal, PendingDecision
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
        
        # Delete state machine tables
        try:
            deleted_counts["pending_decisions"] = db.query(PendingDecision).delete()
        except:
            deleted_counts["pending_decisions"] = 0
        
        try:
            deleted_counts["alternative_dependency_proposals"] = db.query(AlternativeDependencyProposal).delete()
        except:
            deleted_counts["alternative_dependency_proposals"] = 0
        
        try:
            deleted_counts["task_dependencies_v2"] = db.query(TaskDependencyV2).delete()
        except:
            deleted_counts["task_dependencies_v2"] = 0
        
        try:
            deleted_counts["task_merge_proposals"] = db.query(TaskMergeProposal).delete()
        except:
            deleted_counts["task_merge_proposals"] = 0
        
        try:
            deleted_counts["task_aliases"] = db.query(TaskAlias).delete()
        except:
            deleted_counts["task_aliases"] = 0
        
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


@router.api_route("/migrate-state-machines", methods=["GET", "POST"])
async def migrate_state_machines(db: Session = Depends(get_db)):
    """
    Migrate database schema for state machines:
    - Add Task.state, Task.created_by_user_id
    - Create TaskAlias, TaskMergeProposal, TaskDependencyV2
    - Create AlternativeDependencyProposal, PendingDecision
    - Migrate existing dependencies to V2
    """
    results = {"actions": []}
    
    try:
        # --- Task table extensions ---
        try:
            db.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id)"))
            results["actions"].append("Added 'created_by_user_id' to tasks")
        except Exception as e:
            results["actions"].append(f"created_by_user_id: {str(e)}")
        
        try:
            db.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state VARCHAR DEFAULT 'ACTIVE'"))
            results["actions"].append("Added 'state' column to tasks")
        except Exception as e:
            results["actions"].append(f"state: {str(e)}")
        
        try:
            db.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state_changed_at TIMESTAMP"))
            results["actions"].append("Added 'state_changed_at' to tasks")
        except Exception as e:
            results["actions"].append(f"state_changed_at: {str(e)}")
        
        try:
            db.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state_reason TEXT"))
            results["actions"].append("Added 'state_reason' to tasks")
        except Exception as e:
            results["actions"].append(f"state_reason: {str(e)}")
        
        # Set defaults for existing tasks
        try:
            db.execute(text("UPDATE tasks SET state = 'ACTIVE' WHERE state IS NULL"))
            db.execute(text("UPDATE tasks SET created_by_user_id = owner_user_id WHERE created_by_user_id IS NULL"))
            results["actions"].append("Set defaults for existing tasks")
        except Exception as e:
            results["actions"].append(f"defaults: {str(e)}")
        
        # --- TaskAlias table ---
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS task_aliases (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    canonical_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    alias_title VARCHAR NOT NULL,
                    alias_created_by_user_id UUID NOT NULL REFERENCES users(id),
                    merged_from_task_id UUID REFERENCES tasks(id),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_task_alias_canonical ON task_aliases(canonical_task_id)"))
            results["actions"].append("Created task_aliases table")
        except Exception as e:
            results["actions"].append(f"task_aliases: {str(e)}")
        
        # --- TaskMergeProposal table ---
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS task_merge_proposals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    from_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    to_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    proposed_by_user_id UUID NOT NULL REFERENCES users(id),
                    proposal_reason TEXT NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
                    rejected_by_user_id UUID REFERENCES users(id),
                    rejected_reason TEXT,
                    accepted_by_user_id UUID REFERENCES users(id),
                    accepted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_merge_proposal_from_task ON task_merge_proposals(from_task_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_merge_proposal_status ON task_merge_proposals(status)"))
            results["actions"].append("Created task_merge_proposals table")
        except Exception as e:
            results["actions"].append(f"task_merge_proposals: {str(e)}")
        
        # --- TaskDependencyV2 table ---
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS task_dependencies_v2 (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    downstream_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    upstream_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
                    created_by_user_id UUID NOT NULL REFERENCES users(id),
                    accepted_by_user_id UUID REFERENCES users(id),
                    accepted_at TIMESTAMP,
                    rejected_by_user_id UUID REFERENCES users(id),
                    rejected_at TIMESTAMP,
                    rejected_reason TEXT,
                    removed_by_user_id UUID REFERENCES users(id),
                    removed_at TIMESTAMP,
                    removed_reason TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dep_v2_downstream ON task_dependencies_v2(downstream_task_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dep_v2_upstream ON task_dependencies_v2(upstream_task_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dep_v2_status ON task_dependencies_v2(status)"))
            results["actions"].append("Created task_dependencies_v2 table")
        except Exception as e:
            results["actions"].append(f"task_dependencies_v2: {str(e)}")
        
        # --- AlternativeDependencyProposal table ---
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS alternative_dependency_proposals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    original_dependency_id UUID NOT NULL REFERENCES task_dependencies_v2(id) ON DELETE CASCADE,
                    downstream_task_id UUID NOT NULL REFERENCES tasks(id),
                    original_upstream_task_id UUID NOT NULL REFERENCES tasks(id),
                    suggested_upstream_task_id UUID NOT NULL REFERENCES tasks(id),
                    proposed_by_user_id UUID NOT NULL REFERENCES users(id),
                    proposal_reason TEXT NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
                    rejected_by_user_id UUID REFERENCES users(id),
                    rejected_reason TEXT,
                    accepted_by_user_id UUID REFERENCES users(id),
                    accepted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_alt_dep_status ON alternative_dependency_proposals(status)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_alt_dep_downstream ON alternative_dependency_proposals(downstream_task_id)"))
            results["actions"].append("Created alternative_dependency_proposals table")
        except Exception as e:
            results["actions"].append(f"alternative_dependency_proposals: {str(e)}")
        
        # --- PendingDecision table ---
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS pending_decisions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    decision_type VARCHAR NOT NULL,
                    entity_type VARCHAR NOT NULL,
                    entity_id UUID NOT NULL,
                    description TEXT NOT NULL,
                    is_resolved BOOLEAN DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    resolution VARCHAR,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_pending_decision_user ON pending_decisions(user_id, is_resolved)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_pending_decision_entity ON pending_decisions(entity_type, entity_id)"))
            results["actions"].append("Created pending_decisions table")
        except Exception as e:
            results["actions"].append(f"pending_decisions: {str(e)}")
        
        # --- Migrate existing dependencies to V2 ---
        try:
            db.execute(text("""
                INSERT INTO task_dependencies_v2 (id, downstream_task_id, upstream_task_id, status, created_by_user_id, accepted_at)
                SELECT 
                    gen_random_uuid(),
                    td.task_id,
                    td.depends_on_task_id,
                    'CONFIRMED',
                    t.owner_user_id,
                    NOW()
                FROM task_dependencies td
                JOIN tasks t ON t.id = td.task_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM task_dependencies_v2 v2 
                    WHERE v2.downstream_task_id = td.task_id 
                    AND v2.upstream_task_id = td.depends_on_task_id
                )
            """))
            results["actions"].append("Migrated existing dependencies to V2")
        except Exception as e:
            results["actions"].append(f"migrate dependencies: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "message": "State machines migration completed!",
            "results": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.api_route("/update-schema", methods=["GET", "POST"])
async def update_schema(db: Session = Depends(get_db)):
    """
    🔧 Update database schema - adds new columns to existing tables.
    Safe to run multiple times (idempotent).
    
    This adds:
    - state, created_by_user_id, state_changed_at, state_reason to tasks table
    - last_response_id to chat_threads table
    - Creates all new tables if they don't exist
    """
    results = {"columns_added": [], "columns_existed": [], "tables_created": [], "errors": []}
    
    try:
        logger.info("🔧 Running schema update...")
        
        # List of column migrations: (table, column, sql_type, default)
        column_migrations = [
            ("tasks", "state", "VARCHAR", "'ACTIVE'"),
            ("tasks", "created_by_user_id", "UUID REFERENCES users(id)", None),
            ("tasks", "state_changed_at", "TIMESTAMP", None),
            ("tasks", "state_reason", "TEXT", None),
            ("chat_threads", "last_response_id", "VARCHAR", None),
        ]
        
        for table, column, sql_type, default in column_migrations:
            try:
                # Check if column exists
                check_sql = text("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = :table AND column_name = :column
                """)
                exists = db.execute(check_sql, {"table": table, "column": column}).fetchone()
                
                if not exists:
                    # Add column
                    default_clause = f" DEFAULT {default}" if default else ""
                    alter_sql = text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}{default_clause}")
                    db.execute(alter_sql)
                    results["columns_added"].append(f"{table}.{column}")
                    logger.info(f"  ✓ Added column {table}.{column}")
                else:
                    results["columns_existed"].append(f"{table}.{column}")
            except Exception as e:
                results["errors"].append(f"{table}.{column}: {str(e)}")
                logger.warning(f"  ⚠ Error adding {table}.{column}: {e}")
        
        # Set default values for existing data
        # Find Ishay's user ID
        ishay_result = db.execute(text("SELECT id FROM users WHERE LOWER(name) LIKE '%ishay%' LIMIT 1")).fetchone()
        
        if ishay_result:
            ishay_id = str(ishay_result[0])
            logger.info(f"  Found Ishay with ID: {ishay_id}")
            
            # Set ALL tasks to be created by Ishay
            try:
                db.execute(text(f"UPDATE tasks SET created_by_user_id = '{ishay_id}' WHERE created_by_user_id IS NULL"))
                results["columns_added"].append("Set all tasks created_by to Ishay")
                logger.info("  ✓ Set created_by_user_id to Ishay for all tasks")
            except Exception as e:
                results["errors"].append(f"set created_by_user_id to Ishay: {str(e)}")
            
            # Set tasks where owner != Ishay to DRAFT state
            try:
                updated = db.execute(text(f"""
                    UPDATE tasks 
                    SET state = 'DRAFT', state_reason = 'Pending owner acceptance'
                    WHERE created_by_user_id = '{ishay_id}' 
                    AND owner_user_id != '{ishay_id}'
                    AND (state IS NULL OR state = 'ACTIVE')
                """))
                results["columns_added"].append(f"Set {updated.rowcount} tasks to DRAFT (owner != Ishay)")
                logger.info(f"  ✓ Set {updated.rowcount} tasks to DRAFT state (owner != creator)")
            except Exception as e:
                results["errors"].append(f"set DRAFT state: {str(e)}")
            
            # Set tasks where owner == Ishay to ACTIVE
            try:
                db.execute(text(f"""
                    UPDATE tasks 
                    SET state = 'ACTIVE'
                    WHERE created_by_user_id = '{ishay_id}' 
                    AND owner_user_id = '{ishay_id}'
                    AND state IS NULL
                """))
                logger.info("  ✓ Set Ishay's own tasks to ACTIVE state")
            except Exception as e:
                results["errors"].append(f"set ACTIVE state for Ishay: {str(e)}")
            
            # Create pending decisions for DRAFT tasks
            try:
                # Get all DRAFT tasks that need decisions
                draft_tasks = db.execute(text(f"""
                    SELECT t.id, t.title, t.owner_user_id 
                    FROM tasks t
                    WHERE t.state = 'DRAFT' 
                    AND t.created_by_user_id = '{ishay_id}'
                    AND t.owner_user_id != '{ishay_id}'
                    AND NOT EXISTS (
                        SELECT 1 FROM pending_decisions pd 
                        WHERE pd.task_id = t.id 
                        AND pd.decision_type = 'TASK_ACCEPTANCE'
                    )
                """)).fetchall()
                
                for task_id, title, owner_id in draft_tasks:
                    db.execute(text(f"""
                        INSERT INTO pending_decisions (id, user_id, task_id, decision_type, description, created_at)
                        VALUES (
                            gen_random_uuid(),
                            '{owner_id}',
                            '{task_id}',
                            'TASK_ACCEPTANCE',
                            'Ishay created task "{title}" for you. Accept, reject, or propose merge.',
                            CURRENT_TIMESTAMP
                        )
                    """))
                
                results["columns_added"].append(f"Created {len(draft_tasks)} pending decisions for DRAFT tasks")
                logger.info(f"  ✓ Created {len(draft_tasks)} pending decisions")
            except Exception as e:
                results["errors"].append(f"create pending decisions: {str(e)}")
        else:
            # Fallback: set created_by = owner if Ishay not found
            logger.warning("  ⚠ Ishay user not found, using owner as creator")
            try:
                db.execute(text("UPDATE tasks SET created_by_user_id = owner_user_id WHERE created_by_user_id IS NULL"))
                db.execute(text("UPDATE tasks SET state = 'ACTIVE' WHERE state IS NULL"))
            except Exception as e:
                results["errors"].append(f"fallback migration: {str(e)}")
        
        # Create new tables (if they don't exist)
        from app.database import Base, engine
        try:
            Base.metadata.create_all(bind=engine)
            results["tables_created"].append("All new tables created (if not existing)")
            logger.info("  ✓ Created new tables")
        except Exception as e:
            results["errors"].append(f"create tables: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "message": "Schema update completed!",
            "summary": {
                "columns_added": len(results["columns_added"]),
                "columns_existed": len(results["columns_existed"]),
                "errors": len(results["errors"])
            },
            "details": results
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Schema update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Schema update failed: {str(e)}")
