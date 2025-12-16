"""
Task Workflow Simulations

Comprehensive tests simulating real user workflows for task lifecycle.
These tests cover all possible combinations of:
- Task creation (self vs for others)
- Accept/reject flows
- REJECTED state handling
- Edit and reassign flows
- Multi-user scenarios

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
# Single-User Flows
# =============================================================================

class TestSingleUserFlows:
    """Tests for tasks created by their owner."""
    
    def test_create_own_task_is_active(self, db_session, sample_users):
        """Owner creating their own task starts ACTIVE."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="My own task",
            owner=owner,
            creator=owner
        )
        
        assert task.state == TaskState.ACTIVE
        assert task.is_active == True
        
    def test_create_own_task_then_archive(self, db_session, sample_users):
        """Owner creates task -> archives it."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Task to archive",
            owner=owner,
            creator=owner
        )
        
        assert task.state == TaskState.ACTIVE
        
        # Archive it
        result = state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=TaskState.ARCHIVED,
            actor=owner,
            reason="No longer needed"
        )
        
        assert result.state == TaskState.ARCHIVED
        assert result.is_active == False
    
    def test_create_own_task_edit_then_archive(self, test_client, db_session, sample_users):
        """Owner creates task -> edits -> archives."""
        owner = sample_users["employee1"]
        
        # Create
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Original title",
            owner=owner,
            creator=owner
        )
        
        # Edit via API
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"title": "Updated title", "description": "New description"},
            headers={"X-User-Id": str(owner.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.title == "Updated title"
        assert task.state == TaskState.ACTIVE
        
        # Archive via API
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(owner.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.ARCHIVED


# =============================================================================
# Two-User Flows (Creator + Owner)
# =============================================================================

class TestTwoUserFlows:
    """Tests for tasks created by one user for another."""
    
    def test_creator_creates_owner_accepts(self, db_session, sample_users):
        """Creator creates for owner -> Owner accepts -> ACTIVE."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create task for owner
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Task for employee",
            owner=owner,
            creator=creator
        )
        
        assert task.state == TaskState.DRAFT
        assert task.created_by_user_id == creator.id
        assert task.owner_user_id == owner.id
        
        # Verify pending decision exists for owner
        decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner.id,
            PendingDecision.decision_type == PendingDecisionType.TASK_ACCEPTANCE
        ).first()
        assert decision is not None
        
        # Owner accepts
        result = state_machines.accept_task(db_session, task, owner)
        
        assert result.state == TaskState.ACTIVE
        assert result.is_active == True
    
    def test_creator_creates_owner_rejects_creator_sees_decision(self, db_session, sample_users):
        """Creator creates -> Owner rejects -> Creator sees pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Unwanted task",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        result = state_machines.reject_task(db_session, task, owner, "Not my responsibility")
        
        assert result.state == TaskState.REJECTED
        assert result.is_active == True  # REJECTED tasks stay visible
        assert result.state_reason == "Not my responsibility"
        
        # Creator should have pending decision
        creator_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert creator_decision is not None
    
    def test_creator_creates_owner_rejects_creator_archives(self, test_client, db_session, sample_users):
        """Creator creates -> Owner rejects -> Creator archives."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Will be rejected",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "No thanks")
        assert task.state == TaskState.REJECTED
        
        # Creator archives via DELETE
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.ARCHIVED
        assert task.is_active == False
    
    def test_creator_creates_owner_rejects_creator_self_assigns(self, test_client, db_session, sample_users):
        """Creator creates -> Owner rejects -> Creator assigns to self -> ACTIVE."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Will be self-assigned",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "Not for me")
        assert task.state == TaskState.REJECTED
        
        # Creator edits and assigns to self
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(creator.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        # When creator assigns to self, task becomes ACTIVE
        assert task.state == TaskState.ACTIVE
        assert task.owner_user_id == creator.id
    
    def test_creator_creates_owner_rejects_creator_reassigns(self, test_client, db_session, sample_users):
        """Creator creates -> Owner rejects -> Creator reassigns to another -> DRAFT."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        # Create task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Will be reassigned",
            owner=owner1,
            creator=creator
        )
        
        # Owner1 rejects
        state_machines.reject_task(db_session, task, owner1, "Wrong person")
        assert task.state == TaskState.REJECTED
        
        # Creator reassigns to owner2
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.DRAFT
        assert task.owner_user_id == owner2.id
        
        # New owner should have pending decision
        new_decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner2.id,
            PendingDecision.is_resolved == False
        ).first()
        assert new_decision is not None
    
    def test_creator_creates_owner_rejects_creator_edits_same_owner(self, test_client, db_session, sample_users):
        """Creator creates -> Owner rejects -> Creator edits but keeps same owner -> DRAFT."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Original title",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "Needs clarification")
        assert task.state == TaskState.REJECTED
        
        # Creator edits title/description but keeps same owner
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={
                "title": "Clarified title",
                "description": "More details here",
                "owner_user_id": str(owner.id)  # Same owner
            },
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.DRAFT  # Back to DRAFT for owner to reconsider
        assert task.title == "Clarified title"


# =============================================================================
# Three-User Flows (Creator + Owner1 + Owner2)
# =============================================================================

class TestThreeUserFlows:
    """Tests involving creator and multiple potential owners."""
    
    def test_bounce_between_owners_until_accept(self, test_client, db_session, sample_users):
        """Creator -> Owner1 rejects -> reassign to Owner2 -> Owner2 accepts."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        # Create for owner1
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Bouncing task",
            owner=owner1,
            creator=creator
        )
        
        # Owner1 rejects
        state_machines.reject_task(db_session, task, owner1, "Not my area")
        assert task.state == TaskState.REJECTED
        
        # Creator reassigns to owner2
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.DRAFT
        assert task.owner_user_id == owner2.id
        
        # Owner2 accepts
        result = state_machines.accept_task(db_session, task, owner2)
        assert result.state == TaskState.ACTIVE
    
    def test_double_bounce_then_archive(self, test_client, db_session, sample_users):
        """Creator -> Owner1 rejects -> Owner2 rejects -> Creator archives."""
        creator = sample_users["manager"]
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        
        # Create for owner1
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Double bounce task",
            owner=owner1,
            creator=creator
        )
        
        # Owner1 rejects
        state_machines.reject_task(db_session, task, owner1, "Nope")
        
        # Creator reassigns to owner2
        test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        db_session.refresh(task)
        
        # Owner2 rejects
        state_machines.reject_task(db_session, task, owner2, "Also nope")
        assert task.state == TaskState.REJECTED
        
        # Creator gives up and archives
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.ARCHIVED


# =============================================================================
# Rapid State Changes
# =============================================================================

class TestRapidStateChanges:
    """Tests for rapid sequences of state changes."""
    
    def test_fast_path_create_accept_archive(self, db_session, sample_users):
        """Create -> Accept -> Archive in quick succession."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Fast path task",
            owner=owner,
            creator=creator
        )
        assert task.state == TaskState.DRAFT
        
        # Accept immediately
        state_machines.accept_task(db_session, task, owner)
        assert task.state == TaskState.ACTIVE
        
        # Archive immediately
        state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Done quickly")
        assert task.state == TaskState.ARCHIVED
    
    def test_recovery_path_reject_reopen_accept(self, db_session, sample_users):
        """Create -> Reject -> Reopen -> Accept."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Recovery path task",
            owner=owner,
            creator=creator
        )
        
        # Reject
        state_machines.reject_task(db_session, task, owner, "Wait, let me reconsider")
        assert task.state == TaskState.REJECTED
        
        # Creator reopens (back to DRAFT)
        state_machines.reopen_rejected_task(db_session, task, creator)
        assert task.state == TaskState.DRAFT
        
        # Owner accepts this time
        state_machines.accept_task(db_session, task, owner)
        assert task.state == TaskState.ACTIVE


# =============================================================================
# Permission Edge Cases
# =============================================================================

class TestPermissionEdgeCases:
    """Tests for permission boundaries."""
    
    def test_non_owner_cannot_accept(self, db_session, sample_users):
        """Non-owner cannot accept a DRAFT task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test task",
            owner=owner,
            creator=creator
        )
        
        with pytest.raises(ValueError, match="Only the task owner"):
            state_machines.accept_task(db_session, task, other)
    
    def test_non_owner_cannot_reject(self, db_session, sample_users):
        """Non-owner cannot reject a DRAFT task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test task",
            owner=owner,
            creator=creator
        )
        
        with pytest.raises(ValueError, match="Only the task owner"):
            state_machines.reject_task(db_session, task, other, "Not my task to reject")
    
    def test_non_creator_cannot_reopen_rejected(self, db_session, sample_users):
        """Non-creator cannot reopen a REJECTED task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test task",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        # Other user cannot reopen
        with pytest.raises(ValueError, match="Only the task creator"):
            state_machines.reopen_rejected_task(db_session, task, other)
    
    def test_non_creator_cannot_edit_rejected(self, test_client, db_session, sample_users):
        """Non-creator cannot edit a REJECTED task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Test task",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        # Other user tries to edit
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"title": "Hacked title"},
            headers={"X-User-Id": str(other.id)}
        )
        
        # Should be forbidden
        assert response.status_code == 403
    
    def test_manager_can_edit_subordinate_task(self, test_client, db_session, sample_users):
        """Manager can edit tasks owned by their subordinates."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        # Employee creates their own task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Employee task",
            owner=employee,
            creator=employee
        )
        
        # Manager edits it
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"title": "Manager updated title"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        # Should succeed (manager has permission over subordinate's tasks)
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.title == "Manager updated title"


# =============================================================================
# Pending Decision Visibility
# =============================================================================

class TestPendingDecisionVisibility:
    """Tests for correct pending decision visibility."""
    
    def test_owner_sees_draft_decision(self, test_client, db_session, sample_users):
        """Owner sees pending decision for DRAFT task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="For owner",
            owner=owner,
            creator=creator
        )
        
        # Get owner's pending decisions via API
        response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(owner.id)}
        )
        assert response.status_code == 200
        
        data = response.json()
        decisions = data.get("decisions", [])
        
        # Should find the task
        task_ids = [d["entity_id"] for d in decisions if d["type"] == "TASK_ACCEPTANCE"]
        assert str(task.id) in task_ids
    
    def test_creator_sees_rejected_decision(self, test_client, db_session, sample_users):
        """Creator sees pending decision after owner rejects."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Will be rejected",
            owner=owner,
            creator=creator
        )
        
        # Owner rejects
        state_machines.reject_task(db_session, task, owner, "Not for me")
        
        # Get creator's pending decisions
        response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(creator.id)}
        )
        assert response.status_code == 200
        
        data = response.json()
        decisions = data.get("decisions", [])
        
        # Should find the rejected task
        task_ids = [d["entity_id"] for d in decisions]
        assert str(task.id) in task_ids
    
    def test_other_user_does_not_see_decision(self, test_client, db_session, sample_users):
        """Other user does not see someone else's pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Not for other",
            owner=owner,
            creator=creator
        )
        
        # Get other user's pending decisions
        response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(other.id)}
        )
        assert response.status_code == 200
        
        data = response.json()
        decisions = data.get("decisions", [])
        
        # Should NOT find the task
        task_ids = [d["entity_id"] for d in decisions]
        assert str(task.id) not in task_ids

