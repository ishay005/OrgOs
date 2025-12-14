"""
Pending questions service - tracks what needs to be answered by each user.
"""
from datetime import datetime, timedelta
from typing import List
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, 
    SimilarityScore, TaskRelevantUser
)


class PendingQuestion(BaseModel):
    """Represents a question that needs to be asked to a user."""
    id: str  # Composite: f"{task_id or 'user'}_{attribute_name}_{target_user_id}"
    target_user_id: UUID
    task_id: UUID | None
    attribute_name: str
    attribute_label: str
    reason: str  # "missing" | "stale" | "misaligned"
    priority: int  # Lower = more important
    
    class Config:
        frozen = True


async def get_pending_questions_for_user(
    db: AsyncSession,
    user_id: UUID
) -> List[PendingQuestion]:
    """
    Get all pending questions for a user, sorted by priority.
    
    Logic:
    1. Find all tasks the user should answer about:
       - Their own tasks
       - Tasks owned by users they align with
    2. For each (task, attribute) pair, check if:
       - Missing: No answer exists
       - Stale: Answer is older than 7 days
       - Misaligned: Low similarity score exists
    3. Compute priority and return sorted list
    """
    pending: List[PendingQuestion] = []
    staleness_days = 7
    
    # Get user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return []
    
    # Get tasks owned by user
    owned_tasks_result = await db.execute(
        select(Task)
        .where(
            and_(
                Task.owner_user_id == user_id,
                Task.is_active == True
            )
        )
    )
    owned_tasks = owned_tasks_result.scalars().all()
    
    # Get tasks where user is marked as relevant
    relevant_result = await db.execute(
        select(TaskRelevantUser.task_id)
        .where(TaskRelevantUser.user_id == user_id)
    )
    relevant_task_ids = [row[0] for row in relevant_result.fetchall()]
    
    relevant_tasks = []
    if relevant_task_ids:
        relevant_tasks_result = await db.execute(
            select(Task)
            .where(
                and_(
                    Task.id.in_(relevant_task_ids),
                    Task.is_active == True
                )
            )
        )
        relevant_tasks = relevant_tasks_result.scalars().all()
    
    # Combine and dedupe
    task_ids_seen = set()
    tasks = []
    for t in list(owned_tasks) + list(relevant_tasks):
        if t.id not in task_ids_seen:
            task_ids_seen.add(t.id)
            tasks.append(t)
    
    # Get all task attributes
    attrs_result = await db.execute(
        select(AttributeDefinition)
        .where(AttributeDefinition.entity_type == "task")
    )
    attributes = attrs_result.scalars().all()
    
    # For each task and attribute, check if pending
    for task in tasks:
        for attr in attributes:
            # Check if this user has answered this (task, attribute, target_user)
            answer_result = await db.execute(
                select(AttributeAnswer)
                .where(
                    and_(
                        AttributeAnswer.answered_by_user_id == user_id,
                        AttributeAnswer.target_user_id == task.owner_user_id,
                        AttributeAnswer.task_id == task.id,
                        AttributeAnswer.attribute_id == attr.id,
                        AttributeAnswer.refused == False
                    )
                )
                .order_by(AttributeAnswer.updated_at.desc())
            )
            answer = answer_result.scalar_one_or_none()
            
            # Determine reason
            reason = None
            if answer is None:
                reason = "missing"
            elif answer.updated_at < datetime.utcnow() - timedelta(days=staleness_days):
                reason = "stale"
            
            # Check misalignment
            if answer is not None:
                # Check if there's a low similarity score
                sim_result = await db.execute(
                    select(SimilarityScore)
                    .where(
                        and_(
                            or_(
                                and_(
                                    SimilarityScore.answer_a_id == answer.id,
                                    SimilarityScore.similarity_score < 0.6
                                ),
                                and_(
                                    SimilarityScore.answer_b_id == answer.id,
                                    SimilarityScore.similarity_score < 0.6
                                )
                            )
                        )
                    )
                )
                if sim_result.scalar_one_or_none():
                    reason = "misaligned"
            
            # If we have a reason, add to pending
            if reason:
                # Compute priority
                priority = _compute_priority(task, attr, reason)
                
                pending_q = PendingQuestion(
                    id=f"{task.id}_{attr.name}_{task.owner_user_id}",
                    target_user_id=task.owner_user_id,
                    task_id=task.id,
                    attribute_name=attr.name,
                    attribute_label=attr.label,
                    reason=reason,
                    priority=priority
                )
                pending.append(pending_q)
    
    # Sort by priority (lower = more important)
    pending.sort(key=lambda x: x.priority)
    
    return pending


def _compute_priority(task: Task, attr: AttributeDefinition, reason: str) -> int:
    """
    Compute priority for a pending question.
    Lower number = higher priority.
    """
    base = 100
    
    # Adjust by reason
    if reason == "missing":
        base -= 30
    elif reason == "misaligned":
        base -= 20
    elif reason == "stale":
        base -= 10
    
    # Adjust by attribute importance (if we can infer from name)
    important_attrs = ["priority", "status", "main_goal"]
    if attr.name in important_attrs:
        base -= 15
    
    # Could also check task.priority attribute answer if it exists
    # For now, keep it simple
    
    return max(0, base)

