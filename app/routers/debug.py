"""
Debug endpoints for testing components independently
These endpoints are for development/testing and should not be used in production.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict

from app.database import get_db
from app.auth import get_current_user
from app.models import User, AttributeDefinition, EntityType
from app.schemas import (
    AttributeDefinitionResponse, QuestionResponse,
    SimilarityDebugRequest, SimilarityDebugResponse,
    MisalignmentResponse
)
from app.services.similarity import compute_similarity, AttributeType
from app.services.misalignment import compute_misalignments_for_user
from app.routers.questions import get_pending_questions

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/attributes", response_model=Dict[str, List[AttributeDefinitionResponse]])
async def get_all_attributes(db: Session = Depends(get_db)):
    """
    [DEBUG] Get all AttributeDefinitions grouped by entity_type.
    """
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    user_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.USER
    ).all()
    
    return {
        "task": task_attributes,
        "user": user_attributes
    }


@router.get("/questions/raw", response_model=List[QuestionResponse])
async def get_raw_questions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [DEBUG] Get raw question stubs with LLM-generated text.
    Uses the same selection logic as /questions/next but returns more questions.
    """
    questions = await get_pending_questions(current_user, db, max_questions=50)
    return questions


@router.post("/similarity", response_model=SimilarityDebugResponse)
async def test_similarity(request: SimilarityDebugRequest):
    """
    [DEBUG] Test similarity computation between two values.
    Calls the similarity module and returns the score.
    
    This uses the full similarity engine including:
    - OpenAI embeddings for string types
    - Distance-based similarity for numeric types
    - Exact matching for enum/bool types
    
    Useful for testing:
    - Text embedding behavior (especially for main_goal)
    - Numeric similarity formulas
    - Edge cases where values look similar but score differently
    """
    # Convert string type to AttributeType enum
    try:
        attr_type = AttributeType(request.attribute_type)
    except ValueError:
        # Fallback to string if invalid type
        attr_type = AttributeType.string
    
    similarity_score = await compute_similarity(
        value_a=request.value_a,
        value_b=request.value_b,
        attribute_type=attr_type,
        allowed_values=request.allowed_values
    )
    
    return {"similarity_score": similarity_score}


@router.get("/misalignments/raw", response_model=List[MisalignmentResponse])
async def get_raw_misalignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [DEBUG] Get all misalignment pairs with raw scores, without thresholding.
    
    Returns ALL answer pairs where both users have answered,
    regardless of similarity score. This helps with:
    - Tuning the misalignment threshold
    - Understanding similarity score distribution
    - Finding edge cases where similar answers get low scores
    - Testing text embedding behavior on real data
    
    Unlike GET /misalignments, this returns everything, not just low scores.
    """
    # Use the misalignment service WITHOUT thresholding
    misalignments = await compute_misalignments_for_user(
        user_id=current_user.id,
        db=db,
        include_all=True  # Return all pairs, no threshold filtering
    )
    
    return misalignments

