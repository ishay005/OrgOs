"""
Tasks and ontology endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Task, AttributeDefinition, EntityType, AlignmentEdge
from app.schemas import (
    TaskCreate, TaskResponse,
    AttributeDefinitionResponse
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
attributes_router = APIRouter(tags=["attributes"])


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    include_self: bool = Query(True),
    include_aligned: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get tasks owned by current user and/or users they align with.
    """
    query = db.query(Task).filter(Task.is_active == True)
    
    # Build list of owner IDs to include
    owner_ids = []
    
    if include_self:
        owner_ids.append(current_user.id)
    
    if include_aligned:
        alignments = db.query(AlignmentEdge).filter(
            AlignmentEdge.source_user_id == current_user.id
        ).all()
        for alignment in alignments:
            owner_ids.append(alignment.target_user_id)
    
    if not owner_ids:
        return []
    
    tasks = query.filter(Task.owner_user_id.in_(owner_ids)).all()
    
    # Build response with owner names
    result = []
    for task in tasks:
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        result.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "owner_user_id": task.owner_user_id,
            "owner_name": owner.name if owner else "Unknown",
            "is_active": task.is_active,
            "created_at": task.created_at
        })
    
    return result


@router.post("", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new task owned by current user.
    """
    task = Task(
        title=task_data.title,
        description=task_data.description,
        owner_user_id=current_user.id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "owner_user_id": task.owner_user_id,
        "owner_name": current_user.name,
        "is_active": task.is_active,
        "created_at": task.created_at
    }


@attributes_router.get("/task-attributes", response_model=List[AttributeDefinitionResponse])
async def get_task_attributes(db: Session = Depends(get_db)):
    """
    Get all task attribute definitions.
    """
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    return attributes


@attributes_router.get("/user-attributes", response_model=List[AttributeDefinitionResponse])
async def get_user_attributes(db: Session = Depends(get_db)):
    """
    Get all user attribute definitions.
    """
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.USER
    ).all()
    return attributes

