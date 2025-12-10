"""
API endpoint for previewing prompts with real context
"""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from uuid import UUID
from pydantic import BaseModel

from app.database import get_db
from app.services import robin_orchestrator

router = APIRouter(prefix="/prompts/preview", tags=["prompts"])


class PromptPreviewRequest(BaseModel):
    mode: str  # "morning_brief", "user_question", "collect_data"
    has_pending: bool
    prompt_text: str
    context_config: dict


class PromptPreviewResponse(BaseModel):
    full_prompt: dict  # Contains system_prompt, context, and formatting


@router.post("", response_model=PromptPreviewResponse)
async def preview_prompt(
    request: PromptPreviewRequest,
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Build a preview of what the full prompt will look like with real data.
    Uses the exact same functions as the actual Robin orchestrator.
    """
    user_id = UUID(x_user_id)
    
    # Get real user snapshot and task snapshot using the context config
    user_snapshot = robin_orchestrator._get_user_snapshot(db, user_id, request.context_config)
    task_snapshot = robin_orchestrator._get_task_snapshot(db, user_id, request.context_config)
    
    # Get pending questions (just for preview, we'll use empty list)
    pending_relevant = []
    
    # Create a dummy thread_id for preview
    from uuid import uuid4
    dummy_thread_id = uuid4()
    
    # Get recent messages (using the history_size from config)
    message_limit = request.context_config.get('history_size', 2)
    recent_messages = robin_orchestrator._get_recent_chat_messages(db, dummy_thread_id, message_limit)
    
    # Build the actual context string
    context_str = robin_orchestrator._build_context_string(
        request.mode,
        user_snapshot,
        task_snapshot,
        pending_relevant,
        db,
        dummy_thread_id,
        recent_messages,
        request.context_config
    )
    
    # Return the formatted prompt
    return PromptPreviewResponse(
        full_prompt={
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": request.prompt_text
                },
                {
                    "role": "system",
                    "content": f"Context:\n{context_str}"
                },
                {
                    "role": "user",
                    "content": "[User's message will appear here]"
                }
            ],
            "mode": request.mode,
            "has_pending": request.has_pending,
            "context_summary": {
                "user": user_snapshot.get('name', 'Unknown'),
                "tasks_count": len(task_snapshot),
                "history_size": message_limit
            }
        }
    )

