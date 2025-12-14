"""
Questions and answers endpoints
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, QuestionLog, 
    EntityType, TaskRelevantUser
)
from app.schemas import QuestionResponse, AnswerCreate, AnswerResponse
from app.services.llm_questions import generate_question_from_context
from app.services.similarity_cache import calculate_and_store_scores_for_answer

router = APIRouter(prefix="/questions", tags=["questions"])
answers_router = APIRouter(prefix="/answers", tags=["answers"])


async def get_pending_questions(
    user: User,
    db: Session,
    max_questions: int = 10
) -> List[QuestionResponse]:
    """
    Select pending (task, attribute) combinations for the user.
    Returns question stubs ready for answering.
    """
    questions = []
    
    # Get tasks the user should answer about (owned by them or where they are marked as relevant)
    # Own tasks
    own_tasks = db.query(Task).filter(
        Task.owner_user_id == user.id,
        Task.is_active == True
    ).all()
    
    # Tasks where user is marked as relevant
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user.id
    ).all()
    relevant_task_ids = [r.task_id for r in relevant_entries]
    
    relevant_tasks = db.query(Task).filter(
        Task.id.in_(relevant_task_ids),
        Task.is_active == True
    ).all() if relevant_task_ids else []
    
    # Combine and dedupe
    task_ids_seen = set()
    tasks = []
    for t in list(own_tasks) + list(relevant_tasks):
        if t.id not in task_ids_seen:
            task_ids_seen.add(t.id)
            tasks.append(t)
    
    # Get all task attributes
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    # For each task and each attribute, check if answer is missing or stale
    for task in tasks:
        task_owner = db.query(User).filter(User.id == task.owner_user_id).first()
        
        for attribute in task_attributes:
            # Check if answer exists and is recent
            existing_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user.id,
                AttributeAnswer.target_user_id == task.owner_user_id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attribute.id
            ).order_by(AttributeAnswer.updated_at.desc()).first()
            
            # Skip if user refused to answer
            if existing_answer and existing_answer.refused:
                continue
            
            # Determine if answer is stale (older than 1 day)
            is_stale = False
            previous_value = None
            if existing_answer:
                age = datetime.utcnow() - existing_answer.updated_at
                is_stale = age > timedelta(days=1)
                previous_value = existing_answer.value
            
            # Include if missing or stale
            if not existing_answer or is_stale:
                # Generate question text using LLM
                question_text = await generate_question_from_context(
                    attribute_label=attribute.label,
                    attribute_description=attribute.description,
                    attribute_type=attribute.type.value,
                    allowed_values=attribute.allowed_values,
                    target_user_name=task_owner.name,
                    task_title=task.title,
                    task_description=task.description,
                    previous_value=previous_value,
                    is_followup=is_stale,
                    answering_user_name=user.name
                )
                
                # Create question log entry
                question_log = QuestionLog(
                    answered_by_user_id=user.id,
                    target_user_id=task.owner_user_id,
                    task_id=task.id,
                    attribute_id=attribute.id,
                    question_text=question_text
                )
                db.add(question_log)
                db.commit()
                db.refresh(question_log)
                
                questions.append({
                    "question_id": question_log.id,
                    "target_user_id": task.owner_user_id,
                    "target_user_name": task_owner.name,
                    "task_id": task.id,
                    "task_title": task.title,
                    "attribute_id": attribute.id,
                    "attribute_name": attribute.name,
                    "attribute_label": attribute.label,
                    "attribute_type": attribute.type.value,
                    "allowed_values": attribute.allowed_values,
                    "is_followup": is_stale,
                    "previous_value": previous_value,
                    "question_text": question_text
                })
                
                if len(questions) >= max_questions:
                    return questions
    
    return questions


@router.get("/next", response_model=List[QuestionResponse])
async def get_next_questions(
    max_questions: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get next set of questions for the current user.
    Selects pending (task, attribute) combinations that need answering.
    Uses LLM to generate friendly, natural question text.
    """
    questions = await get_pending_questions(current_user, db, max_questions)
    return questions


@answers_router.post("", response_model=AnswerResponse)
async def submit_answer(
    answer_data: AnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an answer to a question.
    Creates or updates the AttributeAnswer record.
    """
    # Look up the question log
    question_log = db.query(QuestionLog).filter(
        QuestionLog.id == answer_data.question_id
    ).first()
    
    if not question_log:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Verify the question was for this user
    if question_log.answered_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="This question is not for you")
    
    # Check if answer already exists
    existing_answer = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == current_user.id,
        AttributeAnswer.target_user_id == question_log.target_user_id,
        AttributeAnswer.task_id == question_log.task_id,
        AttributeAnswer.attribute_id == question_log.attribute_id
    ).first()
    
    if existing_answer:
        # Update existing answer
        if answer_data.refused:
            existing_answer.refused = True
            existing_answer.value = None
        else:
            existing_answer.value = answer_data.value
            existing_answer.refused = False
        existing_answer.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing_answer)
        
        # Trigger similarity score calculation in background
        await calculate_and_store_scores_for_answer(existing_answer.id, db)
        
        return existing_answer
    else:
        # Create new answer
        new_answer = AttributeAnswer(
            answered_by_user_id=current_user.id,
            target_user_id=question_log.target_user_id,
            task_id=question_log.task_id,
            attribute_id=question_log.attribute_id,
            value=answer_data.value if not answer_data.refused else None,
            refused=answer_data.refused
        )
        db.add(new_answer)
        db.commit()
        db.refresh(new_answer)
        
        # Trigger similarity score calculation in background
        await calculate_and_store_scores_for_answer(new_answer.id, db)
        
        return new_answer

