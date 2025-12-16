"""
Tasks and ontology endpoints
"""
import html
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user


def _sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS attacks."""
    if not text:
        return text
    return html.escape(text)
from app.models import (
    User, Task, AttributeDefinition, EntityType, TaskDependency, TaskRelevantUser,
    TaskState, TaskAlias, TaskMergeProposal, MergeProposalStatus,
    TaskDependencyV2, DependencyStatus, AlternativeDependencyProposal, AlternativeDepStatus,
    PendingDecision, PendingDecisionType
)
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
        # Get task owners from tasks where current user is marked as relevant
        relevant_entries = db.query(TaskRelevantUser).filter(
            TaskRelevantUser.user_id == current_user.id
        ).all()
        for entry in relevant_entries:
            task = db.query(Task).filter(Task.id == entry.task_id).first()
            if task and task.owner_user_id not in owner_ids:
                owner_ids.append(task.owner_user_id)
    
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
    Create a new task.
    If owner_user_id is provided and different from current user:
      - Task state is DRAFT
      - A PendingDecision is created for the owner to accept/reject
    Otherwise:
      - Task state is ACTIVE
    Supports parent-child relationships and dependencies.
    """
    # Validate parent exists if provided
    if task_data.parent_id:
        parent_task = db.query(Task).filter(Task.id == task_data.parent_id).first()
        if not parent_task:
            raise HTTPException(status_code=400, detail=f"Parent task {task_data.parent_id} does not exist")
    
    # Determine owner: use provided owner_user_id or default to current user
    owner_user_id = task_data.owner_user_id if task_data.owner_user_id else current_user.id
    
    # Validate owner exists
    owner = db.query(User).filter(User.id == owner_user_id).first()
    if not owner:
        raise HTTPException(status_code=400, detail=f"Owner user {owner_user_id} does not exist")
    
    # Determine if this is a task created for someone else
    is_for_someone_else = owner_user_id != current_user.id
    
    # Set initial state based on ownership
    initial_state = TaskState.DRAFT if is_for_someone_else else TaskState.ACTIVE
    
    # Sanitize inputs to prevent XSS
    safe_title = _sanitize_input(task_data.title)
    safe_description = _sanitize_input(task_data.description) if task_data.description else None
    
    # Create the main task
    task = Task(
        title=safe_title,
        description=safe_description,
        owner_user_id=owner_user_id,
        created_by_user_id=current_user.id,
        parent_id=task_data.parent_id,
        state=initial_state,
        state_changed_at=datetime.utcnow()
    )
    db.add(task)
    db.flush()  # Get the ID without committing
    
    # If task is created for someone else, create a PendingDecision
    if is_for_someone_else:
        pending_decision = PendingDecision(
            user_id=owner_user_id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=task.id,
            description=f"{current_user.name} suggested task '{task.title}' for you. Accept or reject?"
        )
        db.add(pending_decision)
    
    # Handle children: create child tasks if they don't exist
    if task_data.children:
        for child_title in task_data.children:
            # Check if a task with this title already exists for this user
            existing_child = db.query(Task).filter(
                Task.title == child_title,
                Task.owner_user_id == owner_user_id,
                Task.is_active == True
            ).first()
            
            if not existing_child:
                # Create new child task (same state as parent)
                child_task = Task(
                    title=child_title,
                    description=f"Child of: {task.title}",
                    owner_user_id=owner_user_id,
                    created_by_user_id=current_user.id,
                    parent_id=task.id,
                    state=initial_state,
                    state_changed_at=datetime.utcnow()
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
    
    # Auto-populate relevant users
    try:
        from populate_relevant_users import update_relevant_users_for_task
        update_relevant_users_for_task(db, task.id)
    except Exception as e:
        # Don't fail task creation if this fails
        import logging
        logging.getLogger(__name__).warning(f"Could not auto-populate relevant users: {e}")
    
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "owner_user_id": task.owner_user_id,
        "owner_name": owner.name,
        "parent_id": task.parent_id,
        "is_active": task.is_active,
        "created_at": task.created_at
    }


from pydantic import BaseModel
from typing import Optional

from pydantic import Field
from typing import Union, Literal

# Sentinel for "clear this field" vs "not provided"
UNSET = object()

class TaskUpdate(BaseModel):
    """Request model for updating a task"""
    title: Optional[str] = None
    description: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    parent_id: Optional[Union[UUID, Literal[""]]] = None  # "" means clear, None means not set, UUID means set
    is_active: Optional[bool] = None


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    update_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a task's basic information.
    
    Permissions:
    - Task owner can update everything
    - Manager of task owner can update everything
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    can_edit = False
    
    # Owner can edit
    if current_user.id == task.owner_user_id:
        can_edit = True
    
    # Creator can edit when task is REJECTED (to resubmit)
    if task.state == TaskState.REJECTED and current_user.id == task.created_by_user_id:
        can_edit = True
    
    # Manager of owner can edit
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    if owner and owner.manager_id == current_user.id:
        can_edit = True
    
    # Check if current user is any level manager of the owner
    if not can_edit and owner:
        check_manager_id = owner.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_edit = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    if not can_edit:
        raise HTTPException(status_code=403, detail="You don't have permission to edit this task")
    
    # Update fields
    if update_data.title is not None:
        task.title = update_data.title
    
    if update_data.description is not None:
        task.description = update_data.description
    
    if update_data.is_active is not None:
        task.is_active = update_data.is_active
    
    # Update owner (with validation and double consent)
    if update_data.owner_user_id is not None:
        new_owner = db.query(User).filter(User.id == update_data.owner_user_id).first()
        if not new_owner:
            raise HTTPException(status_code=404, detail="New owner not found")
        
        old_owner_id = task.owner_user_id
        new_owner_id = update_data.owner_user_id
        
        # Check if owner is actually changing
        if new_owner_id != old_owner_id:
            # Update the owner
            task.owner_user_id = new_owner_id
            
            # State logic:
            # - If creator becomes owner => ACTIVE
            # - Else => DRAFT pending new owner's acceptance
            db.query(PendingDecision).filter(
                PendingDecision.entity_type == "task",
                PendingDecision.entity_id == task.id,
                PendingDecision.is_resolved == False
            ).delete()
            
            if task.created_by_user_id == new_owner_id:
                task.state = TaskState.ACTIVE
                task.state_changed_at = datetime.utcnow()
                task.state_reason = f"Creator reassigned to self"
                task.is_active = True
            else:
                task.state = TaskState.DRAFT
                task.state_changed_at = datetime.utcnow()
                task.state_reason = f"Ownership transferred from {current_user.name}"
                task.is_active = True
                
                # Create new pending decision for the new owner
                pending_decision = PendingDecision(
                    user_id=new_owner_id,
                    decision_type=PendingDecisionType.TASK_ACCEPTANCE,
                    entity_type="task",
                    entity_id=task.id,
                    description=f"{current_user.name} transferred task '{task.title}' to you. Accept or reject?"
                )
                db.add(pending_decision)

    # If the task was REJECTED and the creator edits (reopens), ensure state aligns with owner
    if task.state == TaskState.REJECTED and current_user.id == task.created_by_user_id:
        # Clear existing pending decisions for creator (they acted)
        db.query(PendingDecision).filter(
            PendingDecision.entity_type == "task",
            PendingDecision.entity_id == task.id,
            PendingDecision.is_resolved == False
        ).delete()
        
        if task.owner_user_id == task.created_by_user_id:
            task.state = TaskState.ACTIVE
            task.state_changed_at = datetime.utcnow()
            task.state_reason = "Creator reassigned to self"
            task.is_active = True
        else:
            task.state = TaskState.DRAFT
            task.state_changed_at = datetime.utcnow()
            task.state_reason = "Resubmitted after rejection"
            task.is_active = True
            
            # Create pending decision for the (new) owner
            pending_decision = PendingDecision(
                user_id=task.owner_user_id,
                decision_type=PendingDecisionType.TASK_ACCEPTANCE,
                entity_type="task",
                entity_id=task.id,
                description=f"Task '{task.title}' was resubmitted. Accept or reject?"
            )
            db.add(pending_decision)
            
            # Recalculate relevant users when owner changes
            try:
                from populate_relevant_users import update_relevant_users_for_task
                update_relevant_users_for_task(db, task.id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not update relevant users: {e}")
    
    # Update parent (with validation)
    # parent_id can be: None (not provided), "" (clear/set to null), or UUID (set to new parent)
    if update_data.parent_id is not None:
        if update_data.parent_id == "" or update_data.parent_id == "null":
            # Clear parent
            task.parent_id = None
        else:
            # Set new parent
            new_parent_id = update_data.parent_id if isinstance(update_data.parent_id, UUID) else UUID(str(update_data.parent_id))
            if new_parent_id == task_id:
                raise HTTPException(status_code=400, detail="Task cannot be its own parent")
            parent = db.query(Task).filter(Task.id == new_parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent task not found")
            task.parent_id = new_parent_id
    
    db.commit()
    db.refresh(task)
    
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "owner_user_id": task.owner_user_id,
        "owner_name": owner.name if owner else "Unknown",
        "parent_id": task.parent_id,
        "is_active": task.is_active,
        "created_at": task.created_at
    }


@router.delete("/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete/archive a task.
    
    Permissions:
    - Task owner can delete their own task
    - Manager can delete tasks owned by their employees (direct or indirect)
    - Task creator can archive a REJECTED task they created
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    can_delete = False
    
    # Owner can delete
    if current_user.id == task.owner_user_id:
        can_delete = True
    
    # Creator can archive rejected task
    if task.state == TaskState.REJECTED and current_user.id == task.created_by_user_id:
        can_delete = True
    
    # Check if current user is a manager of the task owner
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    if owner:
        check_manager_id = owner.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_delete = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    if not can_delete:
        raise HTTPException(status_code=403, detail="You don't have permission to delete this task")
    
    # Archive instead of raw is_active toggle
    task.state = TaskState.ARCHIVED
    task.state_changed_at = datetime.utcnow()
    task.state_reason = "Archived"
    task.is_active = False
    
    # Resolve pending decisions for this task
    from app.services.state_machines import resolve_pending_decision
    resolve_pending_decision(db, "task", task.id, "archived")
    
    # Also remove from relevant users, dependencies, etc.
    db.query(TaskRelevantUser).filter(TaskRelevantUser.task_id == task_id).delete()
    db.query(TaskDependency).filter(
        (TaskDependency.task_id == task_id) | (TaskDependency.depends_on_task_id == task_id)
    ).delete()
    
    db.commit()
    
    return {"message": "Task deleted successfully", "task_id": str(task_id)}


@router.get("/{task_id}/full-details")
async def get_task_full_details(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive task details including:
    - Task state (DRAFT, ACTIVE, ARCHIVED)
    - Owner and Creator info
    - Aliases (from merged tasks)
    - Dependencies with state machine status (PROPOSED, CONFIRMED, REJECTED)
    - Pending proposals (merge, dependency alternatives)
    - Attribute answers from all users
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get owner / creator / all users for edit dialogs
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    creator = db.query(User).filter(User.id == task.created_by_user_id).first() if task.created_by_user_id else None
    all_users = db.query(User).all()
    
    # Get task state
    task_state = task.state.value if hasattr(task, 'state') and task.state else "ACTIVE"
    
    # Get aliases (for merged tasks)
    aliases = []
    try:
        alias_entries = db.query(TaskAlias).filter(TaskAlias.canonical_task_id == task_id).all()
        for alias in alias_entries:
            alias_creator = db.query(User).filter(User.id == alias.alias_created_by_user_id).first()
            aliases.append({
                "id": str(alias.id),
                "title": alias.alias_title,
                "creator_name": alias_creator.name if alias_creator else "Unknown",
                "merged_from_task_id": str(alias.merged_from_task_id) if alias.merged_from_task_id else None
            })
    except Exception:
        pass
    
    # Get V2 dependencies with status
    dependencies_v2 = []
    try:
        # Outgoing (this task depends on)
        outgoing = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == task_id,
            TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
        ).all()
        for dep in outgoing:
            upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
            upstream_owner = db.query(User).filter(User.id == upstream.owner_user_id).first() if upstream else None
            dependencies_v2.append({
                "dependency_id": str(dep.id),
                "direction": "outgoing",
                "task_id": str(dep.upstream_task_id),
                "task_title": upstream.title if upstream else "Unknown",
                "task_owner": upstream_owner.name if upstream_owner else "Unknown",
                "status": dep.status.value,
                "created_by": None,  # Add later if needed
                "rejected_reason": dep.rejected_reason
            })
        
        # Incoming (other tasks depend on this)
        incoming = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.upstream_task_id == task_id,
            TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
        ).all()
        for dep in incoming:
            downstream = db.query(Task).filter(Task.id == dep.downstream_task_id).first()
            downstream_owner = db.query(User).filter(User.id == downstream.owner_user_id).first() if downstream else None
            dependencies_v2.append({
                "dependency_id": str(dep.id),
                "direction": "incoming",
                "task_id": str(dep.downstream_task_id),
                "task_title": downstream.title if downstream else "Unknown",
                "task_owner": downstream_owner.name if downstream_owner else "Unknown",
                "status": dep.status.value,
                "created_by": None,
                "rejected_reason": dep.rejected_reason
            })
    except Exception:
        pass
    
    # Get pending merge proposals involving this task
    merge_proposals = []
    try:
        proposals = db.query(TaskMergeProposal).filter(
            ((TaskMergeProposal.from_task_id == task_id) | (TaskMergeProposal.to_task_id == task_id)),
            TaskMergeProposal.status == MergeProposalStatus.PROPOSED
        ).all()
        for p in proposals:
            from_task = db.query(Task).filter(Task.id == p.from_task_id).first()
            to_task = db.query(Task).filter(Task.id == p.to_task_id).first()
            proposer = db.query(User).filter(User.id == p.proposed_by_user_id).first()
            merge_proposals.append({
                "id": str(p.id),
                "from_task_id": str(p.from_task_id),
                "from_task_title": from_task.title if from_task else "Unknown",
                "to_task_id": str(p.to_task_id),
                "to_task_title": to_task.title if to_task else "Unknown",
                "proposed_by": proposer.name if proposer else "Unknown",
                "reason": p.proposal_reason,
                "status": p.status.value
            })
    except Exception:
        pass
    
    # Get alternative dependency proposals
    alt_dep_proposals = []
    try:
        alt_proposals = db.query(AlternativeDependencyProposal).filter(
            ((AlternativeDependencyProposal.downstream_task_id == task_id) |
             (AlternativeDependencyProposal.original_upstream_task_id == task_id) |
             (AlternativeDependencyProposal.suggested_upstream_task_id == task_id)),
            AlternativeDependencyProposal.status == AlternativeDepStatus.PROPOSED
        ).all()
        for ap in alt_proposals:
            downstream = db.query(Task).filter(Task.id == ap.downstream_task_id).first()
            orig_upstream = db.query(Task).filter(Task.id == ap.original_upstream_task_id).first()
            suggested = db.query(Task).filter(Task.id == ap.suggested_upstream_task_id).first()
            proposer = db.query(User).filter(User.id == ap.proposed_by_user_id).first()
            alt_dep_proposals.append({
                "id": str(ap.id),
                "downstream_task": downstream.title if downstream else "Unknown",
                "original_upstream": orig_upstream.title if orig_upstream else "Unknown",
                "suggested_upstream": suggested.title if suggested else "Unknown",
                "proposed_by": proposer.name if proposer else "Unknown",
                "reason": ap.proposal_reason,
                "status": ap.status.value
            })
    except Exception:
        pass
    
    # Get parent
    parent = None
    if task.parent_id:
        parent_task = db.query(Task).filter(Task.id == task.parent_id).first()
        if parent_task:
            parent_owner = db.query(User).filter(User.id == parent_task.owner_user_id).first()
            parent = {
                "id": str(parent_task.id),
                "title": parent_task.title,
                "owner_name": parent_owner.name if parent_owner else "Unknown"
            }
    
    # Get children
    children = []
    if hasattr(task, 'children') and task.children:
        for child in task.children:
            if child.is_active:
                child_owner = db.query(User).filter(User.id == child.owner_user_id).first()
                children.append({
                    "id": str(child.id),
                    "title": child.title,
                    "owner_name": child_owner.name if child_owner else "Unknown",
                    "state": child.state.value if hasattr(child, 'state') and child.state else "ACTIVE"
                })
    
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "state": task_state,
        "state_reason": task.state_reason if hasattr(task, 'state_reason') else None,
        "state_changed_at": task.state_changed_at.isoformat() if hasattr(task, 'state_changed_at') and task.state_changed_at else None,
        "owner": {
            "id": str(owner.id) if owner else None,
            "name": owner.name if owner else "Unknown"
        },
        "owner_id": str(task.owner_user_id) if task.owner_user_id else None,
        "owner_user_id": str(task.owner_user_id) if task.owner_user_id else None,
        "creator": {
            "id": str(creator.id) if creator else None,
            "name": creator.name if creator else None
        } if creator else None,
        "parent": parent,
        "children": children,
        "is_active": task.is_active,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "aliases": aliases,
        "dependencies_v2": dependencies_v2,
        "merge_proposals": merge_proposals,
        "alt_dependency_proposals": alt_dep_proposals,
        "all_users": [
            {"id": str(u.id), "name": u.name}
            for u in all_users
        ]
    }


@router.get("/{task_id}/dependencies")
async def get_task_dependencies(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all dependencies for a task (tasks this task depends on)."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    deps = db.query(TaskDependency).filter(TaskDependency.task_id == task_id).all()
    
    result = []
    for dep in deps:
        dep_task = db.query(Task).filter(Task.id == dep.depends_on_task_id).first()
        if dep_task:
            owner = db.query(User).filter(User.id == dep_task.owner_user_id).first()
            result.append({
                "dependency_id": str(dep.id),
                "task_id": str(dep_task.id),
                "task_title": dep_task.title,
                "owner_name": owner.name if owner else "Unknown"
            })
    
    return result


@router.post("/{task_id}/dependencies/{depends_on_task_id}")
async def add_task_dependency(
    task_id: UUID,
    depends_on_task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a dependency to a task.
    
    Permissions:
    - Task owner can add dependencies to their task
    - Manager can add dependencies to tasks owned by their employees
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    depends_on_task = db.query(Task).filter(Task.id == depends_on_task_id).first()
    if not depends_on_task:
        raise HTTPException(status_code=404, detail="Dependency task not found")
    
    if task_id == depends_on_task_id:
        raise HTTPException(status_code=400, detail="Task cannot depend on itself")
    
    # Permission check (same as edit)
    can_edit = False
    
    if current_user.id == task.owner_user_id:
        can_edit = True
    
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    if owner:
        check_manager_id = owner.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_edit = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    if not can_edit:
        raise HTTPException(status_code=403, detail="You don't have permission to modify this task's dependencies")
    
    # Check if dependency already exists
    existing = db.query(TaskDependency).filter(
        TaskDependency.task_id == task_id,
        TaskDependency.depends_on_task_id == depends_on_task_id
    ).first()
    
    if existing:
        return {"message": "Dependency already exists", "task_id": str(task_id), "depends_on": str(depends_on_task_id)}
    
    # Create dependency
    dep = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_task_id)
    db.add(dep)
    
    # Update relevant users since dependencies changed
    try:
        from populate_relevant_users import update_relevant_users_for_task
        update_relevant_users_for_task(db, task_id)
        update_relevant_users_for_task(db, depends_on_task_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not update relevant users: {e}")
    
    db.commit()
    
    return {"message": "Dependency added", "task_id": str(task_id), "depends_on": str(depends_on_task_id)}


@router.delete("/{task_id}/dependencies/{depends_on_task_id}")
async def remove_task_dependency(
    task_id: UUID,
    depends_on_task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a dependency from a task.
    
    Permissions:
    - Task owner can remove dependencies from their task
    - Manager can remove dependencies from tasks owned by their employees
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check (same as edit)
    can_edit = False
    
    if current_user.id == task.owner_user_id:
        can_edit = True
    
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    if owner:
        check_manager_id = owner.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_edit = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    if not can_edit:
        raise HTTPException(status_code=403, detail="You don't have permission to modify this task's dependencies")
    
    # Find and delete dependency
    dep = db.query(TaskDependency).filter(
        TaskDependency.task_id == task_id,
        TaskDependency.depends_on_task_id == depends_on_task_id
    ).first()
    
    if not dep:
        raise HTTPException(status_code=404, detail="Dependency not found")
    
    db.delete(dep)
    
    # Update relevant users since dependencies changed
    try:
        from populate_relevant_users import update_relevant_users_for_task
        update_relevant_users_for_task(db, task_id)
        update_relevant_users_for_task(db, depends_on_task_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not update relevant users: {e}")
    
    db.commit()
    
    return {"message": "Dependency removed", "task_id": str(task_id), "removed": str(depends_on_task_id)}


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
        
        # Get relevant users
        relevant_users = db.query(TaskRelevantUser).filter(TaskRelevantUser.task_id == task.id).all()
        relevant_user_ids = [str(r.user_id) for r in relevant_users]
        relevant_user_names = [r.user.name for r in relevant_users if r.user]
        
        result.append({
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "owner_name": owner.name if owner else "Unknown",
            "owner_id": str(task.owner_user_id),
            "parent_id": str(task.parent_id) if task.parent_id else None,
            "children_ids": [str(cid) for cid in children_ids],
            "dependency_ids": [str(did) for did in dependency_ids],
            "attributes": attributes,
            "relevant_user_ids": relevant_user_ids,
            "relevant_user_names": relevant_user_names,
            "state": task.state.value if task.state else "ACTIVE",
            "created_by_user_id": str(task.created_by_user_id) if task.created_by_user_id else None
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
    
    # Get parent info
    parent_info = None
    if task.parent_id:
        parent_task = db.query(Task).filter(Task.id == task.parent_id).first()
        if parent_task:
            parent_owner = db.query(User).filter(User.id == parent_task.owner_user_id).first()
            parent_info = {
                "id": str(parent_task.id),
                "title": parent_task.title,
                "owner_name": parent_owner.name if parent_owner else "Unknown"
            }
    
    # Get children info
    children_info = []
    for child in task.children:
        if child.is_active:
            child_owner = db.query(User).filter(User.id == child.owner_user_id).first()
            children_info.append({
                "id": str(child.id),
                "title": child.title,
                "owner_name": child_owner.name if child_owner else "Unknown"
            })
    
    return {
        "task_id": str(task.id),
        "task_title": task.title,
        "task_description": task.description,
        "owner_name": owner.name if owner else "Unknown",
        "owner_id": str(task.owner_user_id),
        "parent": parent_info,
        "children": children_info,
        "answers_by_attribute": answers_by_attribute
    }


@router.get("/{task_id}/permissions")
async def get_task_permissions(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's permissions for editing a task.
    
    Returns what the user can edit:
    - can_edit_task: can edit title, description, owner, parent
    - can_edit_own_perception: can edit their own perception answers
    - can_manage_all_relevant: can add/remove any user from relevant list
    - can_manage_self_relevant: can add/remove self from relevant list
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    
    # Check if current user can edit the task
    can_edit_task = False
    
    # Owner can edit
    if current_user.id == task.owner_user_id:
        can_edit_task = True
    
    # Check if current user is any level manager of the owner
    if owner:
        check_manager_id = owner.manager_id
        while check_manager_id:
            if check_manager_id == current_user.id:
                can_edit_task = True
                break
            manager = db.query(User).filter(User.id == check_manager_id).first()
            check_manager_id = manager.manager_id if manager else None
    
    # Everyone can edit their own perception
    can_edit_own_perception = True
    
    # Owner and managers can manage all relevant users
    can_manage_all_relevant = can_edit_task
    
    # Everyone can add/remove themselves from relevant
    can_manage_self_relevant = True
    
    # Check if current user is in the relevant list
    is_relevant = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.task_id == task_id,
        TaskRelevantUser.user_id == current_user.id
    ).first() is not None
    
    # Can delete task (same rules as edit)
    can_delete = can_edit_task
    
    # Can manage dependencies (same rules as edit)
    can_manage_dependencies = can_edit_task
    
    return {
        "task_id": str(task_id),
        "can_edit_task": can_edit_task,
        "can_delete": can_delete,
        "can_manage_dependencies": can_manage_dependencies,
        "can_edit_own_perception": can_edit_own_perception,
        "can_manage_all_relevant": can_manage_all_relevant,
        "can_manage_self_relevant": can_manage_self_relevant,
        "is_owner": current_user.id == task.owner_user_id,
        "is_relevant": is_relevant
    }


@router.get("/{task_id}/relevant-users")
async def get_relevant_users(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of users who need to be aligned on this task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    relevant = db.query(TaskRelevantUser).filter(TaskRelevantUser.task_id == task_id).all()
    
    return [{
        "user_id": str(r.user_id),
        "user_name": r.user.name if r.user else "Unknown",
        "added_by": r.added_by.name if r.added_by else "Auto",
        "added_at": r.created_at.isoformat()
    } for r in relevant]


def _is_manager_of(db: Session, manager_id: UUID, employee_id: UUID) -> bool:
    """Check if manager_id is a manager of employee_id (direct or indirect)."""
    current = db.query(User).filter(User.id == employee_id).first()
    while current and current.manager_id:
        if current.manager_id == manager_id:
            return True
        current = db.query(User).filter(User.id == current.manager_id).first()
    return False


def _can_modify_relevant_user(db: Session, current_user: User, task: Task, target_user_id: UUID) -> bool:
    """
    Check if current_user can add/remove target_user to/from task's relevant list.
    
    Rules:
    - Anyone can register/unregister THEMSELVES
    - Task OWNER can register/unregister ANYONE
    - MANAGER can register/unregister their employees (direct or indirect)
    """
    # Self-registration: anyone can add/remove themselves
    if current_user.id == target_user_id:
        return True
    
    # Task owner can manage anyone
    if task.owner_user_id == current_user.id:
        return True
    
    # Manager can manage their employees
    if _is_manager_of(db, current_user.id, target_user_id):
        return True
    
    return False


@router.post("/{task_id}/relevant-users/{user_id}")
async def add_relevant_user(
    task_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a user to the relevant users list for a task.
    
    Permissions:
    - Anyone can add THEMSELVES to any task
    - Task OWNER can add ANYONE
    - MANAGER can add their employees (direct or indirect)
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Permission check
    if not _can_modify_relevant_user(db, current_user, task, user_id):
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. You can only add yourself, or you must be the task owner or a manager of the target user."
        )
    
    # Check if already exists
    existing = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.task_id == task_id,
        TaskRelevantUser.user_id == user_id
    ).first()
    
    if existing:
        return {"message": "User already in relevant list", "user_id": str(user_id)}
    
    # Add new relevant user
    relevant = TaskRelevantUser(
        task_id=task_id,
        user_id=user_id,
        added_by_user_id=current_user.id
    )
    db.add(relevant)
    db.commit()
    
    return {"message": "User added to relevant list", "user_id": str(user_id), "user_name": user.name}


@router.delete("/{task_id}/relevant-users/{user_id}")
async def remove_relevant_user(
    task_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a user from the relevant users list for a task.
    
    Permissions:
    - Anyone can remove THEMSELVES from any task
    - Task OWNER can remove ANYONE
    - MANAGER can remove their employees (direct or indirect)
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    if not _can_modify_relevant_user(db, current_user, task, user_id):
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. You can only remove yourself, or you must be the task owner or a manager of the target user."
        )
    
    existing = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.task_id == task_id,
        TaskRelevantUser.user_id == user_id
    ).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="User not in relevant list")
    
    db.delete(existing)
    db.commit()
    
    return {"message": "User removed from relevant list", "user_id": str(user_id)}

