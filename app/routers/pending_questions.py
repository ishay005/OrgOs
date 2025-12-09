"""
Pending Questions API Router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Task, AttributeDefinition, AttributeAnswer
from app.services.questions import get_pending_questions_for_user, PendingQuestion
from app.services.similarity_cache import calculate_and_store_scores_for_answer

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
    attribute_type: str
    allowed_values: list[str] | None
    reason: str
    priority: int
    
    class Config:
        from_attributes = True


class DirectAnswerCreate(BaseModel):
    """Request body for submitting an answer directly"""
    task_id: Optional[str] = None
    target_user_id: str
    attribute_name: str
    value: str
    refused: bool = False


class DirectAnswerResponse(BaseModel):
    """Response for direct answer submission"""
    id: str
    message: str


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
        
        # Get attribute definition for type and allowed values
        attr_def = db.query(AttributeDefinition).filter(
            AttributeDefinition.name == p.attribute_name
        ).first()
        
        attribute_type = attr_def.type if attr_def else "string"
        allowed_values = attr_def.allowed_values if attr_def and attr_def.allowed_values else None
        
        responses.append(PendingQuestionResponse(
            id=p.id,
            target_user_id=str(p.target_user_id),
            target_user_name=target_user_name,
            task_id=str(p.task_id) if p.task_id else None,
            task_title=task_title,
            attribute_name=p.attribute_name,
            attribute_label=p.attribute_label,
            attribute_type=attribute_type,
            allowed_values=allowed_values,
            reason=p.reason,
            priority=p.priority
        ))
    
    return responses


@router.post("/answer", response_model=DirectAnswerResponse)
async def submit_direct_answer(
    answer_data: DirectAnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an answer directly without needing a question_id.
    
    This is used by the pending questions UI to save answers inline.
    """
    # Find the attribute definition
    attr_def = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == answer_data.attribute_name
    ).first()
    
    if not attr_def:
        raise HTTPException(status_code=404, detail=f"Attribute '{answer_data.attribute_name}' not found")
    
    # Parse task_id if provided
    task_id = None
    if answer_data.task_id and answer_data.task_id != 'null':
        try:
            task_id = UUID(answer_data.task_id)
            # Verify task exists
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id format")
    
    # Parse target_user_id
    try:
        target_user_id = UUID(answer_data.target_user_id)
        # Verify user exists
        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_user_id format")
    
    # Check if an answer already exists
    existing_answer = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == current_user.id,
        AttributeAnswer.target_user_id == target_user_id,
        AttributeAnswer.task_id == task_id,
        AttributeAnswer.attribute_id == attr_def.id
    ).first()
    
    if existing_answer:
        # Update existing answer
        existing_answer.value = answer_data.value
        existing_answer.refused = answer_data.refused
        message = "Answer updated successfully"
    else:
        # Create new answer
        new_answer = AttributeAnswer(
            answered_by_user_id=current_user.id,
            target_user_id=target_user_id,
            task_id=task_id,
            attribute_id=attr_def.id,
            value=answer_data.value,
            refused=answer_data.refused
        )
        db.add(new_answer)
        existing_answer = new_answer
        message = "Answer created successfully"
    
    db.commit()
    db.refresh(existing_answer)
    
    # Calculate and store similarity scores (don't fail the request if this fails)
    try:
        await calculate_and_store_scores_for_answer(db, existing_answer.id)
    except Exception as e:
        # Log the error but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to calculate similarity scores for answer {existing_answer.id}: {e}")
    
    return DirectAnswerResponse(
        id=str(existing_answer.id),
        message=message
    )

