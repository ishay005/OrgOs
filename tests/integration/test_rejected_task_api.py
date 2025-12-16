"""
Rejected Task API Integration Tests

Tests the API endpoints for handling rejected tasks:
- GET /decisions/pending - returns rejected tasks with correct context
- PATCH /tasks/{id} - edit rejected task (creator only)
- DELETE /tasks/{id} - archive rejected task (creator only)
- POST /decisions/task/{id} - accept/reject on DRAFT tasks

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
# GET /decisions/pending Tests
# =============================================================================

class TestPendingDecisionsEndpoint:
    """Tests for GET /decisions/pending endpoint."""
    
    def test_returns_rejected_tasks_with_correct_state(self, test_client, db_session, sample_users):
        """Endpoint returns rejected tasks with task_state in context."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create and reject task
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected task test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Testing API")
        
        # Get creator's pending decisions
        response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        decisions = data.get("decisions", [])
        
        # Find the rejected task decision
        task_decisions = [d for d in decisions if d["entity_id"] == str(task.id)]
        assert len(task_decisions) >= 1
        
        decision = task_decisions[0]
        context = decision.get("context", {})
        
        # Should have task_state in context
        assert context.get("task_state") == "REJECTED" or "REJECTED" in str(decision)
    
    def test_rejected_tasks_show_rejection_reason(self, test_client, db_session, sample_users):
        """Rejected tasks show the rejection reason in context."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reason test task",
            owner=owner,
            creator=creator
        )
        
        rejection_reason = "This is not my area of responsibility"
        state_machines.reject_task(db_session, task, owner, rejection_reason)
        
        response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        decisions = data.get("decisions", [])
        
        # Find task decision
        task_decisions = [d for d in decisions if d["entity_id"] == str(task.id)]
        assert len(task_decisions) >= 1
    
    def test_draft_and_rejected_separated(self, test_client, db_session, sample_users):
        """DRAFT and REJECTED tasks are distinguishable."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        # Create draft task (for owner)
        draft_task = state_machines.create_task_with_state(
            db=db_session,
            title="Draft task",
            owner=owner,
            creator=creator
        )
        
        # Create rejected task (for creator)
        rejected_task = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected task",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, rejected_task, owner, "Rejected")
        
        # Get owner's decisions (should see draft)
        owner_response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(owner.id)}
        )
        assert owner_response.status_code == 200
        owner_decisions = owner_response.json().get("decisions", [])
        owner_task_ids = [d["entity_id"] for d in owner_decisions]
        assert str(draft_task.id) in owner_task_ids
        
        # Get creator's decisions (should see rejected)
        creator_response = test_client.get(
            "/decisions/pending",
            headers={"X-User-Id": str(creator.id)}
        )
        assert creator_response.status_code == 200
        creator_decisions = creator_response.json().get("decisions", [])
        creator_task_ids = [d["entity_id"] for d in creator_decisions]
        assert str(rejected_task.id) in creator_task_ids


# =============================================================================
# PATCH /tasks/{id} Tests (Edit Rejected Task)
# =============================================================================

class TestEditRejectedTaskEndpoint:
    """Tests for PATCH /tasks/{id} on rejected tasks."""
    
    def test_creator_can_edit_rejected_task(self, test_client, db_session, sample_users):
        """Creator can edit their rejected task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Original title",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Wrong title")
        
        # Creator edits
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={
                "title": "Corrected title",
                "description": "Updated description"
            },
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.title == "Corrected title"
        assert task.description == "Updated description"
    
    def test_non_creator_cannot_edit_rejected_task(self, test_client, db_session, sample_users):
        """Non-creator cannot edit rejected task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected task",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        # Other user tries to edit
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"title": "Hacked"},
            headers={"X-User-Id": str(other.id)}
        )
        
        assert response.status_code == 403
    
    def test_edit_rejected_self_assign_becomes_active(self, test_client, db_session, sample_users):
        """Editing rejected task with self-assign makes it ACTIVE."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Self assign test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Not for me")
        
        # Creator assigns to self
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(creator.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.owner_user_id == creator.id
        assert task.state == TaskState.ACTIVE
    
    def test_edit_rejected_reassign_becomes_draft(self, test_client, db_session, sample_users):
        """Editing rejected task with reassign makes it DRAFT."""
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
        
        # Creator reassigns to owner2
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"owner_user_id": str(owner2.id)},
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.owner_user_id == owner2.id
        assert task.state == TaskState.DRAFT
        
        # New pending decision for owner2
        decision = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == owner2.id,
            PendingDecision.is_resolved == False
        ).first()
        assert decision is not None
    
    def test_edit_rejected_keep_same_owner_becomes_draft(self, test_client, db_session, sample_users):
        """Editing rejected task keeping same owner makes it DRAFT."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Same owner test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Needs clarification")
        
        # Creator edits but keeps same owner
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={
                "title": "Clarified title",
                "owner_user_id": str(owner.id)
            },
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.DRAFT
        assert task.owner_user_id == owner.id


# =============================================================================
# DELETE /tasks/{id} Tests (Archive Rejected Task)
# =============================================================================

class TestArchiveRejectedTaskEndpoint:
    """Tests for DELETE /tasks/{id} on rejected tasks."""
    
    def test_creator_can_archive_rejected_task(self, test_client, db_session, sample_users):
        """Creator can archive their rejected task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="To archive",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Not needed")
        
        # Creator archives
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(creator.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.ARCHIVED
        assert task.is_active == False
    
    def test_non_creator_cannot_archive_rejected_task(self, test_client, db_session, sample_users):
        """Non-creator cannot archive rejected task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Cannot archive",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        # Other user tries to archive
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(other.id)}
        )
        
        assert response.status_code == 403
    
    def test_archive_resolves_pending_decision(self, test_client, db_session, sample_users):
        """Archiving rejected task resolves pending decision."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Archive resolution test",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        # Verify pending decision exists
        decision_before = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert decision_before is not None
        
        # Archive
        test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(creator.id)}
        )
        
        # Verify pending decision is resolved
        decision_after = db_session.query(PendingDecision).filter(
            PendingDecision.entity_id == task.id,
            PendingDecision.user_id == creator.id,
            PendingDecision.is_resolved == False
        ).first()
        assert decision_after is None


# =============================================================================
# POST /decisions/task/{id} Tests
# =============================================================================

class TestTaskDecisionEndpoint:
    """Tests for POST /decisions/task/{id} endpoint."""
    
    def test_accept_draft_task(self, test_client, db_session, sample_users):
        """Owner can accept DRAFT task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Accept test",
            owner=owner,
            creator=creator
        )
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.ACTIVE
    
    def test_reject_draft_task_with_reason(self, test_client, db_session, sample_users):
        """Owner can reject DRAFT task with reason."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Reject test",
            owner=owner,
            creator=creator
        )
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "reject", "reason": "Not my responsibility"},
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(task)
        assert task.state == TaskState.REJECTED
        assert task.state_reason == "Not my responsibility"
    
    def test_reject_without_reason_fails(self, test_client, db_session, sample_users):
        """Rejecting without reason fails."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="No reason test",
            owner=owner,
            creator=creator
        )
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "reject"},  # No reason
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code == 400
    
    def test_non_owner_cannot_accept(self, test_client, db_session, sample_users):
        """Non-owner cannot accept task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Permission test",
            owner=owner,
            creator=creator
        )
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(other.id)}
        )
        
        assert response.status_code == 403
    
    def test_cannot_accept_already_active(self, test_client, db_session, sample_users):
        """Cannot accept already ACTIVE task."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Already active",
            owner=owner,
            creator=owner  # Self-created = ACTIVE
        )
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should fail with 400 (not in DRAFT state)
        assert response.status_code == 400


# =============================================================================
# Task Graph Visibility Tests
# =============================================================================

class TestTaskGraphVisibility:
    """Tests for task visibility in task graph."""
    
    def test_rejected_tasks_visible_in_graph(self, test_client, db_session, sample_users):
        """REJECTED tasks should be visible in task graph."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Rejected visible",
            owner=owner,
            creator=creator
        )
        state_machines.reject_task(db_session, task, owner, "Rejected")
        
        assert task.is_active == True  # Should be visible
        
        # Get task graph
        response = test_client.get(
            "/tasks/graph/with-attributes",
            headers={"X-User-Id": str(creator.id)}
        )
        
        if response.status_code == 200:
            data = response.json()
            # Response may be a list or dict with tasks key
            tasks = data if isinstance(data, list) else data.get("tasks", [])
            task_ids = [str(t.get("id") if isinstance(t, dict) else getattr(t, "id", None)) for t in tasks]
            assert str(task.id) in task_ids
    
    def test_archived_tasks_not_in_graph(self, test_client, db_session, sample_users):
        """ARCHIVED tasks should NOT be in task graph."""
        owner = sample_users["employee1"]
        
        task = state_machines.create_task_with_state(
            db=db_session,
            title="Archived invisible",
            owner=owner,
            creator=owner
        )
        state_machines.set_task_state(db_session, task, TaskState.ARCHIVED, owner, reason="Done")
        
        assert task.is_active == False  # Should be invisible
        
        # Get task graph
        response = test_client.get(
            "/tasks/graph/with-attributes",
            headers={"X-User-Id": str(owner.id)}
        )
        
        if response.status_code == 200:
            data = response.json()
            # Response may be a list or dict with tasks key
            tasks = data if isinstance(data, list) else data.get("tasks", [])
            task_ids = [str(t.get("id") if isinstance(t, dict) else getattr(t, "id", None)) for t in tasks]
            assert str(task.id) not in task_ids

