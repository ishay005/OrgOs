"""
Pending Decisions API endpoints.
Handles task acceptance, merge proposals, dependency consent, and alternative dependencies.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import (
    User, Task, TaskState, TaskMergeProposal, MergeProposalStatus,
    TaskDependencyV2, DependencyStatus, AlternativeDependencyProposal, AlternativeDepStatus,
    PendingDecision, PendingDecisionType
)
from app.services import state_machines

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decisions", tags=["decisions"])


# =============================================================================
# Request Models
# =============================================================================

class TaskDecisionRequest(BaseModel):
    action: str  # "accept", "reject", "propose_merge"
    reason: Optional[str] = None
    merge_into_task_id: Optional[str] = None


class MergeDecisionRequest(BaseModel):
    action: str  # "accept", "reject"
    reason: Optional[str] = None


class DependencyDecisionRequest(BaseModel):
    action: str  # "accept", "reject", "propose_alternative"
    reason: Optional[str] = None
    alternative_task_id: Optional[str] = None


class AlternativeDecisionRequest(BaseModel):
    action: str  # "accept", "reject"
    reason: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/pending")
async def get_pending_decisions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all pending decisions for the current user.
    Includes task acceptances, merge proposals, dependency approvals, etc.
    """
    decisions = state_machines.get_pending_decisions_for_user(db, current_user.id)
    
    result = []
    for d in decisions:
        # Enrich with context based on type
        context = {}
        
        if d.entity_type == "task" and d.decision_type == PendingDecisionType.TASK_ACCEPTANCE:
            task = db.query(Task).filter(Task.id == d.entity_id).first()
            if task:
                creator = db.query(User).filter(User.id == task.created_by_user_id).first()
                
                # Check if the current user has already proposed a merge for this task
                pending_merge = db.query(TaskMergeProposal).filter(
                    TaskMergeProposal.from_task_id == task.id,
                    TaskMergeProposal.proposed_by_user_id == current_user.id,
                    TaskMergeProposal.status == MergeProposalStatus.PROPOSED
                ).first()
                
                context = {
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "task_description": task.description,
                    "task_state": task.state.value if task.state else None,
                    "task_state_reason": task.state_reason,
                    "creator_name": creator.name if creator else "Unknown",
                    "creator_id": str(task.created_by_user_id) if task.created_by_user_id else None,
                    "owner_id": str(task.owner_user_id) if task.owner_user_id else None,
                    "has_pending_merge": pending_merge is not None,
                    "pending_merge_id": str(pending_merge.id) if pending_merge else None,
                    "pending_merge_target": None
                }
                
                # If there's a pending merge, get target task info
                if pending_merge:
                    target_task = db.query(Task).filter(Task.id == pending_merge.to_task_id).first()
                    context["pending_merge_target"] = target_task.title if target_task else "Unknown"
        
        elif d.entity_type == "merge_proposal":
            proposal = db.query(TaskMergeProposal).filter(TaskMergeProposal.id == d.entity_id).first()
            if proposal:
                from_task = db.query(Task).filter(Task.id == proposal.from_task_id).first()
                to_task = db.query(Task).filter(Task.id == proposal.to_task_id).first()
                proposer = db.query(User).filter(User.id == proposal.proposed_by_user_id).first()
                context = {
                    "proposal_id": str(proposal.id),
                    "from_task_title": from_task.title if from_task else "Unknown",
                    "to_task_title": to_task.title if to_task else "Unknown",
                    "proposer_name": proposer.name if proposer else "Unknown",
                    "reason": proposal.proposal_reason
                }
        
        elif d.entity_type == "dependency":
            dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == d.entity_id).first()
            if dep:
                downstream = db.query(Task).filter(Task.id == dep.downstream_task_id).first()
                upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
                context = {
                    "dependency_id": str(dep.id),
                    "downstream_task": downstream.title if downstream else "Unknown",
                    "upstream_task": upstream.title if upstream else "Unknown"
                }
        
        elif d.entity_type == "alt_dependency":
            alt = db.query(AlternativeDependencyProposal).filter(
                AlternativeDependencyProposal.id == d.entity_id
            ).first()
            if alt:
                downstream = db.query(Task).filter(Task.id == alt.downstream_task_id).first()
                orig = db.query(Task).filter(Task.id == alt.original_upstream_task_id).first()
                suggested = db.query(Task).filter(Task.id == alt.suggested_upstream_task_id).first()
                proposer = db.query(User).filter(User.id == alt.proposed_by_user_id).first()
                context = {
                    "proposal_id": str(alt.id),
                    "downstream_task": downstream.title if downstream else "Unknown",
                    "original_upstream": orig.title if orig else "Unknown",
                    "suggested_upstream": suggested.title if suggested else "Unknown",
                    "proposer_name": proposer.name if proposer else "Unknown",
                    "reason": alt.proposal_reason
                }
        
        result.append({
            "id": str(d.id),
            "type": d.decision_type.value,
            "entity_type": d.entity_type,
            "entity_id": str(d.entity_id),
            "description": d.description,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "context": context
        })
    
    return {"decisions": result}


@router.post("/task/{task_id}")
async def decide_on_task(
    task_id: UUID,
    request: TaskDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a decision on a DRAFT task suggested to the current user.
    Actions: accept, reject, propose_merge
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Owner can act on DRAFT; creator can reopen REJECTED
    if task.state == TaskState.DRAFT:
        if task.owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the task owner can make this decision")
    elif task.state == TaskState.REJECTED:
        if task.created_by_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the task creator can reopen a rejected task")
    else:
        raise HTTPException(status_code=400, detail=f"Task is not actionable in state {task.state.value}")
    
    try:
        if task.state == TaskState.DRAFT:
            if request.action == "accept":
                result = state_machines.accept_task(db, task, current_user)
                return {"success": True, "message": "Task accepted", "new_state": result.state.value}
            
            elif request.action == "reject":
                if not request.reason:
                    raise HTTPException(status_code=400, detail="Reason is required for rejection")
                result = state_machines.reject_task(db, task, current_user, request.reason)
                return {"success": True, "message": "Task rejected", "new_state": result.state.value}
            
            elif request.action == "propose_merge":
                if not request.merge_into_task_id:
                    raise HTTPException(status_code=400, detail="merge_into_task_id is required")
                if not request.reason:
                    raise HTTPException(status_code=400, detail="Reason is required for merge proposal")
                
                to_task = db.query(Task).filter(Task.id == UUID(request.merge_into_task_id)).first()
                if not to_task:
                    raise HTTPException(status_code=404, detail="Target task not found")
                
                proposal = state_machines.propose_task_merge(db, task, to_task, current_user, request.reason)
                return {"success": True, "message": "Merge proposed", "proposal_id": str(proposal.id)}
        elif task.state == TaskState.REJECTED:
            if request.action == "reopen":
                result = state_machines.reopen_rejected_task(db, task, current_user)
                return {"success": True, "message": "Task reopened to DRAFT", "new_state": result.state.value}
        
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/merge/{proposal_id}")
async def decide_on_merge(
    proposal_id: UUID,
    request: MergeDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a decision on a merge proposal (second consent from task creator).
    Actions: accept, reject
    """
    proposal = db.query(TaskMergeProposal).filter(TaskMergeProposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Merge proposal not found")
    
    try:
        if request.action == "accept":
            result = state_machines.accept_merge_proposal(db, proposal, current_user)
            return {"success": True, "message": "Merge accepted and executed", "status": result.status.value}
        
        elif request.action == "reject":
            if not request.reason:
                raise HTTPException(status_code=400, detail="Reason is required for rejection")
            result = state_machines.reject_merge_proposal(db, proposal, current_user, request.reason)
            return {"success": True, "message": "Merge rejected", "status": result.status.value}
        
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/merge/{proposal_id}")
async def cancel_merge_proposal(
    proposal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a merge proposal that you proposed.
    Only the proposer can cancel their own proposal.
    """
    proposal = db.query(TaskMergeProposal).filter(TaskMergeProposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Merge proposal not found")
    
    # Only the proposer can cancel
    if proposal.proposed_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the proposer can cancel this merge")
    
    # Only cancel if still in PROPOSED status
    if proposal.status != MergeProposalStatus.PROPOSED:
        raise HTTPException(status_code=400, detail=f"Cannot cancel proposal in {proposal.status.value} status")
    
    # Delete the proposal
    db.delete(proposal)
    
    # Also delete any pending decisions related to this merge
    db.query(PendingDecision).filter(
        PendingDecision.entity_type == "merge_proposal",
        PendingDecision.entity_id == proposal_id
    ).delete()
    
    db.commit()
    
    return {"success": True, "message": "Merge proposal cancelled"}


@router.post("/dependency/{dependency_id}")
async def decide_on_dependency(
    dependency_id: UUID,
    request: DependencyDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a decision on a proposed dependency (upstream owner decides).
    Actions: accept, reject, propose_alternative
    """
    dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == dependency_id).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependency not found")
    
    try:
        if request.action == "accept":
            result = state_machines.accept_dependency(db, dep, current_user)
            return {"success": True, "message": "Dependency accepted", "status": result.status.value}
        
        elif request.action == "reject":
            if not request.reason:
                raise HTTPException(status_code=400, detail="Reason is required for rejection")
            result = state_machines.reject_dependency(db, dep, current_user, request.reason)
            return {"success": True, "message": "Dependency rejected", "status": result.status.value}
        
        elif request.action == "propose_alternative":
            if not request.alternative_task_id:
                raise HTTPException(status_code=400, detail="alternative_task_id is required")
            if not request.reason:
                raise HTTPException(status_code=400, detail="Reason is required for alternative proposal")
            
            alt_task = db.query(Task).filter(Task.id == UUID(request.alternative_task_id)).first()
            if not alt_task:
                raise HTTPException(status_code=404, detail="Alternative task not found")
            
            proposal = state_machines.propose_alternative_dependency(db, dep, alt_task, current_user, request.reason)
            return {"success": True, "message": "Alternative proposed", "proposal_id": str(proposal.id)}
        
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/alternative/{proposal_id}")
async def decide_on_alternative(
    proposal_id: UUID,
    request: AlternativeDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Make a decision on an alternative dependency proposal (downstream owner decides).
    Actions: accept, reject
    """
    proposal = db.query(AlternativeDependencyProposal).filter(
        AlternativeDependencyProposal.id == proposal_id
    ).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Alternative dependency proposal not found")
    
    try:
        if request.action == "accept":
            result_proposal, new_dep = state_machines.accept_alternative_dependency(db, proposal, current_user)
            return {
                "success": True,
                "message": "Alternative accepted",
                "new_dependency_id": str(new_dep.id)
            }
        
        elif request.action == "reject":
            if not request.reason:
                raise HTTPException(status_code=400, detail="Reason is required for rejection")
            result = state_machines.reject_alternative_dependency(db, proposal, current_user, request.reason)
            return {"success": True, "message": "Alternative rejected", "status": result.status.value}
        
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

