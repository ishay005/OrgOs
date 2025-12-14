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
