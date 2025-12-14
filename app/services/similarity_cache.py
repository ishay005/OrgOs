"""
Service for calculating and caching similarity scores in the database.

This module handles:
1. Calculating similarity scores when answers change
2. Storing scores in the similarity_scores table
3. Retrieving pre-calculated scores for fast queries
"""
import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models import SimilarityScore, AttributeAnswer, AttributeDefinition, User
from app.services.similarity import compute_similarity, AttributeType

logger = logging.getLogger(__name__)


async def calculate_and_store_scores_for_answer(
    answer_id: UUID,
    db: Session
) -> int:
    """
    Calculate and store similarity scores for a single answer.
    
    This finds all other answers that should be compared with this one
    and calculates/stores their similarity scores.
    
    Args:
        answer_id: The UUID of the answer that was just created/updated
        db: Database session
        
    Returns:
        Number of similarity scores calculated and stored
    
    Logic:
        1. Get the answer that was just created/updated
        2. Find all other answers for the SAME task and attribute
        3. For each pair, calculate similarity and store in DB
    """
    # Get the answer
    answer = db.query(AttributeAnswer).filter(AttributeAnswer.id == answer_id).first()
    if not answer or answer.refused:
        logger.info(f"Answer {answer_id} not found or refused, skipping similarity calculation")
        return 0
    
    # Get the attribute definition to know the type
    attribute = db.query(AttributeDefinition).filter(
        AttributeDefinition.id == answer.attribute_id
    ).first()
    
    if not attribute:
        logger.error(f"Attribute not found for answer {answer_id}")
        return 0
    
    # Find all other answers for the SAME task and attribute
    # (but from different users)
    other_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.task_id == answer.task_id,
        AttributeAnswer.attribute_id == answer.attribute_id,
        AttributeAnswer.id != answer.id,
        AttributeAnswer.refused == False,
        AttributeAnswer.value != None
    ).all()
    
    logger.info(
        f"Calculating similarities for answer {answer_id}: "
        f"task={answer.task_id}, attribute={attribute.name}, "
        f"comparing with {len(other_answers)} other answers"
    )
    
    scores_calculated = 0
    
    for other_answer in other_answers:
        try:
            # Calculate similarity
            attr_type = AttributeType(attribute.type.value)
            similarity_score = await compute_similarity(
                value_a=answer.value,
                value_b=other_answer.value,
                attribute_type=attr_type,
                allowed_values=attribute.allowed_values,
                attribute_name=attribute.name
            )
            
            # Store or update the score
            # Always store with answer_a_id < answer_b_id for consistency
            if str(answer.id) < str(other_answer.id):
                answer_a_id, answer_b_id = answer.id, other_answer.id
            else:
                answer_a_id, answer_b_id = other_answer.id, answer.id
            
            # Check if score already exists
            existing_score = db.query(SimilarityScore).filter(
                SimilarityScore.answer_a_id == answer_a_id,
                SimilarityScore.answer_b_id == answer_b_id
            ).first()
            
            if existing_score:
                # Update existing score
                existing_score.similarity_score = similarity_score
                logger.debug(f"Updated score: {answer_a_id} <-> {answer_b_id} = {similarity_score:.3f}")
            else:
                # Create new score
                new_score = SimilarityScore(
                    answer_a_id=answer_a_id,
                    answer_b_id=answer_b_id,
                    similarity_score=similarity_score
                )
                db.add(new_score)
                logger.debug(f"Created score: {answer_a_id} <-> {answer_b_id} = {similarity_score:.3f}")
            
            scores_calculated += 1
            
        except Exception as e:
            logger.error(
                f"Error calculating similarity between {answer.id} and {other_answer.id}: {e}",
                exc_info=True
            )
            continue
    
    # Commit all changes
    db.commit()
    
    logger.info(f"Calculated and stored {scores_calculated} similarity scores for answer {answer_id}")
    return scores_calculated


async def get_cached_similarity(
    answer_a_id: UUID,
    answer_b_id: UUID,
    db: Session
) -> Optional[float]:
    """
    Get a pre-calculated similarity score from the cache.
    
    Args:
        answer_a_id: First answer UUID
        answer_b_id: Second answer UUID
        db: Database session
        
    Returns:
        Similarity score (0.0-1.0) if found, None otherwise
    """
    # Query for either direction (answer_a, answer_b) or (answer_b, answer_a)
    score = db.query(SimilarityScore).filter(
        or_(
            and_(
                SimilarityScore.answer_a_id == answer_a_id,
                SimilarityScore.answer_b_id == answer_b_id
            ),
            and_(
                SimilarityScore.answer_a_id == answer_b_id,
                SimilarityScore.answer_b_id == answer_a_id
            )
        )
    ).first()
    
    return score.similarity_score if score else None


async def recalculate_all_scores(db: Session) -> int:
    """
    Recalculate ALL similarity scores in the database.
    
    This is useful for:
    - Initial population of the cache
    - After changing similarity algorithms
    - Periodic recalculation
    
    WARNING: This can take a long time for large datasets!
    
    Returns:
        Total number of scores calculated
    """
    logger.info("Starting full recalculation of all similarity scores...")
    
    # Get all answers
    all_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.refused == False,
        AttributeAnswer.value != None
    ).all()
    
    total_scores = 0
    
    for answer in all_answers:
        scores = await calculate_and_store_scores_for_answer(answer.id, db)
        total_scores += scores
    
    logger.info(f"Full recalculation complete: {total_scores} total scores calculated")
    return total_scores


def recalculate_all_similarity_scores(db: Session) -> int:
    """
    SYNCHRONOUS version to recalculate similarity scores.
    Uses simple string matching instead of OpenAI for speed.
    
    Called after data import to populate similarity scores.
    
    Returns:
        Total number of scores calculated
    """
    logger.info("📊 Recalculating all similarity scores (sync mode)...")
    
    # Clear existing scores
    db.query(SimilarityScore).delete()
    db.commit()
    
    # Get all answers grouped by (task_id, attribute_id)
    all_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.refused == False,
        AttributeAnswer.value != None
    ).all()
    
    # Group answers by (task_id, attribute_id)
    answer_groups = {}
    for answer in all_answers:
        key = (str(answer.task_id) if answer.task_id else 'none', str(answer.attribute_id))
        if key not in answer_groups:
            answer_groups[key] = []
        answer_groups[key].append(answer)
    
    total_scores = 0
    
    for key, answers in answer_groups.items():
        if len(answers) < 2:
            continue
        
        # Compare all pairs
        for i, answer_a in enumerate(answers):
            for answer_b in answers[i+1:]:
                # Simple similarity calculation (exact match = 1.0, else try to compute)
                if answer_a.value == answer_b.value:
                    similarity = 1.0
                else:
                    # For strings, use simple comparison
                    val_a = str(answer_a.value).strip().lower()
                    val_b = str(answer_b.value).strip().lower()
                    
                    if val_a == val_b:
                        similarity = 1.0
                    elif val_a in val_b or val_b in val_a:
                        similarity = 0.7
                    else:
                        # Check if both are dependency attributes (exact match for tasks)
                        # For enum values, same = 1.0, different = 0.0
                        similarity = 0.0
                
                # Store with consistent ordering
                if str(answer_a.id) < str(answer_b.id):
                    a_id, b_id = answer_a.id, answer_b.id
                else:
                    a_id, b_id = answer_b.id, answer_a.id
                
                new_score = SimilarityScore(
                    answer_a_id=a_id,
                    answer_b_id=b_id,
                    similarity_score=similarity
                )
                db.add(new_score)
                total_scores += 1
    
    db.commit()
    logger.info(f"✅ Created {total_scores} similarity scores")
    return total_scores

