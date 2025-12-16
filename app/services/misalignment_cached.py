"""
Optimized misalignment computation using pre-calculated similarity scores.

This module replaces the slow on-demand calculation with fast database lookups.
"""
import logging
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, 
    EntityType, SimilarityScore, TaskDependency, TaskRelevantUser
)
from app.config import settings

logger = logging.getLogger(__name__)


def get_relationship_type(user: User, other_user: User) -> str:
    """
    Determine the relationship type between two users.
    Returns: 'manager', 'employee', 'teammate', 'other'
    """
    if user.manager_id == other_user.id:
        return 'manager'  # other_user is my manager
    elif other_user.manager_id == user.id:
        return 'employee'  # other_user is my employee
    elif user.manager_id and user.manager_id == other_user.manager_id:
        return 'teammate'  # same manager
    else:
        return 'other'  # connected via task dependencies only


def get_connected_task_ids(db: Session, user_id: UUID, other_user_id: UUID) -> set:
    """
    Get task IDs where these users have a connection (dependency, parent, child).
    
    Returns set of task IDs owned by other_user that are connected to user's tasks.
    """
    connected_tasks = set()
    
    # Get all tasks owned by both users
    my_tasks = db.query(Task).filter(Task.owner_user_id == user_id, Task.is_active == True).all()
    their_tasks = db.query(Task).filter(Task.owner_user_id == other_user_id, Task.is_active == True).all()
    
    my_task_ids = {t.id for t in my_tasks}
    their_task_ids = {t.id for t in their_tasks}
    
    # 1. Check direct dependencies (my task depends on their task, or vice versa)
    for dep in db.query(TaskDependency).all():
        # My task depends on their task
        if dep.task_id in my_task_ids and dep.depends_on_task_id in their_task_ids:
            connected_tasks.add(dep.depends_on_task_id)
        # Their task depends on my task
        if dep.task_id in their_task_ids and dep.depends_on_task_id in my_task_ids:
            connected_tasks.add(dep.task_id)
    
    # 2. Check mutual parent (my task and their task have the same parent)
    for my_task in my_tasks:
        if my_task.parent_id:
            for their_task in their_tasks:
                if their_task.parent_id == my_task.parent_id:
                    connected_tasks.add(their_task.id)
    
    # 3. Check parent-child relationship (my task is parent/child of their task)
    for my_task in my_tasks:
        for their_task in their_tasks:
            # Their task is a child of my task
            if their_task.parent_id == my_task.id:
                connected_tasks.add(their_task.id)
            # My task is a child of their task
            if my_task.parent_id == their_task.id:
                connected_tasks.add(their_task.id)
    
    return connected_tasks


class MisalignmentDTO(BaseModel):
    """Data transfer object for a single misalignment"""
    other_user_id: UUID
    other_user_name: str
    task_id: Optional[UUID]
    task_title: Optional[str]
    attribute_id: UUID
    attribute_name: str
    attribute_label: str
    your_value: str
    their_value: str
    similarity_score: float


async def compute_misalignments_for_user_cached(
    user_id: UUID,
    db: Session,
    threshold: Optional[float] = None,
    include_all: bool = False
) -> list[MisalignmentDTO]:
    """
    Compute misalignments using PRE-CALCULATED similarity scores.
    
    This is 100x+ faster than the original version because it reads
    from the similarity_scores table instead of calling OpenAI.
    
    Args:
        user_id: UUID of the user to compute misalignments for
        db: Database session
        threshold: Similarity threshold (default from settings)
        include_all: If True, return all pairs regardless of threshold
    
    Returns:
        List of MisalignmentDTO objects representing perception gaps
    """
    if threshold is None:
        threshold = settings.misalignment_threshold
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User {user_id} not found")
        return []
    
    misalignments = []
    
    # Find all tasks where this user is marked as relevant
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user_id
    ).all()
    
    # Get unique task owner pairs
    task_owner_pairs = []
    for entry in relevant_entries:
        task = db.query(Task).filter(Task.id == entry.task_id, Task.is_active == True).first()
        if task and task.owner_user_id != user_id:
            other_user = db.query(User).filter(User.id == task.owner_user_id).first()
            if other_user:
                task_owner_pairs.append((task, other_user))
    
    logger.info(
        f"Computing misalignments (cached) for user {user.name} "
        f"with {len(task_owner_pairs)} relevant tasks"
    )
    
    processed_pairs = set()
    for task, other_user in task_owner_pairs:
        pair_key = (task.id, other_user.id)
        if pair_key in processed_pairs:
            continue
        processed_pairs.add(pair_key)
        
        # We already have task and other_user from the loop
        # Determine relationship type
        relationship = get_relationship_type(user, other_user)
        
        # We're directly working with the relevant task
        # Get all task attributes
        task_attributes = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.TASK
        ).all()
        
        for attribute in task_attributes:
            # Get current user's answer about other user's task
            my_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == other_user.id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).first()
            
            # Get other user's self-answer about their own task
            their_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == other_user.id,
                AttributeAnswer.target_user_id == other_user.id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).first()
            
            # Both answers must exist
            if not my_answer or not their_answer:
                continue
            
            if not my_answer.value or not their_answer.value:
                continue
            
            # Look up PRE-CALCULATED similarity score from cache
            similarity_score_record = db.query(SimilarityScore).filter(
                or_(
                    and_(
                        SimilarityScore.answer_a_id == my_answer.id,
                    SimilarityScore.answer_b_id == their_answer.id
                ),
                and_(
                    SimilarityScore.answer_a_id == their_answer.id,
                    SimilarityScore.answer_b_id == my_answer.id
                )
            )
            ).first()
            
            if similarity_score_record:
                similarity_score = similarity_score_record.similarity_score
                
                # Include if below threshold (or if include_all is True)
                if include_all or similarity_score < threshold:
                    misalignment = MisalignmentDTO(
                        other_user_id=other_user.id,
                        other_user_name=other_user.name,
                        task_id=task.id,
                        task_title=task.title,
                        attribute_id=attribute.id,
                        attribute_name=attribute.name,
                        attribute_label=attribute.label,
                        your_value=my_answer.value,
                        their_value=their_answer.value,
                        similarity_score=similarity_score
                    )
                    
                    misalignments.append(misalignment)
                    
                    if similarity_score < threshold:
                        logger.debug(
                            f"Misalignment found (cached): {user.name} vs {other_user.name} "
                            f"on {task.title}/{attribute.label}: "
                            f"score={similarity_score:.3f}"
                        )
            else:
                # Fallback: simple string comparison when no cached score exists
                if my_answer.value.strip().lower() == their_answer.value.strip().lower():
                    similarity_score = 1.0
                elif my_answer.value.strip().lower() in their_answer.value.strip().lower() or \
                     their_answer.value.strip().lower() in my_answer.value.strip().lower():
                    similarity_score = 0.7
                else:
                    similarity_score = 0.0
                
                # Include if below threshold (or if include_all is True)
                if include_all or similarity_score < threshold:
                    misalignment = MisalignmentDTO(
                        other_user_id=other_user.id,
                        other_user_name=other_user.name,
                        task_id=task.id,
                        task_title=task.title,
                        attribute_id=attribute.id,
                        attribute_name=attribute.name,
                        attribute_label=attribute.label,
                        your_value=my_answer.value,
                        their_value=their_answer.value,
                        similarity_score=similarity_score
                    )
                    misalignments.append(misalignment)
    
    # REVERSE DIRECTION: Check how OTHERS perceive MY tasks
    # This shows if my manager or teammates understand my work
    logger.info(f"Checking reverse comparisons (others' views of {user.name}'s tasks)")
    
    # Get all tasks owned by current user
    my_tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    for task in my_tasks:
        # Get all task attributes
        task_attributes = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.TASK
        ).all()
        
        for attribute in task_attributes:
            # Get my self-answer about my own task
            my_self_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == user_id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).first()
            
            if not my_self_answer or not my_self_answer.value:
                continue
            
            # Find ALL other users who answered about MY task
            others_answers = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id != user_id,  # Not me
                AttributeAnswer.target_user_id == user_id,  # About me
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).all()
            
            for other_answer in others_answers:
                if not other_answer.value:
                    continue
                
                # Get the other user
                other_user = db.query(User).filter(
                    User.id == other_answer.answered_by_user_id
                ).first()
                
                if not other_user:
                    continue
                
                # Look up PRE-CALCULATED similarity score
                similarity_score_record = db.query(SimilarityScore).filter(
                    or_(
                        and_(
                            SimilarityScore.answer_a_id == my_self_answer.id,
                            SimilarityScore.answer_b_id == other_answer.id
                        ),
                        and_(
                            SimilarityScore.answer_a_id == other_answer.id,
                            SimilarityScore.answer_b_id == my_self_answer.id
                        )
                    )
                ).first()
                
                if similarity_score_record:
                    similarity_score = similarity_score_record.similarity_score
                else:
                    # Fallback: simple string comparison when no cached score exists
                    if my_self_answer.value.strip().lower() == other_answer.value.strip().lower():
                        similarity_score = 1.0
                    elif my_self_answer.value.strip().lower() in other_answer.value.strip().lower() or \
                         other_answer.value.strip().lower() in my_self_answer.value.strip().lower():
                        similarity_score = 0.7
                    else:
                        similarity_score = 0.0
                
                # Include if below threshold (or if include_all is True)
                if include_all or similarity_score < threshold:
                    misalignment = MisalignmentDTO(
                        other_user_id=other_user.id,
                        other_user_name=other_user.name,
                        task_id=task.id,
                        task_title=task.title,
                        attribute_id=attribute.id,
                        attribute_name=attribute.name,
                        attribute_label=attribute.label,
                        your_value=my_self_answer.value,
                        their_value=other_answer.value,
                        similarity_score=similarity_score
                    )
                    
                    misalignments.append(misalignment)
                    
                    if similarity_score < threshold:
                        logger.debug(
                            f"Reverse misalignment found: {other_user.name} vs {user.name} "
                            f"on {task.title}/{attribute.label}: "
                            f"score={similarity_score:.3f}"
                        )
    
    logger.info(
        f"Found {len(misalignments)} total comparison(s) (cached) for {user.name} "
        f"(threshold={threshold})"
    )
    
    return misalignments

