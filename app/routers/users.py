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
