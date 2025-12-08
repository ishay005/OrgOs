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
    User, Task, AttributeDefinition, AttributeAnswer, AlignmentEdge, 
    EntityType, SimilarityScore
)
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
    
    # Find all users this user aligns with
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    
    logger.info(
        f"Computing misalignments (cached) for user {user.name} "
        f"with {len(alignments)} alignments"
    )
    
    for alignment in alignments:
        # Get the aligned user
        other_user = db.query(User).filter(
            User.id == alignment.target_user_id
        ).first()
        
        if not other_user:
            continue
        
        # Get all active tasks owned by the other user
        tasks = db.query(Task).filter(
            Task.owner_user_id == other_user.id,
            Task.is_active == True
        ).all()
        
        for task in tasks:
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
                    logger.warning(
                        f"No cached similarity score found for answers "
                        f"{my_answer.id} and {their_answer.id}. "
                        f"This should have been calculated when the answer was saved!"
                    )
    
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

