"""
Misalignment detection endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import MisalignmentResponse
from app.services.misalignment import compute_misalignments_for_user

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
    # Use the misalignment service with thresholding
    misalignments = await compute_misalignments_for_user(
        user_id=current_user.id,
        db=db,
        include_all=False  # Only return misalignments below threshold
    )
    
    return misalignments

