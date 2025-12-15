"""
Dependency State Machine Unit Tests

Tests the dependency lifecycle including:
- propose_dependency: Creating PROPOSED dependencies
- accept_dependency: PROPOSED → CONFIRMED
- reject_dependency: PROPOSED → REJECTED with reason
- remove_dependency: Setting REMOVED status
- Auto-confirmation when same owner
- Prevention of self-dependencies and duplicates

Unit Size: Service-level functions
Failure Modes:
- Self-dependencies allowed
- Duplicate dependencies created
- Wrong user accepting/rejecting
- Missing rejection reasons
- Invalid status transitions
"""

import pytest
import uuid
from datetime import datetime

from app.models import (
    Task, TaskState, User, TaskDependencyV2, DependencyStatus,
    AlternativeDependencyProposal, AlternativeDepStatus
)
from app.services import state_machines


class TestProposeDependency:
    """Test dependency proposal logic."""
    
    def test_propose_dependency_creates_proposed_status(self, db_session, sample_users, sample_tasks):
        """Proposing a dependency should create it with PROPOSED status."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        assert dep.status == DependencyStatus.PROPOSED
        assert dep.downstream_task_id == task1.id
        assert dep.upstream_task_id == task2.id
        assert dep.created_by_user_id == proposer.id
    
    def test_same_owner_auto_confirms(self, db_session, sample_users):
        """When both tasks have same owner, dependency is auto-confirmed."""
        owner = sample_users["employee1"]
        
        task1 = Task(
            id=uuid.uuid4(),
            title="Task A",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        task2 = Task(
            id=uuid.uuid4(),
            title="Task B",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([task1, task2])
        db_session.commit()
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=owner,
            downstream_task=task1,
            upstream_task=task2
        )
        
        assert dep.status == DependencyStatus.CONFIRMED
        assert dep.accepted_by_user_id == owner.id
    
    def test_no_self_dependency(self, db_session, sample_users, sample_tasks):
        """Cannot create a dependency from a task to itself."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        with pytest.raises(ValueError, match="self"):
            state_machines.propose_dependency(
                db=db_session,
                requester=owner,
                downstream_task=task,
                upstream_task=task
            )
    
    def test_no_duplicate_proposed_dependency(self, db_session, sample_users, sample_tasks):
        """Cannot propose duplicate dependency."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        
        # First proposal
        dep1 = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        # Second proposal should return existing or raise
        dep2 = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        # Should return same dependency (no duplicate)
        assert dep1.id == dep2.id


class TestAcceptDependency:
    """Test dependency acceptance logic."""
    
    def test_upstream_owner_can_accept(self, db_session, sample_users, sample_tasks):
        """Only the upstream task owner can accept."""
        task1 = sample_tasks["task1"]  # Owner: employee1
        task2 = sample_tasks["task2"]  # Owner: employee2
        proposer = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        result = state_machines.accept_dependency(db_session, dep, upstream_owner)
        
        assert result.status == DependencyStatus.CONFIRMED
        assert result.accepted_by_user_id == upstream_owner.id
        assert result.accepted_at is not None
    
    def test_non_owner_cannot_accept(self, db_session, sample_users, sample_tasks):
        """Non-owner cannot accept dependency."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        wrong_user = sample_users["manager"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        with pytest.raises(ValueError, match="owner"):
            state_machines.accept_dependency(db_session, dep, wrong_user)
    
    def test_cannot_accept_confirmed_dependency(self, db_session, sample_users):
        """Cannot accept already confirmed dependency."""
        owner = sample_users["employee1"]
        
        task1 = Task(
            id=uuid.uuid4(),
            title="Task A",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        task2 = Task(
            id=uuid.uuid4(),
            title="Task B",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([task1, task2])
        db_session.commit()
        
        # This auto-confirms
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=owner,
            downstream_task=task1,
            upstream_task=task2
        )
        
        assert dep.status == DependencyStatus.CONFIRMED
        
        with pytest.raises(ValueError, match="not in PROPOSED"):
            state_machines.accept_dependency(db_session, dep, owner)


class TestRejectDependency:
    """Test dependency rejection logic."""
    
    def test_reject_requires_reason(self, db_session, sample_users, sample_tasks):
        """Rejection must have a reason."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        with pytest.raises(ValueError, match="reason"):
            state_machines.reject_dependency(db_session, dep, upstream_owner, "")
    
    def test_reject_sets_status_and_reason(self, db_session, sample_users, sample_tasks):
        """Rejection should set REJECTED status and store reason."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        reason = "This task is not related to mine"
        result = state_machines.reject_dependency(db_session, dep, upstream_owner, reason)
        
        assert result.status == DependencyStatus.REJECTED
        assert result.rejected_by_user_id == upstream_owner.id
        assert result.rejected_reason == reason
        assert result.rejected_at is not None
    
    def test_only_upstream_owner_can_reject(self, db_session, sample_users, sample_tasks):
        """Only upstream owner can reject."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        proposer = sample_users["employee1"]
        wrong_user = sample_users["manager"]
        
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        with pytest.raises(ValueError, match="owner"):
            state_machines.reject_dependency(db_session, dep, wrong_user, "Invalid reason")


class TestRemoveDependency:
    """Test dependency removal logic."""
    
    def test_downstream_owner_can_remove(self, db_session, sample_users, sample_tasks):
        """Downstream task owner can remove dependency."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        downstream_owner = sample_users["employee1"]
        
        # Create and accept dependency
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.CONFIRMED,
            created_by_user_id=downstream_owner.id
        )
        db_session.add(dep)
        db_session.commit()
        
        result = state_machines.remove_dependency(db_session, dep, downstream_owner)
        
        assert result.status == DependencyStatus.REMOVED
        assert result.removed_by_user_id == downstream_owner.id
    
    def test_upstream_owner_can_remove(self, db_session, sample_users, sample_tasks):
        """Upstream task owner can also remove dependency."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        downstream_owner = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.CONFIRMED,
            created_by_user_id=downstream_owner.id
        )
        db_session.add(dep)
        db_session.commit()
        
        result = state_machines.remove_dependency(db_session, dep, upstream_owner)
        
        assert result.status == DependencyStatus.REMOVED


class TestAlternativeDependency:
    """Test alternative dependency proposal flow."""
    
    def test_propose_alternative(self, db_session, sample_users, sample_tasks):
        """Can propose an alternative upstream task."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        
        # Create a third task as alternative
        alt_task = Task(
            id=uuid.uuid4(),
            title="Alternative Task",
            owner_user_id=sample_users["manager"].id,
            created_by_user_id=sample_users["manager"].id,
            state=TaskState.ACTIVE
        )
        db_session.add(alt_task)
        db_session.commit()
        
        proposer = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        # First create a proposed dependency
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=proposer,
            downstream_task=task1,
            upstream_task=task2
        )
        
        # Upstream owner proposes alternative
        alt_proposal = state_machines.propose_alternative_dependency(
            db=db_session,
            original_dependency=dep,
            suggested_upstream_task=alt_task,
            proposer=upstream_owner,
            reason="This other task is more relevant"
        )
        
        assert alt_proposal.status == AlternativeDepStatus.PROPOSED
        assert alt_proposal.suggested_upstream_task_id == alt_task.id
        assert alt_proposal.proposal_reason == "This other task is more relevant"

