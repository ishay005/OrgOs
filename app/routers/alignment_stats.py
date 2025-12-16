"""
Alignment statistics endpoints - reads from pre-computed similarity_scores cache
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import User, Task, AttributeAnswer, SimilarityScore
from typing import Dict

router = APIRouter(prefix="/alignment-stats", tags=["alignment-stats"])


@router.get("/users")
async def get_user_alignment_stats(db: Session = Depends(get_db)) -> Dict[str, float]:
    """
    Get alignment percentage for each user from pre-computed similarity scores.
    
    Returns: { "user_id": alignment_percentage (0-100) }
    
    Reads from the similarity_scores table which is updated whenever answers change.
    """
    users = db.query(User).all()
    stats = {}
    
    for user in users:
        # Get all answer IDs for this user
        user_answer_ids = [
            a.id for a in db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user.id,
                AttributeAnswer.refused == False
            ).all()
        ]
        
        if not user_answer_ids:
            stats[str(user.id)] = 100.0  # No data = assume aligned
            continue
        
        # Get all pre-computed similarity scores involving this user's answers
        scores = db.query(SimilarityScore).filter(
            or_(
                SimilarityScore.answer_a_id.in_(user_answer_ids),
                SimilarityScore.answer_b_id.in_(user_answer_ids)
            )
        ).all()
        
        if scores:
            # Average similarity score as alignment percentage
            avg_similarity = sum(s.similarity_score for s in scores) / len(scores)
            stats[str(user.id)] = round(avg_similarity * 100, 1)
        else:
            # Fallback: simple comparison if no cached scores
            user_answers = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user.id,
                AttributeAnswer.refused == False
            ).all()
            
            if not user_answers:
                stats[str(user.id)] = 100.0
                continue
            
            total = 0
            aligned = 0
            for ua in user_answers:
                # Compare against other users' answers on same task/attribute
                others = db.query(AttributeAnswer).filter(
                    AttributeAnswer.task_id == ua.task_id,
                    AttributeAnswer.attribute_id == ua.attribute_id,
                    AttributeAnswer.answered_by_user_id != user.id,
                    AttributeAnswer.refused == False
                ).all()
                for ob in others:
                    total += 1
                    if ua.value and ob.value and ua.value.strip().lower() == ob.value.strip().lower():
                        aligned += 1
            stats[str(user.id)] = round((aligned / total) * 100, 1) if total > 0 else 100.0
    
    return stats


@router.get("/tasks")
async def get_task_alignment_stats(db: Session = Depends(get_db)) -> Dict[str, float]:
    """
    Get alignment percentage for each task from pre-computed similarity scores.
    
    Returns: { "task_id": alignment_percentage (0-100) }
    
    Reads from the similarity_scores table which is updated whenever answers change.
    """
    tasks = db.query(Task).filter(Task.is_active == True).all()
    stats = {}
    
    for task in tasks:
        # Get all answer IDs for this task
        task_answer_ids = [
            a.id for a in db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.refused == False
            ).all()
        ]
        
        if not task_answer_ids:
            stats[str(task.id)] = 100.0  # No data = assume aligned
            continue
        
        # Get all pre-computed similarity scores for answers about this task
        scores = db.query(SimilarityScore).filter(
            or_(
                SimilarityScore.answer_a_id.in_(task_answer_ids),
                SimilarityScore.answer_b_id.in_(task_answer_ids)
            )
        ).all()
        
        if scores:
            # Average similarity score as alignment percentage
            avg_similarity = sum(s.similarity_score for s in scores) / len(scores)
            stats[str(task.id)] = round(avg_similarity * 100, 1)
        else:
            # Fallback: compare all answers on this task
            answers = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.refused == False
            ).all()
            total = 0
            aligned = 0
            for i, a in enumerate(answers):
                for b in answers[i+1:]:
                    if a.value is None or b.value is None:
                        continue
                    total += 1
                    if a.value.strip().lower() == b.value.strip().lower():
                        aligned += 1
            stats[str(task.id)] = round((aligned / total) * 100, 1) if total > 0 else 100.0
    
    return stats
