"""
Authentication dependency for FastAPI
"""
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Annotated

from app.database import get_db
from app.models import User


async def get_current_user(
    x_user_id: Annotated[str, Header()],
    db: Session = Depends(get_db)
) -> User:
    """
    Resolve current user from X-User-Id header.
    Returns 401 if header is missing or user not found.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    
    try:
        user_uuid = UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-User-Id format")
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

