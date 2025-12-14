"""
Misalignment computation service

This module finds perception gaps between users by comparing their answers
about the same tasks and attributes.
"""
import logging
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, EntityType, TaskRelevantUser
)
from app.services.similarity import compute_similarity, AttributeType
from app.config import settings

logger = logging.getLogger(__name__)


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


async def compute_misalignments_for_user(
    user_id: UUID,
    db: Session,
    threshold: Optional[float] = None,
    include_all: bool = False
) -> list[MisalignmentDTO]:
    """
    Compute misalignments between a user and people they align with.
    
    This function finds cases where:
    - User U has answered about user V's task
    - User V has answered about their own task
    - The answers differ (similarity < threshold)
    
    Args:
        user_id: UUID of the user to compute misalignments for
        db: Database session
        threshold: Similarity threshold below which to report misalignment
                   (default from settings.misalignment_threshold)
        include_all: If True, return all pairs regardless of threshold
                     (useful for debug endpoint)
    
    Returns:
        List of MisalignmentDTO objects representing perception gaps
    
    Logic:
        1. Find all tasks where user U is in the relevant_users list
        2. For each such task T (owned by user V):
           a. For each task attribute A
           b. Get U's answer about V's task (answered_by=U, target=V, task=T)
           c. Get V's self-answer (answered_by=V, target=V, task=T)
           d. If both answers exist and not refused:
              - Compute similarity using embeddings/type-specific logic
              - If similarity < threshold, report as misalignment
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
    
    # Get unique task owners (excluding self)
    task_owner_pairs = []  # (task, owner)
    for entry in relevant_entries:
        task = db.query(Task).filter(Task.id == entry.task_id, Task.is_active == True).first()
        if task and task.owner_user_id != user_id:
            owner = db.query(User).filter(User.id == task.owner_user_id).first()
            if owner:
                task_owner_pairs.append((task, owner))
    
    logger.info(
        f"Computing misalignments for user {user.name} with {len(task_owner_pairs)} relevant tasks"
    )
    
    # Process each task-owner pair
    processed_pairs = set()
    for task, other_user in task_owner_pairs:
        pair_key = (task.id, other_user.id)
        if pair_key in processed_pairs:
            continue
        processed_pairs.add(pair_key)
        
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
            
            # Compute similarity using the similarity engine
            try:
                # Convert attribute type to AttributeType enum
                attr_type = AttributeType(attribute.type.value)
                
                similarity_score = await compute_similarity(
                    value_a=my_answer.value,
                    value_b=their_answer.value,
                    attribute_type=attr_type,
                    allowed_values=attribute.allowed_values,
                    attribute_name=attribute.name
                )
                
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
                        logger.info(
                            f"Misalignment found: {user.name} vs {other_user.name} "
                            f"on {task.title}/{attribute.label}: "
                            f"'{my_answer.value}' vs '{their_answer.value}' "
                            f"(score={similarity_score:.3f})"
                        )
            
            except Exception as e:
                logger.error(
                    f"Error computing similarity for {attribute.name}: {e}",
                    exc_info=True
                )
                continue
    
    logger.info(
        f"Found {len(misalignments)} misalignment(s) for {user.name} "
        f"(threshold={threshold})"
    )
    
    return misalignments


async def compute_user_misalignments(
    user_id: UUID,
    db: Session,
    include_user_attributes: bool = False
) -> list[MisalignmentDTO]:
    """
    Compute misalignments for user attributes (optional).
    
    This is similar to task misalignments but for user-level attributes
    like role_title, decision_scope, etc.
    
    Args:
        user_id: UUID of the user
        db: Database session
        include_user_attributes: Whether to check user attributes
    
    Returns:
        List of misalignments for user attributes
    """
    if not include_user_attributes:
        return []
    
    misalignments = []
    threshold = settings.misalignment_threshold
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    # Find aligned users from TaskRelevantUser (task owners where this user is relevant)
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user_id
    ).all()
    
    # Get unique other users (task owners)
    other_user_ids = set()
    for entry in relevant_entries:
        task = db.query(Task).filter(Task.id == entry.task_id).first()
        if task and task.owner_user_id != user_id:
            other_user_ids.add(task.owner_user_id)
    
    for other_user_id in other_user_ids:
        other_user = db.query(User).filter(User.id == other_user_id).first()
        if not other_user:
            continue
        
        # Get all user attributes
        user_attributes = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == EntityType.USER
        ).all()
        
        for attribute in user_attributes:
            # Get current user's answer about other user
            my_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == other_user.id,
                AttributeAnswer.task_id == None,  # User attributes have no task
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).first()
            
            # Get other user's self-answer
            their_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == other_user.id,
                AttributeAnswer.target_user_id == other_user.id,
                AttributeAnswer.task_id == None,
                AttributeAnswer.attribute_id == attribute.id,
                AttributeAnswer.refused == False
            ).first()
            
            if not my_answer or not their_answer:
                continue
            
            if not my_answer.value or not their_answer.value:
                continue
            
            try:
                attr_type = AttributeType(attribute.type.value)
                
                similarity_score = await compute_similarity(
                    value_a=my_answer.value,
                    value_b=their_answer.value,
                    attribute_type=attr_type,
                    allowed_values=attribute.allowed_values,
                    attribute_name=attribute.name
                )
                
                if similarity_score < threshold:
                    misalignment = MisalignmentDTO(
                        other_user_id=other_user.id,
                        other_user_name=other_user.name,
                        task_id=None,  # User attribute, no task
                        task_title=None,
                        attribute_id=attribute.id,
                        attribute_name=attribute.name,
                        attribute_label=attribute.label,
                        your_value=my_answer.value,
                        their_value=their_answer.value,
                        similarity_score=similarity_score
                    )
                    
                    misalignments.append(misalignment)
            
            except Exception as e:
                logger.error(f"Error computing user attribute similarity: {e}")
                continue
    
    return misalignments

