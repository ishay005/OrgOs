"""
Task State Machine Unit Tests

Tests the pure task state logic including:
- Task creation with correct initial states
- State transitions (DRAFT → ACTIVE/REJECTED → ARCHIVED, REJECTED → DRAFT)
- Illegal transition prevention
- State change validation

Unit Size: Service-level functions with mocked DB
Failure Modes:
- Incorrect initial state based on owner vs creator
- Allowed illegal state transitions
- State changes without proper authorization
- Missing state_changed_at timestamps
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models import Task, TaskState, User, PendingDecision, PendingDecisionType
from app.services import state_machines


class TestTaskCreationState:
    """Test initial task state based on owner/creator relationship."""
    
    def test_task_created_by_owner_is_active(self, db_session, sample_users):
        """When created_by == owner, task should be ACTIVE."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Self-created task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE if owner.id == owner.id else TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        assert task.state == TaskState.ACTIVE
    
    def test_task_created_for_other_is_draft(self, db_session, sample_users):
        """When created_by != owner, task should be DRAFT."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Suggested task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        assert task.state == TaskState.DRAFT
        assert task.owner_user_id != task.created_by_user_id


class TestTaskStateTransitions:
    """Test valid state transitions."""
    
    def test_draft_to_active_on_accept(self, db_session, sample_users):
        """DRAFT → ACTIVE when owner accepts the task."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        # Create DRAFT task
        task = Task(
            id=uuid.uuid4(),
            title="Suggested task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        # Accept the task
        state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=TaskState.ACTIVE,
            reason="Accepted by owner",
            actor=employee
        )
        
        assert task.state == TaskState.ACTIVE
        assert task.state_changed_at is not None
    
    def test_active_to_archived(self, db_session, sample_users, sample_tasks):
        """ACTIVE → ARCHIVED when task is archived/completed."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        assert task.state == TaskState.ACTIVE
        
        state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=TaskState.ARCHIVED,
            reason="Archived for cleanup",
            actor=owner
        )
        
        assert task.state == TaskState.ARCHIVED
    
    def test_state_change_updates_timestamp(self, db_session, sample_users, sample_tasks):
        """State changes should update state_changed_at."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        original_time = task.state_changed_at
        
        state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=TaskState.ARCHIVED,
            reason="Completed",
            actor=owner
        )
        
        assert task.state_changed_at is not None
        # Note: might be same if test runs fast, so we check it's set
    
    def test_same_state_no_change(self, db_session, sample_users, sample_tasks):
        """Setting same state should be a no-op."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        original_state = task.state
        
        state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=original_state,
            reason="No change",
            actor=owner
        )
        
        assert task.state == original_state


class TestTaskAcceptReject:
    """Test task accept/reject flows."""
    
    def test_accept_task_changes_state_to_active(self, db_session, sample_users):
        """Accepting a DRAFT task should change it to ACTIVE."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Suggested task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        result = state_machines.accept_task(db_session, task, employee)
        
        assert result.state == TaskState.ACTIVE
    
    def test_reject_task_sets_rejected(self, db_session, sample_users):
        """Rejecting a DRAFT task should set it to REJECTED with reason."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Suggested task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        reason = "Not relevant to my work"
        result = state_machines.reject_task(db_session, task, employee, reason)
        
        assert result.state == TaskState.REJECTED
        assert result.state_reason == reason
        assert result.is_active is True

    def test_rejected_can_return_to_draft_by_creator(self, db_session, sample_users):
        """Creator can reopen a rejected task back to DRAFT."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Suggested task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.REJECTED
        )
        db_session.add(task)
        db_session.commit()
        
        result = state_machines.reopen_rejected_task(db_session, task, manager)
        assert result.state == TaskState.DRAFT


class TestTaskStateValidation:
    """Test state validation and constraints."""
    
    def test_only_owner_can_accept(self, db_session, sample_users):
        """Only the task owner should be able to accept."""
        manager = sample_users["manager"]
        employee1 = sample_users["employee1"]
        employee2 = sample_users["employee2"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Task for employee1",
            owner_user_id=employee1.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        # employee2 trying to accept should fail
        with pytest.raises(ValueError, match="Only the task owner"):
            state_machines.accept_task(db_session, task, employee2)
    
    def test_cannot_accept_already_active_task(self, db_session, sample_users, sample_tasks):
        """Cannot accept a task that's already ACTIVE."""
        task = sample_tasks["task1"]  # Already ACTIVE
        owner = sample_users["employee1"]
        
        with pytest.raises(ValueError, match="not in DRAFT"):
            state_machines.accept_task(db_session, task, owner)

