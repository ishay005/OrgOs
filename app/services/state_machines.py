"""
State Machine Services for OrgOs.

Implements:
- Task state machine (DRAFT -> ACTIVE -> DONE -> ARCHIVED)
- Task merge with double consent
- Attribute/Perception consensus computation
- Dependency state machine (PROPOSED -> CONFIRMED/REJECTED/REMOVED)
- Alternative dependency proposals with double consent
"""
import html
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import (
    User, Task, TaskState, TaskAlias, TaskMergeProposal, MergeProposalStatus,
    TaskDependencyV2, DependencyStatus, AlternativeDependencyProposal, AlternativeDepStatus,
    AttributeAnswer, SimilarityScore, AttributeConsensusState,
    PendingDecision, PendingDecisionType, AttributeDefinition
)

logger = logging.getLogger(__name__)


def _sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS attacks."""
    if not text:
        return text
    return html.escape(text)


# =============================================================================
# Task State Machine
# =============================================================================

def set_task_state(
    db: Session,
    task: Task,
    new_state: TaskState,
    actor: User,
    reason: Optional[str] = None
) -> Task:
    """
    Change Task.state, record timestamps and optional reason.
    
    Transitions:
    - DRAFT -> ACTIVE (owner accepts)
    - DRAFT -> ARCHIVED (owner rejects)
    - ACTIVE -> DONE (completion)
    - ACTIVE -> ARCHIVED (archived)
    - DONE -> ARCHIVED (archived)
    
    Raises ValueError for:
    - Actor is not the owner
    - Invalid state transition (e.g. DRAFT -> DONE directly)
    - Trying to reactivate an ARCHIVED task
    """
    old_state = task.state
    
    # Same-state transition is a no-op
    if old_state == new_state:
        return task
    
    # Permission check: only owner can change state
    if actor.id != task.owner_user_id:
        raise ValueError("Only the task owner can change a task's state")
    
    # Validate state transitions
    VALID_TRANSITIONS = {
        TaskState.DRAFT: [TaskState.ACTIVE, TaskState.ARCHIVED],
        TaskState.ACTIVE: [TaskState.DONE, TaskState.ARCHIVED],
        TaskState.DONE: [TaskState.ARCHIVED, TaskState.ACTIVE],  # Can reopen
        TaskState.ARCHIVED: [],  # Cannot leave ARCHIVED
    }
    
    if new_state not in VALID_TRANSITIONS.get(old_state, []):
        raise ValueError(f"Invalid state transition: {old_state.value} -> {new_state.value}")
    
    task.state = new_state
    task.state_changed_at = datetime.utcnow()
    task.state_reason = reason
    task.updated_at = datetime.utcnow()
    
    # Update is_active flag based on state
    if new_state in [TaskState.ACTIVE, TaskState.DONE]:
        task.is_active = True
    elif new_state == TaskState.ARCHIVED:
        task.is_active = False
    
    db.commit()
    logger.info(f"Task {task.id} state changed: {old_state} -> {new_state} by {actor.name}")
    
    return task


def create_task_with_state(
    db: Session,
    title: str,
    owner: User,
    creator: User,
    description: Optional[str] = None,
    parent_id: Optional[UUID] = None
) -> Task:
    """
    Create a new task with proper state based on owner/creator relationship.
    
    - If creator == owner: state = ACTIVE (self-created task)
    - If creator != owner: state = DRAFT (suggested task, needs acceptance)
    
    Sanitizes title and description to prevent XSS attacks.
    Requires both owner and creator to be set.
    """
    # Validate required fields
    if not title or not title.strip():
        raise ValueError("Task title is required")
    if not owner:
        raise ValueError("Task owner is required")
    if not creator:
        raise ValueError("Task creator is required")
    
    # Sanitize inputs
    safe_title = _sanitize_input(title.strip())
    safe_description = _sanitize_input(description) if description else None
    
    # Determine initial state
    if creator.id == owner.id:
        initial_state = TaskState.ACTIVE
    else:
        initial_state = TaskState.DRAFT
    
    task = Task(
        title=safe_title,
        description=safe_description,
        owner_user_id=owner.id,
        created_by_user_id=creator.id,
        parent_id=parent_id,
        state=initial_state,
        is_active=(initial_state == TaskState.ACTIVE)
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    logger.info(f"Created task '{safe_title}' owner={owner.name} creator={creator.name} state={initial_state}")
    
    # If DRAFT, create a pending decision for the owner
    if initial_state == TaskState.DRAFT:
        create_pending_decision(
            db=db,
            user_id=owner.id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=task.id,
            description=f"{creator.name} suggested task '{safe_title}' for you. Accept, reject, or propose merge?"
        )
    
    return task


def accept_task(db: Session, task: Task, actor: User) -> Task:
    """
    Owner accepts a DRAFT task, transitioning it to ACTIVE.
    """
    if task.state != TaskState.DRAFT:
        raise ValueError(f"Task is not in DRAFT state (current: {task.state})")
    if actor.id != task.owner_user_id:
        raise ValueError("Only the task owner can accept a task")
    
    task = set_task_state(db, task, TaskState.ACTIVE, actor)
    
    # Resolve pending decision
    resolve_pending_decision(db, "task", task.id, "accepted")
    
    return task


def reject_task(db: Session, task: Task, actor: User, reason: str) -> Task:
    """
    Owner rejects a DRAFT task, transitioning it to ARCHIVED.
    Reason is required.
    """
    if task.state != TaskState.DRAFT:
        raise ValueError(f"Task is not in DRAFT state (current: {task.state})")
    if actor.id != task.owner_user_id:
        raise ValueError("Only the task owner can reject a task")
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is required")
    
    task = set_task_state(db, task, TaskState.ARCHIVED, actor, reason=reason)
    
    # Resolve pending decision
    resolve_pending_decision(db, "task", task.id, "rejected")
    
    return task


def complete_task(db: Session, task: Task, actor: User) -> Task:
    """
    Mark an ACTIVE task as DONE.
    """
    if task.state != TaskState.ACTIVE:
        raise ValueError(f"Task is not in ACTIVE state (current: {task.state})")
    
    return set_task_state(db, task, TaskState.DONE, actor)


def archive_task(db: Session, task: Task, actor: User, reason: Optional[str] = None) -> Task:
    """
    Archive a task (ACTIVE or DONE -> ARCHIVED).
    """
    if task.state not in [TaskState.ACTIVE, TaskState.DONE]:
        raise ValueError(f"Cannot archive task in {task.state} state")
    
    return set_task_state(db, task, TaskState.ARCHIVED, actor, reason=reason)


# =============================================================================
# Task Merge Proposal & Execution
# =============================================================================

def propose_task_merge(
    db: Session,
    from_task: Task,
    to_task: Task,
    proposer: User,
    reason: str
) -> TaskMergeProposal:
    """
    Propose merging from_task into to_task.
    Creates a pending decision for the creator of from_task.
    
    Requires both tasks to have the same owner.
    """
    if from_task.id == to_task.id:
        raise ValueError("Cannot merge a task into itself")
    if not reason or not reason.strip():
        raise ValueError("Proposal reason is required")
    if to_task.state == TaskState.ARCHIVED:
        raise ValueError("Cannot merge into an archived task")
    
    # Merge requires same owner
    if from_task.owner_user_id != to_task.owner_user_id:
        raise ValueError("Cannot merge tasks with different owners")
    
    # Check for existing active proposal
    existing = db.query(TaskMergeProposal).filter(
        TaskMergeProposal.from_task_id == from_task.id,
        TaskMergeProposal.to_task_id == to_task.id,
        TaskMergeProposal.status == MergeProposalStatus.PROPOSED
    ).first()
    
    if existing:
        raise ValueError("An active merge proposal already exists for these tasks")
    
    proposal = TaskMergeProposal(
        from_task_id=from_task.id,
        to_task_id=to_task.id,
        proposed_by_user_id=proposer.id,
        proposal_reason=reason,
        status=MergeProposalStatus.PROPOSED
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    
    logger.info(f"Merge proposal created: {from_task.title} -> {to_task.title} by {proposer.name}")
    
    # Create pending decision for the creator of from_task (second consent)
    creator_id = from_task.created_by_user_id or from_task.owner_user_id
    if creator_id != proposer.id:
        create_pending_decision(
            db=db,
            user_id=creator_id,
            decision_type=PendingDecisionType.MERGE_CONSENT,
            entity_type="merge_proposal",
            entity_id=proposal.id,
            description=f"{proposer.name} suggests merging '{from_task.title}' into '{to_task.title}'. Reason: {reason}"
        )
    
    return proposal


def accept_merge_proposal(db: Session, proposal: TaskMergeProposal, actor: User) -> TaskMergeProposal:
    """
    Accept a merge proposal (second consent from creator of from_task).
    Executes the merge.
    """
    if proposal.status != MergeProposalStatus.PROPOSED:
        raise ValueError(f"Proposal is not in PROPOSED status (current: {proposal.status})")
    
    from_task = db.query(Task).get(proposal.from_task_id)
    
    # Verify actor is the creator of from_task
    creator_id = from_task.created_by_user_id or from_task.owner_user_id
    if actor.id != creator_id:
        raise ValueError("Only the creator of the source task can accept a merge proposal")
    
    # Update proposal status
    proposal.status = MergeProposalStatus.ACCEPTED
    proposal.accepted_by_user_id = actor.id
    proposal.accepted_at = datetime.utcnow()
    db.commit()
    
    # Execute the merge
    execute_task_merge(db, proposal)
    
    # Resolve pending decisions
    resolve_pending_decision(db, "merge_proposal", proposal.id, "accepted")
    resolve_pending_decision(db, "task", from_task.id, "merged")
    
    logger.info(f"Merge proposal accepted: {from_task.title} merged into task {proposal.to_task_id}")
    
    return proposal


def reject_merge_proposal(
    db: Session,
    proposal: TaskMergeProposal,
    actor: User,
    reason: str
) -> TaskMergeProposal:
    """
    Reject a merge proposal. from_task remains as separate DRAFT task.
    """
    if proposal.status != MergeProposalStatus.PROPOSED:
        raise ValueError(f"Proposal is not in PROPOSED status (current: {proposal.status})")
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is required")
    
    from_task = db.query(Task).get(proposal.from_task_id)
    creator_id = from_task.created_by_user_id or from_task.owner_user_id
    
    if actor.id != creator_id:
        raise ValueError("Only the creator of the source task can reject a merge proposal")
    
    proposal.status = MergeProposalStatus.REJECTED
    proposal.rejected_by_user_id = actor.id
    proposal.rejected_reason = reason
    db.commit()
    
    # Resolve pending decision
    resolve_pending_decision(db, "merge_proposal", proposal.id, "rejected")
    
    logger.info(f"Merge proposal rejected: {from_task.title} remains separate")
    
    return proposal


def cancel_merge_proposal(db: Session, proposal: TaskMergeProposal) -> None:
    """
    Cancel a pending merge proposal (by the proposer).
    This simply removes the proposal without affecting the task state.
    """
    if proposal.status != MergeProposalStatus.PROPOSED:
        raise ValueError("Can only cancel PROPOSED merge proposals")
    
    # Delete the proposal
    db.delete(proposal)
    db.commit()
    
    logger.info(f"Merge proposal {proposal.id} cancelled")


def execute_task_merge(db: Session, proposal: TaskMergeProposal) -> None:
    """
    Execute a merge after acceptance.
    - Create TaskAlias
    - Migrate AttributeAnswers, Dependencies, Questions
    - Archive from_task
    """
    from_task = db.query(Task).get(proposal.from_task_id)
    to_task = db.query(Task).get(proposal.to_task_id)
    
    # 1. Create TaskAlias
    alias = TaskAlias(
        canonical_task_id=to_task.id,
        alias_title=from_task.title,
        alias_created_by_user_id=from_task.created_by_user_id or from_task.owner_user_id,
        merged_from_task_id=from_task.id
    )
    db.add(alias)
    
    # 2. Migrate AttributeAnswers
    answers = db.query(AttributeAnswer).filter(AttributeAnswer.task_id == from_task.id).all()
    for answer in answers:
        # Check for duplicate (same user, same attribute, same target)
        existing = db.query(AttributeAnswer).filter(
            AttributeAnswer.task_id == to_task.id,
            AttributeAnswer.attribute_id == answer.attribute_id,
            AttributeAnswer.answered_by_user_id == answer.answered_by_user_id,
            AttributeAnswer.target_user_id == answer.target_user_id
        ).first()
        
        if not existing:
            # Re-point the answer
            answer.task_id = to_task.id
    
    # 3. Migrate Dependencies (V2)
    # Downstream dependencies (from_task depends on something)
    downstream_deps = db.query(TaskDependencyV2).filter(
        TaskDependencyV2.downstream_task_id == from_task.id,
        TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
    ).all()
    
    for dep in downstream_deps:
        # Check for duplicate
        existing = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == to_task.id,
            TaskDependencyV2.upstream_task_id == dep.upstream_task_id,
            TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
        ).first()
        
        if not existing:
            dep.downstream_task_id = to_task.id
        else:
            dep.status = DependencyStatus.REMOVED
            dep.removed_reason = "Merged - duplicate dependency"
    
    # Upstream dependencies (something depends on from_task)
    upstream_deps = db.query(TaskDependencyV2).filter(
        TaskDependencyV2.upstream_task_id == from_task.id,
        TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
    ).all()
    
    for dep in upstream_deps:
        # Check for duplicate
        existing = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == dep.downstream_task_id,
            TaskDependencyV2.upstream_task_id == to_task.id,
            TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
        ).first()
        
        if not existing:
            dep.upstream_task_id = to_task.id
        else:
            dep.status = DependencyStatus.REMOVED
            dep.removed_reason = "Merged - duplicate dependency"
    
    # 4. Archive from_task
    from_task.state = TaskState.ARCHIVED
    from_task.state_reason = f"Merged into '{to_task.title}'"
    from_task.state_changed_at = datetime.utcnow()
    from_task.is_active = False
    
    db.commit()
    logger.info(f"Merge executed: '{from_task.title}' -> '{to_task.title}'")


# =============================================================================
# Attribute Consensus State Machine
# =============================================================================

@dataclass
class AttributeAnswerSummary:
    user_id: str
    user_name: str
    value: str
    updated_at: datetime


@dataclass
class AttributeConsensusResult:
    state: AttributeConsensusState
    is_stale: bool
    answers: List[AttributeAnswerSummary]
    similarity_score: Optional[float] = None


def compute_attribute_consensus(
    db: Session,
    element_type: str,  # "task" for now
    element_id: UUID,
    attribute_name: str,
    staleness_days: int = 14,
    alignment_threshold: float = 0.7
) -> AttributeConsensusResult:
    """
    Compute the consensus state for an attribute on an element.
    
    Returns:
    - NO_DATA: No answers exist
    - SINGLE_SOURCE: Only one user has answered
    - ALIGNED: Multiple answers that agree (similarity >= threshold)
    - MISALIGNED: Multiple answers that disagree
    """
    # Get the attribute definition
    attr_def = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == attribute_name,
        AttributeDefinition.entity_type == element_type
    ).first()
    
    if not attr_def:
        return AttributeConsensusResult(
            state=AttributeConsensusState.NO_DATA,
            is_stale=False,
            answers=[]
        )
    
    # Fetch all non-refused answers for this (element, attribute)
    answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.task_id == element_id,
        AttributeAnswer.attribute_id == attr_def.id,
        AttributeAnswer.refused == False
    ).all()
    
    if len(answers) == 0:
        return AttributeConsensusResult(
            state=AttributeConsensusState.NO_DATA,
            is_stale=False,
            answers=[]
        )
    
    # Build answer summaries
    answer_summaries = []
    max_updated_at = None
    
    for ans in answers:
        user = db.query(User).get(ans.answered_by_user_id)
        answer_summaries.append(AttributeAnswerSummary(
            user_id=str(ans.answered_by_user_id),
            user_name=user.name if user else "Unknown",
            value=ans.value,
            updated_at=ans.updated_at
        ))
        if max_updated_at is None or ans.updated_at > max_updated_at:
            max_updated_at = ans.updated_at
    
    # Check staleness
    is_stale = False
    if max_updated_at:
        is_stale = (datetime.utcnow() - max_updated_at) > timedelta(days=staleness_days)
    
    if len(answers) == 1:
        return AttributeConsensusResult(
            state=AttributeConsensusState.SINGLE_SOURCE,
            is_stale=is_stale,
            answers=answer_summaries
        )
    
    # Multiple answers - check alignment using SimilarityScore
    # Get all answer IDs
    answer_ids = [ans.id for ans in answers]
    
    # Fetch similarity scores between these answers
    scores = db.query(SimilarityScore).filter(
        SimilarityScore.answer_a_id.in_(answer_ids),
        SimilarityScore.answer_b_id.in_(answer_ids)
    ).all()
    
    if not scores:
        # No similarity scores computed yet - check if values are identical
        unique_values = set(ans.value for ans in answers if ans.value)
        if len(unique_values) <= 1:
            return AttributeConsensusResult(
                state=AttributeConsensusState.ALIGNED,
                is_stale=is_stale,
                answers=answer_summaries,
                similarity_score=1.0
            )
        else:
            return AttributeConsensusResult(
                state=AttributeConsensusState.MISALIGNED,
                is_stale=is_stale,
                answers=answer_summaries,
                similarity_score=0.0
            )
    
    # Calculate average similarity
    avg_similarity = sum(s.similarity_score for s in scores) / len(scores)
    
    if avg_similarity >= alignment_threshold:
        state = AttributeConsensusState.ALIGNED
    else:
        state = AttributeConsensusState.MISALIGNED
    
    return AttributeConsensusResult(
        state=state,
        is_stale=is_stale,
        answers=answer_summaries,
        similarity_score=avg_similarity
    )


# =============================================================================
# Dependency State Machine
# =============================================================================

def _would_create_circular_dependency(db: Session, downstream_id: UUID, proposed_upstream_id: UUID) -> bool:
    """
    Check if adding proposed_upstream as a dependency of downstream would create a cycle.
    Uses BFS to traverse existing dependencies.
    """
    visited = set()
    queue = [proposed_upstream_id]
    
    while queue:
        current = queue.pop(0)
        if current == downstream_id:
            return True  # Found a cycle
        if current in visited:
            continue
        visited.add(current)
        
        # Find all tasks that current depends on (current is downstream, find upstreams)
        upstreams = db.query(TaskDependencyV2.upstream_task_id).filter(
            TaskDependencyV2.downstream_task_id == current,
            TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
        ).all()
        
        for (upstream_id,) in upstreams:
            if upstream_id not in visited:
                queue.append(upstream_id)
    
    return False


def propose_dependency(
    db: Session,
    requester: User,
    downstream_task: Task,
    upstream_task: Task
) -> TaskDependencyV2:
    """
    Propose a dependency: downstream_task depends on upstream_task.
    
    - If same owner for both tasks: auto-confirm
    - Otherwise: create PROPOSED and pending decision for upstream owner
    
    Raises ValueError for:
    - Self dependency
    - Archived task dependency
    - Circular dependency
    """
    if downstream_task.id == upstream_task.id:
        raise ValueError("A task cannot depend on itself")
    
    # Cannot depend on an archived task
    if upstream_task.state == TaskState.ARCHIVED:
        raise ValueError("Cannot create dependency on an ARCHIVED task")
    
    if downstream_task.state == TaskState.ARCHIVED:
        raise ValueError("Cannot add dependency from an ARCHIVED task")
    
    # Check for circular dependency
    if _would_create_circular_dependency(db, downstream_task.id, upstream_task.id):
        raise ValueError("Circular dependency detected")
    
    # Check for existing non-REMOVED dependency
    existing = db.query(TaskDependencyV2).filter(
        TaskDependencyV2.downstream_task_id == downstream_task.id,
        TaskDependencyV2.upstream_task_id == upstream_task.id,
        TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
    ).first()
    
    if existing:
        return existing  # Already exists, no-op
    
    # Create new dependency
    dep = TaskDependencyV2(
        downstream_task_id=downstream_task.id,
        upstream_task_id=upstream_task.id,
        created_by_user_id=requester.id,
        status=DependencyStatus.PROPOSED
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    
    # Auto-confirm if same owner
    if downstream_task.owner_user_id == upstream_task.owner_user_id:
        dep.status = DependencyStatus.CONFIRMED
        dep.accepted_by_user_id = upstream_task.owner_user_id
        dep.accepted_at = datetime.utcnow()
        db.commit()
        logger.info(f"Dependency auto-confirmed (same owner): {downstream_task.title} -> {upstream_task.title}")
    else:
        # Create pending decision for upstream owner
        create_pending_decision(
            db=db,
            user_id=upstream_task.owner_user_id,
            decision_type=PendingDecisionType.DEPENDENCY_ACCEPTANCE,
            entity_type="dependency",
            entity_id=dep.id,
            description=f"'{downstream_task.title}' wants to depend on your task '{upstream_task.title}'. Accept?"
        )
        logger.info(f"Dependency proposed: {downstream_task.title} -> {upstream_task.title}")
    
    return dep


def accept_dependency(db: Session, dependency: TaskDependencyV2, actor: User) -> TaskDependencyV2:
    """
    Accept a PROPOSED dependency. Only upstream task owner can accept.
    """
    if dependency.status != DependencyStatus.PROPOSED:
        raise ValueError(f"Dependency is not in PROPOSED status (current: {dependency.status})")
    
    upstream_task = db.query(Task).get(dependency.upstream_task_id)
    if actor.id != upstream_task.owner_user_id:
        raise ValueError("Only the upstream task owner can accept a dependency")
    
    dependency.status = DependencyStatus.CONFIRMED
    dependency.accepted_by_user_id = actor.id
    dependency.accepted_at = datetime.utcnow()
    db.commit()
    
    # Resolve pending decision
    resolve_pending_decision(db, "dependency", dependency.id, "accepted")
    
    logger.info(f"Dependency confirmed by {actor.name}")
    return dependency


def reject_dependency(
    db: Session,
    dependency: TaskDependencyV2,
    actor: User,
    reason: str
) -> TaskDependencyV2:
    """
    Reject a PROPOSED dependency. Only upstream task owner can reject.
    """
    if dependency.status != DependencyStatus.PROPOSED:
        raise ValueError(f"Dependency is not in PROPOSED status (current: {dependency.status})")
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is required")
    
    upstream_task = db.query(Task).get(dependency.upstream_task_id)
    if actor.id != upstream_task.owner_user_id:
        raise ValueError("Only the upstream task owner can reject a dependency")
    
    dependency.status = DependencyStatus.REJECTED
    dependency.rejected_by_user_id = actor.id
    dependency.rejected_at = datetime.utcnow()
    dependency.rejected_reason = reason
    db.commit()
    
    # Resolve pending decision
    resolve_pending_decision(db, "dependency", dependency.id, "rejected")
    
    logger.info(f"Dependency rejected by {actor.name}: {reason}")
    return dependency


def remove_dependency(
    db: Session,
    dependency: TaskDependencyV2,
    actor: User,
    reason: Optional[str] = None
) -> TaskDependencyV2:
    """
    Remove an existing dependency. Owner of either task can remove.
    """
    if dependency.status not in [DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED]:
        raise ValueError(f"Cannot remove dependency in {dependency.status} status")
    
    downstream_task = db.query(Task).get(dependency.downstream_task_id)
    upstream_task = db.query(Task).get(dependency.upstream_task_id)
    
    if actor.id not in [downstream_task.owner_user_id, upstream_task.owner_user_id]:
        raise ValueError("Only task owners can remove a dependency")
    
    dependency.status = DependencyStatus.REMOVED
    dependency.removed_by_user_id = actor.id
    dependency.removed_at = datetime.utcnow()
    dependency.removed_reason = reason
    db.commit()
    
    logger.info(f"Dependency removed by {actor.name}")
    return dependency


# =============================================================================
# Alternative Dependency Proposals
# =============================================================================

def propose_alternative_dependency(
    db: Session,
    original_dependency: TaskDependencyV2,
    suggested_upstream_task: Task,
    proposer: User,
    reason: str
) -> AlternativeDependencyProposal:
    """
    Propose an alternative dependency: instead of A->B, suggest A->C.
    Called when upstream owner rejects A->B but offers A->C.
    """
    if not reason or not reason.strip():
        raise ValueError("Proposal reason is required")
    
    downstream_task = db.query(Task).get(original_dependency.downstream_task_id)
    original_upstream = db.query(Task).get(original_dependency.upstream_task_id)
    
    if original_upstream.owner_user_id != proposer.id:
        raise ValueError("Only the original upstream owner can propose alternatives")
    
    if suggested_upstream_task.id == original_dependency.upstream_task_id:
        raise ValueError("Alternative must be different from original")
    
    if suggested_upstream_task.id == downstream_task.id:
        raise ValueError("Cannot create circular dependency")
    
    # Mark original as rejected
    original_dependency.status = DependencyStatus.REJECTED
    original_dependency.rejected_by_user_id = proposer.id
    original_dependency.rejected_at = datetime.utcnow()
    original_dependency.rejected_reason = f"Suggesting alternative: {suggested_upstream_task.title}"
    
    # Create alternative proposal
    alt = AlternativeDependencyProposal(
        original_dependency_id=original_dependency.id,
        downstream_task_id=downstream_task.id,
        original_upstream_task_id=original_upstream.id,
        suggested_upstream_task_id=suggested_upstream_task.id,
        proposed_by_user_id=proposer.id,
        proposal_reason=reason,
        status=AlternativeDepStatus.PROPOSED
    )
    db.add(alt)
    db.commit()
    db.refresh(alt)
    
    # Create pending decision for downstream owner
    create_pending_decision(
        db=db,
        user_id=downstream_task.owner_user_id,
        decision_type=PendingDecisionType.ALTERNATIVE_DEP_ACCEPTANCE,
        entity_type="alt_dependency",
        entity_id=alt.id,
        description=f"Instead of '{original_upstream.title}', depend on '{suggested_upstream_task.title}'? Reason: {reason}"
    )
    
    logger.info(f"Alternative dependency proposed: {downstream_task.title} -> {suggested_upstream_task.title}")
    return alt


def accept_alternative_dependency(
    db: Session,
    proposal: AlternativeDependencyProposal,
    actor: User
) -> Tuple[AlternativeDependencyProposal, TaskDependencyV2]:
    """
    Accept an alternative dependency proposal.
    Creates the new dependency as CONFIRMED.
    """
    if proposal.status != AlternativeDepStatus.PROPOSED:
        raise ValueError(f"Proposal is not in PROPOSED status (current: {proposal.status})")
    
    downstream_task = db.query(Task).get(proposal.downstream_task_id)
    if actor.id != downstream_task.owner_user_id:
        raise ValueError("Only the downstream task owner can accept alternative dependency")
    
    # Accept the proposal
    proposal.status = AlternativeDepStatus.ACCEPTED
    proposal.accepted_by_user_id = actor.id
    proposal.accepted_at = datetime.utcnow()
    
    # Create the new dependency as CONFIRMED
    new_dep = TaskDependencyV2(
        downstream_task_id=proposal.downstream_task_id,
        upstream_task_id=proposal.suggested_upstream_task_id,
        created_by_user_id=proposal.proposed_by_user_id,
        status=DependencyStatus.CONFIRMED,
        accepted_by_user_id=actor.id,
        accepted_at=datetime.utcnow()
    )
    db.add(new_dep)
    db.commit()
    db.refresh(new_dep)
    
    # Resolve pending decision
    resolve_pending_decision(db, "alt_dependency", proposal.id, "accepted")
    
    logger.info(f"Alternative dependency accepted: new edge created")
    return proposal, new_dep


def reject_alternative_dependency(
    db: Session,
    proposal: AlternativeDependencyProposal,
    actor: User,
    reason: str
) -> AlternativeDependencyProposal:
    """
    Reject an alternative dependency proposal.
    No dependency is confirmed (neither original nor alternative).
    """
    if proposal.status != AlternativeDepStatus.PROPOSED:
        raise ValueError(f"Proposal is not in PROPOSED status (current: {proposal.status})")
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is required")
    
    downstream_task = db.query(Task).get(proposal.downstream_task_id)
    if actor.id != downstream_task.owner_user_id:
        raise ValueError("Only the downstream task owner can reject alternative dependency")
    
    proposal.status = AlternativeDepStatus.REJECTED
    proposal.rejected_by_user_id = actor.id
    proposal.rejected_reason = reason
    db.commit()
    
    # Resolve pending decision
    resolve_pending_decision(db, "alt_dependency", proposal.id, "rejected")
    
    logger.info(f"Alternative dependency rejected: {reason}")
    return proposal


# =============================================================================
# Pending Decision Helpers
# =============================================================================

def create_pending_decision(
    db: Session,
    user_id: UUID,
    decision_type: PendingDecisionType,
    entity_type: str,
    entity_id: UUID,
    description: str
) -> PendingDecision:
    """Create a pending decision for a user."""
    decision = PendingDecision(
        user_id=user_id,
        decision_type=decision_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        is_resolved=False
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    
    logger.info(f"Created pending decision: {decision_type} for user {user_id}")
    return decision


def resolve_pending_decision(
    db: Session,
    entity_type: str,
    entity_id: UUID,
    resolution: str
) -> None:
    """Resolve all pending decisions for an entity."""
    decisions = db.query(PendingDecision).filter(
        PendingDecision.entity_type == entity_type,
        PendingDecision.entity_id == entity_id,
        PendingDecision.is_resolved == False
    ).all()
    
    for decision in decisions:
        decision.is_resolved = True
        decision.resolved_at = datetime.utcnow()
        decision.resolution = resolution
    
    db.commit()


def get_pending_decisions_for_user(db: Session, user_id: UUID) -> List[PendingDecision]:
    """Get all unresolved pending decisions for a user."""
    return db.query(PendingDecision).filter(
        PendingDecision.user_id == user_id,
        PendingDecision.is_resolved == False
    ).order_by(PendingDecision.created_at.desc()).all()


# =============================================================================
# Query Helpers for State Machines
# =============================================================================

def get_confirmed_dependencies_for_task(
    db: Session,
    task_id: UUID
) -> Tuple[List[TaskDependencyV2], List[TaskDependencyV2]]:
    """
    Get confirmed dependencies for a task.
    Returns (outgoing, incoming) where:
    - outgoing: tasks this task depends on
    - incoming: tasks that depend on this task
    """
    outgoing = db.query(TaskDependencyV2).filter(
        TaskDependencyV2.downstream_task_id == task_id,
        TaskDependencyV2.status == DependencyStatus.CONFIRMED
    ).all()
    
    incoming = db.query(TaskDependencyV2).filter(
        TaskDependencyV2.upstream_task_id == task_id,
        TaskDependencyV2.status == DependencyStatus.CONFIRMED
    ).all()
    
    return outgoing, incoming


def get_proposed_dependencies_for_task(
    db: Session,
    task_id: UUID
) -> List[TaskDependencyV2]:
    """Get pending (PROPOSED) dependencies involving this task."""
    return db.query(TaskDependencyV2).filter(
        or_(
            TaskDependencyV2.downstream_task_id == task_id,
            TaskDependencyV2.upstream_task_id == task_id
        ),
        TaskDependencyV2.status == DependencyStatus.PROPOSED
    ).all()


def get_task_aliases(db: Session, task_id: UUID) -> List[TaskAlias]:
    """Get all aliases for a canonical task."""
    return db.query(TaskAlias).filter(
        TaskAlias.canonical_task_id == task_id
    ).all()


def get_canonical_tasks(db: Session, include_drafts: bool = False) -> List[Task]:
    """
    Get all canonical tasks (first-class nodes in OrgMap).
    Excludes ARCHIVED tasks unless they're the canonical for aliases.
    """
    query = db.query(Task).filter(Task.is_active == True)
    
    if not include_drafts:
        query = query.filter(Task.state != TaskState.DRAFT)
    
    return query.all()

