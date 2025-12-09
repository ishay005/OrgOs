"""
Pending Questions API Router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Task
from app.services.questions import get_pending_questions_for_user, PendingQuestion

router = APIRouter(prefix="/pending-questions", tags=["pending-questions"])


class PendingQuestionResponse(BaseModel):
    """Response model for a pending question"""
    id: str
    target_user_id: str
    target_user_name: str
    task_id: str | None
    task_title: str | None
    attribute_name: str
    attribute_label: str
    reason: str
    priority: int
    
    class Config:
        from_attributes = True


@router.get("", response_model=List[PendingQuestionResponse])
async def get_pending_questions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all pending questions for the current user.
    
    Returns a list of questions that need to be answered, sorted by priority.
    """
    # Use the sync version from robin_orchestrator
    from app.services.robin_orchestrator import _get_pending_sync
    
    pending = _get_pending_sync(db, current_user.id)
    
    # Enrich with user and task names
    responses = []
    for p in pending:
        # Get target user name
        target_user = db.query(User).filter(User.id == p.target_user_id).first()
        target_user_name = target_user.name if target_user else "Unknown"
        
        # Get task title if applicable
        task_title = None
        if p.task_id:
            task = db.query(Task).filter(Task.id == p.task_id).first()
            task_title = task.title if task else "Unknown Task"
        
        responses.append(PendingQuestionResponse(
            id=p.id,
            target_user_id=str(p.target_user_id),
            target_user_name=target_user_name,
            task_id=str(p.task_id) if p.task_id else None,
            task_title=task_title,
            attribute_name=p.attribute_name,
            attribute_label=p.attribute_label,
            reason=p.reason,
            priority=p.priority
        ))
    
    return responses

