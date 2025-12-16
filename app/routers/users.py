"""
User management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import time as time_type

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import (
    UserCreate, UserResponse, UserListResponse,
    OrgChartNode, OrgChartResponse
)

router = APIRouter(prefix="/users", tags=["users"])


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
    
    # Validate manager_id if provided
    manager = None
    if user_data.manager_id:
        manager = db.query(User).filter(User.id == user_data.manager_id).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager user not found")
    
    user = User(
        name=user_data.name,
        email=user_data.email,
        timezone=user_data.timezone or "UTC",
        notification_time=notification_time,
        manager_id=user_data.manager_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Enrich response with manager info
    response_data = UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        timezone=user.timezone,
        notification_time=user.notification_time,
        manager_id=user.manager_id,
        manager_name=manager.name if user.manager_id and manager else None,
        employee_count=0
    )
    
    return response_data


@router.get("", response_model=List[UserListResponse])
async def list_users(db: Session = Depends(get_db)):
    """
    Get all users (id and name only).
    """
    users = db.query(User).all()
    return users


from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class UserUpdate(BaseModel):
    """Request model for updating a user"""
    name: Optional[str] = None
    email: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    manager_id: Optional[UUID] = None


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a user's information.
    
    Permissions:
    - Users can update their own info (name, email, team, role)
    - Managers can update their employees' info
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Permission check
    can_edit = False
    
    # Users can edit themselves
    if current_user.id == user_id:
        can_edit = True
    
    # Check if current user is a manager of this user
    if not can_edit:
        check_manager_id = user.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_edit = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    if not can_edit:
        raise HTTPException(status_code=403, detail="You don't have permission to edit this user")
    
    # Update fields
    if update_data.name is not None:
        user.name = update_data.name
    
    if update_data.email is not None:
        user.email = update_data.email
    
    if update_data.team is not None:
        user.team = update_data.team
    
    if update_data.role is not None:
        user.role = update_data.role
    
    if update_data.manager_id is not None:
        # Only managers can change manager_id
        if current_user.id != user_id:
            new_manager = db.query(User).filter(User.id == update_data.manager_id).first()
            if not new_manager:
                raise HTTPException(status_code=404, detail="New manager not found")
            user.manager_id = update_data.manager_id
    
    db.commit()
    db.refresh(user)
    
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "team": user.team,
        "role": user.role,
        "manager_id": str(user.manager_id) if user.manager_id else None,
        "message": "User updated successfully"
    }


@router.get("/{user_id}/alignment-details")
async def get_user_alignment_details(user_id: str, db: Session = Depends(get_db)):
    """
    Get detailed alignment comparison for a specific user.
    Shows each attribute comparison with other users who answered about the same tasks.
    """
    from app.models import Task, AttributeAnswer, AttributeDefinition
    from uuid import UUID
    
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    comparisons = []
    total_comparisons = 0
    aligned_count = 0
    
    # Get all answers provided by this user
    user_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == uid,
        AttributeAnswer.refused == False
    ).all()
    
    for user_answer in user_answers:
        # Get task info
        task = db.query(Task).filter(Task.id == user_answer.task_id).first()
        task_title = task.title if task else "Unknown"
        
        # Get attribute info
        attr = db.query(AttributeDefinition).filter(AttributeDefinition.id == user_answer.attribute_id).first()
        attr_label = attr.label if attr else "Unknown"
        
        # Find other users who answered the same task/attribute
        other_answers = db.query(AttributeAnswer).filter(
            AttributeAnswer.task_id == user_answer.task_id,
            AttributeAnswer.attribute_id == user_answer.attribute_id,
            AttributeAnswer.answered_by_user_id != uid,
            AttributeAnswer.refused == False
        ).all()
        
        for other_answer in other_answers:
            other_user = db.query(User).filter(User.id == other_answer.answered_by_user_id).first()
            other_name = other_user.name if other_user else "Unknown"
            
            is_aligned = user_answer.value.strip().lower() == other_answer.value.strip().lower()
            total_comparisons += 1
            if is_aligned:
                aligned_count += 1
            
            comparisons.append({
                "task_id": str(user_answer.task_id),
                "task_title": task_title,
                "attribute": attr_label,
                "user_value": user_answer.value,
                "other_user": other_name,
                "other_value": other_answer.value,
                "is_aligned": is_aligned
            })
    
    overall_alignment = round((aligned_count / total_comparisons * 100)) if total_comparisons > 0 else 100
    
    return {
        "user_id": str(user_id),
        "user_name": user.name,
        "overall_alignment": overall_alignment,
        "total_comparisons": total_comparisons,
        "aligned_count": aligned_count,
        "comparisons": comparisons
    }
