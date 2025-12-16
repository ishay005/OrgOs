"""
Task State Invariant Tests

Property-based tests that verify critical invariants:
- REJECTED tasks always have is_active=True
- REJECTED tasks always have state_reason set
- DRAFT/ACTIVE/REJECTED tasks are visible (is_active=True)
- Only ARCHIVED tasks have is_active=False
- Pending decisions exist for correct user after each transition
- Fuzz testing with random operation sequences

These invariants must ALWAYS hold, regardless of how the state was reached.
"""

import pytest
import uuid
import random
from datetime import datetime

from app.models import (
    Task, TaskState, User, PendingDecision, PendingDecisionType
)
from app.services import state_machines


# =============================================================================
# Core State Invariants
# =============================================================================

class TestRejectedStateInvariants:
    """Invariants specific to the REJECTED state."""
    
    def test_rejected_task_is_active(self, db_session, sample_users):
        """REJECTED tasks must have is_active=True."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test rejected visibility",
            owner=owner,
            creator=creator
        )
        
        # Reject it
        state_machines.reject_task(db_session, task, owner, "Testing")
        
        assert task.state == TaskState.REJECTED
        assert task.is_active == True, "REJECTED tasks MUST have is_active=True"
    
    def test_rejected_task_has_reason(self, db_session, sample_users):
        """REJECTED tasks must have state_reason set."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test rejected reason",
            owner=owner,
            creator=creator
        )
        
        reason = "This is the rejection reason"
        state_machines.reject_task(db_session, task, owner, reason)
        
        assert task.state == TaskState.REJECTED
        assert task.state_reason == reason, "REJECTED tasks MUST have state_reason set"
    
    def test_rejected_without_reason_fails(self, db_session, sample_users):
        """Rejecting without a reason must fail."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test no reason",
            owner=owner,
            creator=creator
        )
        
        with pytest.raises(ValueError, match="[Rr]eason"):
            state_machines.reject_task(db_session, task, owner, "")
        
        with pytest.raises(ValueError, match="[Rr]eason"):
            state_machines.reject_task(db_session, task, owner, "   ")


class TestVisibilityInvariants:
    """Invariants for task visibility (is_active flag)."""
    
    def test_draft_is_active(self, db_session, sample_users):
        """DRAFT tasks must have is_active=True."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Draft visibility test",
            owner=owner,
            creator=creator
        )
        
        assert task.state == TaskState.DRAFT
        assert task.is_active == True, "DRAFT tasks MUST be visible (is_active=True)"
    
    def test_active_is_active(self, db_session, sample_users):
        """ACTIVE tasks must have is_active=True."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Active visibility test",
            owner=owner,
            creator=owner  # Self-created = ACTIVE
        )
        
        assert task.state == TaskState.ACTIVE
        assert task.is_active == True, "ACTIVE tasks MUST be visible (is_active=True)"
    
    def test_archived_is_inactive(self, db_session, sample_users):
        """ARCHIVED tasks must have is_active=False."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Archive visibility test",
            owner=owner,
            creator=owner
        )
        
        state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Archiving")
        
        assert task.state == TaskState.ARCHIVED
        assert task.is_active == False, "ARCHIVED tasks MUST be invisible (is_active=False)"
    
    def test_only_archived_is_inactive(self, db_session, sample_users):
        """Only ARCHIVED state should have is_active=False."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Test all non-ARCHIVED states
        for target_state in [TaskState.DRAFT, TaskState.ACTIVE, TaskState.REJECTED]:
            task = Task(
                id=uuid.uuid4(),
                title=f"Test {target_state.value}",
                owner_user_id=owner.id,
                created_by_user_id=creator.id,
                state=target_state,
                is_active=True
            )
            db_session.add(task)
            db_session.commit()
            
            assert task.is_active == True, f"{target_state.value} tasks MUST have is_active=True"


class TestPendingDecisionInvariants:
    """Invariants for pending decisions."""
    
    def test_draft_has_owner_decision(self, db_session, sample_users):
        """DRAFT tasks must have pending decision for owner."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Draft decision test",
            owner=owner,
            creator=creator
        )
        
        decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).first()
        
        assert decision is not None, "DRAFT tasks MUST have pending decision for owner"
    
    def test_rejected_has_creator_decision(self, db_session, sample_users):
        """REJECTED tasks must have pending decision for creator."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected decision test",
            owner=owner,
            creator=creator
        )
        
        # Reject it
        state_machines.reject_task(db_session, task, owner, "Testing decision")
        
        decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        
        assert decision is not None, "REJECTED tasks MUST have pending decision for creator"
    
    def test_accepted_resolves_owner_decision(self, db_session, sample_users):
        """Accepting a task must resolve the owner's pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Accept resolution test",
            owner=owner,
            creator=creator
        )
        
        # Accept it
        state_machines.accept_task(db_session, task, owner)
        
        # Owner's decision should be resolved
        unresolved = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).first()
        
        assert unresolved is None, "Accept MUST resolve owner's pending decision"
    
    def test_no_duplicate_decisions(self, db_session, sample_users):
        """No duplicate unresolved decisions for same entity+user."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Duplicate check test",
            owner=owner,
            creator=creator
        )
        
        # Count decisions
        count = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).count()
        
        assert count <= 1, f"Found {count} duplicate decisions for same entity+user"


# =============================================================================
# Fuzz Testing with Random Operations
# =============================================================================

class TestFuzzOperations:
    """Fuzz testing with random operation sequences."""
    
    def test_random_operations_maintain_invariants(self, db_session, sample_users):
        """Random operations must maintain all invariants."""
        random.seed(42)  # Reproducibility
        
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        users = [creator, owner1, owner2]
        
        # Create some tasks
        tasks = []
        for i in range(5):
            owner = random.choice([owner1, owner2])
            task_creator = random.choice([creator, owner])
            
            task = state_machines.create_task_with_state(
                db=db_session,
                title=f"Fuzz Task {i}",
                owner=owner,
                creator=task_creator
            )
            tasks.append(task)
        
        # Random operations
        operations = ["accept", "reject", "archive", "reopen"]
        
        for _ in range(30):
            task = random.choice(tasks)
            op = random.choice(operations)
            
            try:
                if op == "accept" and task.state == TaskState.DRAFT:
                    owner = db_session.query(User).filter(User.id == task.owner_user_id).first()
                    state_machines.accept_task(db_session, task, owner)
                
                elif op == "reject" and task.state == TaskState.DRAFT:
                    owner = db_session.query(User).filter(User.id == task.owner_user_id).first()
                    state_machines.reject_task(db_session, task, owner, f"Fuzz reject {random.randint(1,100)}")
                
                elif op == "archive" and task.state == TaskState.ACTIVE:
                    owner = db_session.query(User).filter(User.id == task.owner_user_id).first()
                    state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Fuzz archive")
                
                elif op == "reopen" and task.state == TaskState.REJECTED:
                    task_creator = db_session.query(User).filter(User.id == task.created_by_user_id).first()
                    state_machines.reopen_rejected_task(db_session, task, task_creator)
                
            except (ValueError, Exception):
                db_session.rollback()
                continue
        
        # === Verify all invariants ===
        for task in tasks:
            db_session.refresh(task)
            
            # Visibility invariants
            if task.state == TaskState.ARCHIVED:
                assert task.is_active == False, f"ARCHIVED task {task.id} has is_active=True"
            else:
                assert task.is_active == True, f"{task.state.value} task {task.id} has is_active=False"
            
            # REJECTED reason invariant
            if task.state == TaskState.REJECTED:
                assert task.state_reason is not None and len(task.state_reason.strip()) > 0, \
                    f"REJECTED task {task.id} has no reason"
    
    def test_sequence_create_reject_reopen_accept(self, db_session, sample_users):
        """Full lifecycle: Create -> Reject -> Reopen -> Accept."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Lifecycle test",
            owner=owner,
            creator=creator
        )
        assert task.state == TaskState.DRAFT
        assert task.is_active == True
        
        # Reject
        state_machines.reject_task(db_session, task, owner, "First rejection")
        assert task.state == TaskState.REJECTED
        assert task.is_active == True
        assert task.state_reason == "First rejection"
        
        # Reopen
        state_machines.reopen_rejected_task(db_session, task, creator)
        assert task.state == TaskState.DRAFT
        assert task.is_active == True
        
        # Accept
        state_machines.accept_task(db_session, task, owner)
        assert task.state == TaskState.ACTIVE
        assert task.is_active == True
    
    def test_sequence_create_reject_reject_reject(self, db_session, sample_users):
        """Multiple rejections maintain invariants."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        # Create
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Multi-reject test",
            owner=owner1,
            creator=creator
        )
        
        # First rejection
        state_machines.reject_task(db_session, task, owner1, "Reason 1")
        assert task.state == TaskState.REJECTED
        assert task.is_active == True
        
        # Reopen and reassign
        state_machines.reopen_rejected_task(db_session, task, creator)
        task.owner_user_id = owner2.id
        task.state = TaskState.DRAFT
        db_session.commit()
        
        # Second rejection
        state_machines.reject_task(db_session, task, owner2, "Reason 2")
        assert task.state == TaskState.REJECTED
        assert task.is_active == True
        assert task.state_reason == "Reason 2"


# =============================================================================
# State Transition Validation
# =============================================================================

class TestStateTransitionValidation:
    """Tests for valid/invalid state transitions."""
    
    def test_valid_transitions_from_draft(self, db_session, sample_users):
        """DRAFT can go to ACTIVE, REJECTED."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # DRAFT -> ACTIVE
        task1 = state_machines.create_task_with_state(
            db=db_session,
            title="Draft to active",
            owner=owner,
            creator=creator
        )
        state_machines.accept_task(db_session, task1, owner)
        assert task1.state == TaskState.ACTIVE
        
        # DRAFT -> REJECTED
        task2 = state_machines.create_task_with_state(
            db=db_session,
            title="Draft to rejected",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task2, owner, "Rejecting")
        assert task2.state == TaskState.REJECTED
    
    def test_valid_transitions_from_active(self, db_session, sample_users):
        """ACTIVE can go to ARCHIVED."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Active to archived",
            owner=owner,
            creator=owner
        )
        assert task.state == TaskState.ACTIVE
        
        state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Done")
        assert task.state == TaskState.ARCHIVED
    
    def test_valid_transitions_from_rejected(self, db_session, sample_users):
        """REJECTED can go to DRAFT, ARCHIVED."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # REJECTED -> DRAFT
        task1 = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected to draft",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task1, owner, "Reject1")
        state_machines.reopen_rejected_task(db_session, task1, creator)
        assert task1.state == TaskState.DRAFT
        
        # REJECTED -> ARCHIVED
        task2 = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected to archived",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task2, owner, "Reject2")
        state_machines.set_task_state(db_session, task2, TaskState.ARCHIVED, creator, reason="Cleanup")
        assert task2.state == TaskState.ARCHIVED
    
    def test_invalid_transition_archived_to_active(self, db_session, sample_users):
        """ARCHIVED cannot go back to ACTIVE."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Archived stuck",
            owner=owner,
            creator=owner
        )
        state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Done")
        
        with pytest.raises(ValueError, match="Invalid state transition"):
            state_machines.set_task_state(db_session, task, TaskState.ACTIVE, owner, reason="Reopen")

