"""
User and alignment management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import time as time_type

from app.database import get_db
from app.auth import get_current_user
from app.models import User, AlignmentEdge
from app.schemas import (
    UserCreate, UserResponse, UserListResponse,
    AlignmentCreate, AlignmentResponse
)

router = APIRouter(prefix="/users", tags=["users"])
alignment_router = APIRouter(prefix="/alignments", tags=["alignments"])


@router.post("", response_model=UserResponse)
async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user.
    Returns the user ID which the client should store and reuse in X-User-Id header.
    """
    # Parse notification_time string to time object
    notification_time = time_type(10, 0)  # default
    if user_data.notification_time:
        try:
            hour, minute = map(int, user_data.notification_time.split(":"))
            notification_time = time_type(hour, minute)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid notification_time format. Use HH:MM")
    
    user = User(
        name=user_data.name,
        email=user_data.email,
        timezone=user_data.timezone or "UTC",
        notification_time=notification_time
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user


@router.get("", response_model=List[UserListResponse])
async def list_users(db: Session = Depends(get_db)):
    """
    Get all users (id and name only).
    """
    users = db.query(User).all()
    return users


@alignment_router.get("", response_model=List[AlignmentResponse])
async def get_alignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get alignment list for current user.
    Returns list of users the current user aligns with.
    """
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == current_user.id
    ).all()
    
    result = []
    for alignment in alignments:
        target_user = db.query(User).filter(User.id == alignment.target_user_id).first()
        if target_user:
            result.append({
                "target_user_id": target_user.id,
                "target_user_name": target_user.name
            })
    
    return result


@alignment_router.post("", response_model=List[AlignmentResponse])
async def update_alignment(
    alignment_data: AlignmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create or delete an alignment edge.
    If align=true: create edge (idempotent)
    If align=false: delete edge
    Returns updated alignment list.
    """
    target_user = db.query(User).filter(User.id == alignment_data.target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    existing = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == current_user.id,
        AlignmentEdge.target_user_id == alignment_data.target_user_id
    ).first()
    
    if alignment_data.align:
        # Create edge if doesn't exist
        if not existing:
            edge = AlignmentEdge(
                source_user_id=current_user.id,
                target_user_id=alignment_data.target_user_id
            )
            db.add(edge)
            db.commit()
    else:
        # Delete edge if exists
        if existing:
            db.delete(existing)
            db.commit()
    
    # Return updated list
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == current_user.id
    ).all()
    
    result = []
    for alignment in alignments:
        target_user = db.query(User).filter(User.id == alignment.target_user_id).first()
        if target_user:
            result.append({
                "target_user_id": target_user.id,
                "target_user_name": target_user.name
            })
    
    return result

