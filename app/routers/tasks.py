"""
Tasks and ontology endpoints
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Task, AttributeDefinition, EntityType, AlignmentEdge, TaskDependency
from app.schemas import (
    TaskCreate, TaskResponse,
    AttributeDefinitionResponse, TaskGraphNode
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
            "parent_id": task.parent_id,
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
    Supports parent-child relationships and dependencies.
    """
    # Validate parent exists if provided
    if task_data.parent_id:
        parent_task = db.query(Task).filter(Task.id == task_data.parent_id).first()
        if not parent_task:
            raise HTTPException(status_code=400, detail=f"Parent task {task_data.parent_id} does not exist")
    
    # Create the main task
    task = Task(
        title=task_data.title,
        description=task_data.description,
        owner_user_id=current_user.id,
        parent_id=task_data.parent_id
    )
    db.add(task)
    db.flush()  # Get the ID without committing
    
    # Handle children: create child tasks if they don't exist
    if task_data.children:
        for child_title in task_data.children:
            # Check if a task with this title already exists for this user
            existing_child = db.query(Task).filter(
                Task.title == child_title,
                Task.owner_user_id == current_user.id,
                Task.is_active == True
            ).first()
            
            if not existing_child:
                # Create new child task
                child_task = Task(
                    title=child_title,
                    description=f"Child of: {task.title}",
                    owner_user_id=current_user.id,
                    parent_id=task.id
                )
                db.add(child_task)
            else:
                # Update existing task to be a child of this task
                existing_child.parent_id = task.id
    
    # Handle dependencies
    if task_data.dependencies:
        for dep_id in task_data.dependencies:
            # Verify dependency task exists
            dep_task = db.query(Task).filter(Task.id == dep_id).first()
            if not dep_task:
                raise HTTPException(status_code=400, detail=f"Dependency task {dep_id} does not exist")
            
            # Create dependency relationship
            dependency = TaskDependency(
                task_id=task.id,
                depends_on_task_id=dep_id
            )
            db.add(dependency)
    
    db.commit()
    db.refresh(task)
    
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "owner_user_id": task.owner_user_id,
        "owner_name": current_user.name,
        "parent_id": task.parent_id,
        "is_active": task.is_active,
        "created_at": task.created_at
    }


@attributes_router.get("/task-attributes", response_model=List[AttributeDefinitionResponse])
async def get_task_attributes(
    db: Session = Depends(get_db)
):
    """
    Get all task attribute definitions.
    No authentication required - this is schema information.
    """
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    return attributes


@attributes_router.get("/user-attributes", response_model=List[AttributeDefinitionResponse])
async def get_user_attributes(
    db: Session = Depends(get_db)
):
    """
    Get all user attribute definitions.
    No authentication required - this is schema information.
    """
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.USER
    ).all()
    return attributes


@router.get("/graph", response_model=List[TaskGraphNode])
async def get_task_graph(
    db: Session = Depends(get_db)
):
    """
    Get all tasks with their relationships for graph visualization.
    Returns tasks with parent, children, and dependency information.
    """
    tasks = db.query(Task).filter(Task.is_active == True).all()
    
    result = []
    for task in tasks:
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        
        # Get children IDs
        children_ids = [child.id for child in task.children]
        
        # Get dependency IDs
        dependencies = db.query(TaskDependency).filter(
            TaskDependency.task_id == task.id
        ).all()
        dependency_ids = [dep.depends_on_task_id for dep in dependencies]
        
        result.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "owner_name": owner.name if owner else "Unknown",
            "parent_id": task.parent_id,
            "children_ids": children_ids,
            "dependency_ids": dependency_ids
        })
    
    return result


@router.get("/graph/with-attributes")
async def get_task_graph_with_attributes(
    db: Session = Depends(get_db)
):
    """
    Get all tasks with their relationships AND attribute answers for filtering.
    Returns tasks with parent, children, dependency info, plus all attribute values.
    """
    from app.models import AttributeAnswer, AttributeDefinition, EntityType
    
    tasks = db.query(Task).filter(Task.is_active == True).all()
    
    # Get all task attributes
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    result = []
    for task in tasks:
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        
        # Get children IDs
        children_ids = [child.id for child in task.children]
        
        # Get dependency IDs
        dependencies = db.query(TaskDependency).filter(
            TaskDependency.task_id == task.id
        ).all()
        dependency_ids = [dep.depends_on_task_id for dep in dependencies]
        
        # Get attribute answers for this task (self-answers by owner)
        attributes = {}
        for attr in task_attributes:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.answered_by_user_id == task.owner_user_id,
                AttributeAnswer.target_user_id == task.owner_user_id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).order_by(AttributeAnswer.created_at.desc()).first()
            
            if answer:
                attributes[attr.name] = {
                    "value": answer.value,
                    "label": attr.label,
                    "type": attr.type.value
                }
        
        result.append({
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "owner_name": owner.name if owner else "Unknown",
            "owner_id": str(task.owner_user_id),
            "parent_id": str(task.parent_id) if task.parent_id else None,
            "children_ids": [str(cid) for cid in children_ids],
            "dependency_ids": [str(did) for did in dependency_ids],
            "attributes": attributes
        })
    
    return result


@router.get("/{task_id}/answers")
async def get_task_answers(
    task_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get all answers about a specific task from all users.
    Returns answers grouped by attribute and user for easy comparison.
    """
    from app.models import AttributeAnswer, AttributeDefinition, EntityType
    
    # Get the task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    
    # Get all task attributes
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    # Get all answers for this task
    all_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.task_id == task_id,
        AttributeAnswer.refused == False
    ).all()
    
    # Organize by attribute, then by user
    answers_by_attribute = {}
    
    for attr in task_attributes:
        # Get all answers for this attribute
        attr_answers = [a for a in all_answers if a.attribute_id == attr.id]
        
        if attr_answers:
            user_answers = []
            for answer in attr_answers:
                answering_user = db.query(User).filter(User.id == answer.answered_by_user_id).first()
                user_answers.append({
                    "user_id": str(answer.answered_by_user_id),
                    "user_name": answering_user.name if answering_user else "Unknown",
                    "value": answer.value,
                    "answered_at": answer.created_at.isoformat(),
                    "is_owner": answer.answered_by_user_id == task.owner_user_id
                })
            
            answers_by_attribute[attr.name] = {
                "attribute_id": str(attr.id),
                "attribute_label": attr.label,
                "attribute_type": attr.type.value,
                "allowed_values": attr.allowed_values,
                "answers": user_answers
            }
    
    return {
        "task_id": str(task.id),
        "task_title": task.title,
        "task_description": task.description,
        "owner_name": owner.name if owner else "Unknown",
        "owner_id": str(task.owner_user_id),
        "answers_by_attribute": answers_by_attribute
    }

