"""
Misalignment detection endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from collections import defaultdict, Counter

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import MisalignmentResponse
from app.services.misalignment_cached import compute_misalignments_for_user_cached

router = APIRouter(prefix="/misalignments", tags=["misalignments"])


@router.get("", response_model=List[MisalignmentResponse])
async def get_misalignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compute misalignments between current user's perceptions and
    aligned users' self-perceptions.
    
    Returns only misalignments where similarity score is below the threshold
    (default 0.6), indicating a significant perception gap.
    
    Compares:
    - Current user's answers about aligned users & their tasks
    - Those users' self-answers on the same task/attribute
    
    Uses:
    - OpenAI embeddings for semantic similarity on text attributes (main_goal)
    - Type-specific similarity for enum, bool, int, float, date
    """
    # Use the cached misalignment service with thresholding
    misalignments = await compute_misalignments_for_user_cached(
        user_id=current_user.id,
        db=db,
        include_all=False  # Only return misalignments below threshold
    )
    
    return misalignments


@router.get("/statistics")
async def get_misalignment_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get comprehensive misalignment statistics and analytics.
    
    Returns:
    - Total misalignment count
    - Breakdown by attribute
    - Breakdown by user
    - Breakdown by severity
    - Most misaligned tasks
    - Average similarity scores
    """
    # Get all misalignments (including those above threshold for stats)
    all_misalignments = await compute_misalignments_for_user_cached(
        user_id=current_user.id,
        db=db,
        include_all=True  # Get all for statistics
    )
    
    if not all_misalignments:
        return {
            "total_count": 0,
            "by_attribute": {},
            "by_user": {},
            "by_severity": {"high": 0, "medium": 0, "low": 0},
            "by_task": {},
            "average_similarity": 1.0,
            "total_comparisons": 0
        }
    
    # Calculate statistics
    by_attribute = defaultdict(list)
    by_user = defaultdict(list)
    by_task = defaultdict(list)
    
    for m in all_misalignments:
        by_attribute[m.attribute_label].append(m.similarity_score)
        by_user[m.other_user_name].append(m.similarity_score)
        if m.task_title:
            by_task[m.task_title].append(m.similarity_score)
    
    # Severity classification
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for m in all_misalignments:
        if m.similarity_score < 0.3:
            severity_counts["high"] += 1
        elif m.similarity_score < 0.6:
            severity_counts["medium"] += 1
        else:
            severity_counts["low"] += 1
    
    # Aggregate statistics
    stats = {
        "total_count": len(all_misalignments),
        "total_comparisons": len(all_misalignments),
        "average_similarity": sum(m.similarity_score for m in all_misalignments) / len(all_misalignments),
        
        # By attribute
        "by_attribute": {
            attr: {
                "count": len(scores),
                "avg_similarity": sum(scores) / len(scores),
                "min_similarity": min(scores),
                "max_similarity": max(scores)
            }
            for attr, scores in by_attribute.items()
        },
        
        # By user
        "by_user": {
            user: {
                "count": len(scores),
                "avg_similarity": sum(scores) / len(scores),
                "min_similarity": min(scores)
            }
            for user, scores in by_user.items()
        },
        
        # By severity
        "by_severity": severity_counts,
        
        # Most misaligned tasks
        "most_misaligned_tasks": [
            {
                "task": task,
                "count": len(scores),
                "avg_similarity": sum(scores) / len(scores)
            }
            for task, scores in sorted(
                by_task.items(),
                key=lambda x: sum(x[1]) / len(x[1])
            )[:5]  # Top 5 most misaligned
        ]
    }
    
    return stats

