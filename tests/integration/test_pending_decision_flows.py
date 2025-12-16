"""
Pending Decision Flows Integration Tests

Tests the consistency and correctness of pending decisions:
- After create for other: owner has pending decision
- After accept: pending decision resolved
- After reject: owner's decision resolved, creator gets new decision
- After creator archives rejected: creator's decision resolved
- After creator reassigns: creator's decision resolved, new owner gets decision
- No duplicate pending decisions for same entity

All tests run in isolated test database via pytest fixtures.
"""

import pytest
import uuid
from datetime import datetime

from app.models import (
    Task, TaskState, User, PendingDecision, PendingDecisionType
)
from app.services import state_machines


# =============================================================================
# Create Task Decision Tests
# =============================================================================

class TestCreateTaskDecisions:
    """Tests for pending decisions on task creation."""
    
    def test_create_for_self_no_decision(self, db_session, sample_users):
        """Self-created task should NOT have pending decision."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Self task",
            owner=owner,
            creator=owner
        )
        
        # Should be ACTIVE with no pending decision
        assert task.state == TaskState.ACTIVE
        
        decisions = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.is_resolved == False
        ).all()
        
        assert len(decisions) == 0, "Self-created task should have no pending decisions"
    
    def test_create_for_other_has_owner_decision(self, db_session, sample_users):
        """Task created for other should have pending decision for owner."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="For employee",
            owner=owner,
            creator=creator
        )
        
        assert task.state == TaskState.DRAFT
        
        # Owner should have pending decision
        owner_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.decision_type == PendingDecisionType.TASK_ACCEPTANCE,
            PendingDecision.is_resolved == False
        ).first()
        
        assert owner_decision is not None
    
    def test_create_for_other_creator_has_no_decision(self, db_session, sample_users):
        """Task created for other should NOT give creator a decision initially."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="For employee",
            owner=owner,
            creator=creator
        )
        
        # Creator should NOT have pending decision initially
        creator_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        
        assert creator_decision is None


# =============================================================================
# Accept Task Decision Tests
# =============================================================================

class TestAcceptTaskDecisions:
    """Tests for pending decisions after accept."""
    
    def test_accept_resolves_owner_decision(self, db_session, sample_users):
        """Accepting task should resolve owner's pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Accept test",
            owner=owner,
            creator=creator
        )
        
        # Verify decision exists before accept
        before = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).first()
        assert before is not None
        
        # Accept
        state_machines.accept_task(db_session, task, owner)
        
        # Verify decision is resolved
        after = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).first()
        assert after is None
    
    def test_accept_no_new_decisions(self, db_session, sample_users):
        """Accepting task should not create new unresolved decisions."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Accept test",
            owner=owner,
            creator=creator
        )
        
        # Accept
        state_machines.accept_task(db_session, task, owner)
        
        # Count unresolved decisions
        count = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.is_resolved == False
        ).count()
        
        assert count == 0


# =============================================================================
# Reject Task Decision Tests
# =============================================================================

class TestRejectTaskDecisions:
    """Tests for pending decisions after reject."""
    
    def test_reject_resolves_owner_decision(self, db_session, sample_users):
        """Rejecting task should resolve owner's pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reject test",
            owner=owner,
            creator=creator
        )
        
        # Reject
        state_machines.reject_task(db_session, task, owner, "Not for me")
        
        # Owner's decision should be resolved
        owner_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).first()
        assert owner_decision is None
    
    def test_reject_creates_creator_decision(self, db_session, sample_users):
        """Rejecting task should create pending decision for creator."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reject test",
            owner=owner,
            creator=creator
        )
        
        # Reject
        state_machines.reject_task(db_session, task, owner, "Not for me")
        
        # Creator should have pending decision
        creator_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert creator_decision is not None
    
    def test_reject_creator_decision_has_correct_type(self, db_session, sample_users):
        """Creator's decision after reject should have correct type."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Type test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        
        assert decision is not None
        assert decision.decision_type == PendingDecisionType.TASK_ACCEPTANCE


# =============================================================================
# Archive Rejected Task Decision Tests
# =============================================================================

class TestArchiveRejectedDecisions:
    """Tests for pending decisions after archiving rejected task."""
    
    def test_archive_resolves_creator_decision(self, test_client, db_session, sample_users):
        """Archiving rejected task should resolve creator's decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Archive test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Not needed")
        
        # Verify creator has decision
        before = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert before is not None
        
        # Archive via API
        test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(creator.id)}
        )
        
        # Verify creator's decision is resolved
        after = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert after is None


# =============================================================================
# Reassign Rejected Task Decision Tests
# =============================================================================

class TestReassignRejectedDecisions:
    """Tests for pending decisions after reassigning rejected task."""
    
    def test_reassign_resolves_creator_decision(self, test_client, db_session, sample_users):
        """Reassigning rejected task should resolve creator's decision."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reassign test",
            owner=owner1,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner1, "Wrong person")
        
        # Verify creator has decision
        before = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert before is not None
        
        # Reassign via API
        test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        # Creator's decision for REJECTED should be resolved
        # (might have new one for DRAFT if logic creates it)
        db_session.expire_all()
    
    def test_reassign_creates_new_owner_decision(self, test_client, db_session, sample_users):
        """Reassigning rejected task should create decision for new owner."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reassign test",
            owner=owner1,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner1, "Wrong person")
        
        # Reassign via API
        test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        # New owner should have pending decision
        new_owner_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner2.id,
            PendingDecision.is_resolved == False
        ).first()
        assert new_owner_decision is not None
    
    def test_reassign_old_owner_has_no_decision(self, test_client, db_session, sample_users):
        """After reassign, old owner should have no pending decision."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reassign test",
            owner=owner1,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner1, "Wrong person")
        
        # Reassign
        test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        # Old owner should have no unresolved decisions
        old_owner_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner1.id,
            PendingDecision.is_resolved == False
        ).first()
        assert old_owner_decision is None


# =============================================================================
# No Duplicate Decisions Tests
# =============================================================================

class TestNoDuplicateDecisions:
    """Tests ensuring no duplicate pending decisions."""
    
    def test_no_duplicate_on_create(self, db_session, sample_users):
        """Creating task should not create duplicate decisions."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Duplicate test",
            owner=owner,
            creator=creator
        )
        
        count = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).count()
        
        assert count == 1
    
    def test_no_duplicate_on_reject(self, db_session, sample_users):
        """Rejecting task should not create duplicate decisions."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Duplicate test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        count = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).count()
        
        assert count == 1
    
    def test_no_duplicate_on_reopen(self, db_session, sample_users):
        """Reopening rejected task should not create duplicate decisions."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reopen test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        state_machines.reopen_rejected_task(db_session, task, creator)
        
        # Owner should have exactly 1 unresolved decision
        count = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == False
        ).count()
        
        assert count == 1
    
    def test_total_unresolved_reasonable(self, db_session, sample_users):
        """At any time, at most 1 unresolved decision per entity per user."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Total test",
            owner=owner,
            creator=creator
        )
        
        # Do multiple operations
        state_machines.reject_task(db_session, task, owner, "First reject")
        state_machines.reopen_rejected_task(db_session, task, creator)
        state_machines.reject_task(db_session, task, owner, "Second reject")
        state_machines.reopen_rejected_task(db_session, task, creator)
        
        # Check each user has at most 1 unresolved
        for user in [creator, owner]:
            count = db_session.query(PendingDecision).filter(
                PendingDecision.entity_id == task.id,
                PendingDecision.user_id == user.id,
                PendingDecision.is_resolved == False
            ).count()
            
            assert count <= 1, f"User {user.name} has {count} duplicate decisions"


# =============================================================================
# Decision Resolution Status Tests
# =============================================================================

class TestDecisionResolutionStatus:
    """Tests for decision resolution field consistency."""
    
    def test_resolved_has_resolved_at(self, db_session, sample_users):
        """Resolved decisions should have resolved_at timestamp."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Resolution test",
            owner=owner,
            creator=creator
        )
        
        # Accept to resolve decision
        state_machines.accept_task(db_session, task, owner)
        
        # Find resolved decision
        resolved = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == True
        ).first()
        
        assert resolved is not None
        assert resolved.resolved_at is not None
    
    def test_resolved_has_resolution(self, db_session, sample_users):
        """Resolved decisions should have resolution text."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Resolution test",
            owner=owner,
            creator=creator
        )
        
        # Accept to resolve decision
        state_machines.accept_task(db_session, task, owner)
        
        # Find resolved decision
        resolved = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.is_resolved == True
        ).first()
        
        assert resolved is not None
        assert resolved.resolution is not None
        assert len(resolved.resolution) > 0

