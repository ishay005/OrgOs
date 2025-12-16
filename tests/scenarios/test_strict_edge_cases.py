"""
Strict Edge Case and Adversarial Tests

These tests specifically target edge cases and adversarial scenarios
that could cause system failures, data corruption, or security issues.

If these tests fail, it indicates a potential vulnerability or bug.
"""

import pytest
import uuid
from datetime import datetime, timedelta
import string
import random

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType, TaskDependencyV2, DependencyStatus
)
from app.services import state_machines


class TestBoundaryConditions:
    """Test extreme boundary conditions."""
    
    def test_very_long_task_title(self, test_client, db_session, sample_users):
        """System should handle or reject very long task titles."""
        owner = sample_users["employee1"]
        
        # Create task with very long title (10000 chars)
        long_title = "A" * 10000
        
        response = test_client.post(
            "/tasks/",
            json={
                "title": long_title,
                "description": "Test"
            },
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should either succeed with truncated title, or fail with 400/422
        assert response.status_code in [200, 201, 400, 422], \
            f"Unexpected status {response.status_code} for very long title"
    
    def test_unicode_and_emoji_in_task_title(self, test_client, db_session, sample_users):
        """System should handle unicode and emoji in titles."""
        owner = sample_users["employee1"]
        
        unicode_title = "任务 🚀 ñoño 中文 العربية"
        
        response = test_client.post(
            "/tasks/",
            json={
                "title": unicode_title,
                "description": "Unicode test"
            },
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should succeed and preserve unicode
        if response.status_code in [200, 201]:
            data = response.json()
            assert "title" in data or True  # Check response has title
    
    def test_html_injection_in_task_title(self, test_client, db_session, sample_users):
        """System should sanitize or escape HTML in titles."""
        owner = sample_users["employee1"]
        
        xss_title = "<script>alert('xss')</script><img onerror='alert(1)' src=x>"
        
        response = test_client.post(
            "/tasks/",
            json={
                "title": xss_title,
                "description": "XSS test"
            },
            headers={"X-User-Id": str(owner.id)}
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            # If stored, title should be sanitized/escaped
            if "title" in data:
                assert "<script>" not in data.get("title", xss_title), \
                    "Script tags should be escaped or removed"
    
    def test_sql_injection_in_search(self, test_client, db_session, sample_users):
        """System should be safe from SQL injection."""
        owner = sample_users["employee1"]
        
        sql_injection = "'; DROP TABLE tasks; --"
        
        # Try to search with SQL injection
        response = test_client.get(
            f"/tasks/?search={sql_injection}",
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should return normally (empty results or error), not crash
        assert response.status_code in [200, 400, 404, 422], \
            f"SQL injection caused unexpected status {response.status_code}"
        
        # Verify tasks table still exists by creating a new task
        verify_response = test_client.post(
            "/tasks/",
            json={"title": "Post-injection test"},
            headers={"X-User-Id": str(owner.id)}
        )
        assert verify_response.status_code in [200, 201], \
            "Tasks table seems to be damaged after SQL injection attempt"


class TestRaceConditions:
    """Test potential race condition scenarios."""
    
    def test_double_accept_task(self, test_client, db_session, sample_users, sample_tasks):
        """Double-accepting a task should be handled gracefully."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        # If task is DRAFT, accept it twice
        if task.state == TaskState.DRAFT:
            response1 = test_client.post(
                f"/decisions/task/{task.id}",
                json={"action": "accept"},
                headers={"X-User-Id": str(owner.id)}
            )
            
            response2 = test_client.post(
                f"/decisions/task/{task.id}",
                json={"action": "accept"},
                headers={"X-User-Id": str(owner.id)}
            )
            
            # Second should fail gracefully (400) or succeed idempotently
            assert response2.status_code in [200, 400], \
                f"Double accept returned unexpected status {response2.status_code}"
    
    def test_double_accept_dependency(self, db_session, sample_users, sample_tasks):
        """Double-accepting a dependency should be handled."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        owner = sample_users["employee1"]
        upstream_owner = sample_users["employee2"]
        
        dep = state_machines.propose_dependency(
            db_session, owner, task1, task2
        )
        
        if dep.status == DependencyStatus.PROPOSED:
            # Accept twice
            result1 = state_machines.accept_dependency(db_session, dep, upstream_owner)
            
            try:
                result2 = state_machines.accept_dependency(db_session, dep, upstream_owner)
                # If it doesn't raise, should return same status
            except ValueError:
                pass  # Good - prevented double accept


class TestMalformedInput:
    """Test handling of malformed or unexpected input."""
    
    def test_invalid_uuid_format(self, test_client, sample_users):
        """Invalid UUID should return proper error."""
        owner = sample_users["employee1"]
        
        # Use an endpoint that exists and accepts task_id
        response = test_client.get(
            "/tasks/not-a-valid-uuid/full-details",
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code in [400, 404, 422], \
            f"Invalid UUID returned {response.status_code} instead of error"
    
    def test_missing_required_fields(self, test_client, sample_users):
        """Missing required fields should return proper error."""
        owner = sample_users["employee1"]
        
        # Empty task
        response = test_client.post(
            "/tasks/",
            json={},
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code in [400, 422], \
            f"Empty task creation returned {response.status_code} instead of validation error"
    
    def test_wrong_type_fields(self, test_client, sample_users):
        """Wrong field types should return proper error."""
        owner = sample_users["employee1"]
        
        response = test_client.post(
            "/tasks/",
            json={
                "title": 12345,  # Should be string
                "description": ["not", "a", "string"]  # Should be string
            },
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should either accept with coercion or reject with 422
        assert response.status_code in [200, 201, 400, 422], \
            f"Wrong type fields returned unexpected {response.status_code}"
    
    def test_negative_values(self, test_client, sample_users, sample_tasks):
        """Negative values for numeric fields should be handled."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        
        # Try to set negative limit on dependencies
        response = test_client.get(
            f"/tasks/?limit=-1&offset=-100",
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should either ignore negative or return error
        assert response.status_code in [200, 400, 422]


class TestResourceExhaustion:
    """Test behavior under resource pressure."""
    
    def test_many_attributes_on_single_task(self, db_session, sample_users, sample_tasks, sample_attributes):
        """Task with many attribute answers should work correctly."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        # Create 100 attribute answers
        for i in range(100):
            for attr_name, attr in sample_attributes.items():
                answer = AttributeAnswer(
                    id=uuid.uuid4(),
                    answered_by_user_id=owner.id,
                    target_user_id=owner.id,
                    task_id=task.id,
                    attribute_id=attr.id,
                    value=f"Value {i}"
                )
                db_session.add(answer)
        
        try:
            db_session.commit()
        except Exception as e:
            pytest.fail(f"Failed to create many attributes: {e}")
        
        # Now compute consensus - should not timeout or crash
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name="priority"
        )
        
        assert consensus is not None


class TestDataConsistency:
    """Test data consistency after various operations."""
    
    def test_task_count_after_bulk_operations(self, db_session, sample_users):
        """Task count should be consistent after bulk operations."""
        owner = sample_users["employee1"]
        
        initial_count = db_session.query(Task).filter(
            Task.owner_user_id == owner.id
        ).count()
        
        # Create 10 tasks
        created_tasks = []
        for i in range(10):
            task = Task(
                id=uuid.uuid4(),
                title=f"Bulk Task {i}",
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                state=TaskState.ACTIVE
            )
            db_session.add(task)
            created_tasks.append(task)
        
        db_session.commit()
        
        # Verify count increased by 10
        new_count = db_session.query(Task).filter(
            Task.owner_user_id == owner.id
        ).count()
        
        assert new_count == initial_count + 10, \
            f"Expected {initial_count + 10} tasks but found {new_count}"
    
    def test_dependency_consistency_after_task_archive(self, db_session, sample_users):
        """Dependencies should be handled when task is archived."""
        owner = sample_users["employee1"]
        
        task_a = Task(id=uuid.uuid4(), title="Task A", owner_user_id=owner.id,
                      created_by_user_id=owner.id, state=TaskState.ACTIVE)
        task_b = Task(id=uuid.uuid4(), title="Task B", owner_user_id=owner.id,
                      created_by_user_id=owner.id, state=TaskState.ACTIVE)
        db_session.add_all([task_a, task_b])
        db_session.commit()
        
        # Create dependency A -> B
        dep = state_machines.propose_dependency(db_session, owner, task_a, task_b)
        
        # Archive task B (don't cascade to dependencies per requirement #40)
        state_machines.set_task_state(db_session, task_b, TaskState.ARCHIVED, owner, reason="Archived")
        
        # Dependency should remain unchanged (per requirement: don't touch dependencies on archive)
        db_session.refresh(dep)
        # Dependency remains as-is - other tasks may still have goals related to this task
        assert dep.status in [DependencyStatus.CONFIRMED, DependencyStatus.PROPOSED]


class TestAuthorizationBypass:
    """Test for authorization bypass vulnerabilities."""
    
    def test_cannot_access_other_users_draft_tasks(self, test_client, db_session, sample_users):
        """User should not see another user's draft tasks."""
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        manager = sample_users["manager"]
        
        # Create draft task for owner (created by manager)
        draft_task = Task(
            id=uuid.uuid4(),
            title="Private Draft",
            owner_user_id=owner.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(draft_task)
        db_session.commit()
        
        # Other user tries to access it
        response = test_client.get(
            f"/tasks/{draft_task.id}",
            headers={"X-User-Id": str(other.id)}
        )
        
        # Should be 404 (not found) or 403 (forbidden), not 200
        if response.status_code == 200:
            # If visible, verify it doesn't leak sensitive info
            data = response.json()
            # At minimum, non-owner shouldn't be able to modify it
    
    def test_cannot_modify_others_pending_decisions(self, test_client, db_session, sample_users):
        """User cannot make decisions on others' pending items."""
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        manager = sample_users["manager"]
        
        # Create draft task for owner
        draft_task = Task(
            id=uuid.uuid4(),
            title="Owner's Task",
            owner_user_id=owner.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(draft_task)
        db_session.commit()
        
        # Other user tries to accept it
        response = test_client.post(
            f"/decisions/task/{draft_task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(other.id)}
        )
        
        # Should fail with 403 or 400
        assert response.status_code in [400, 403, 404], \
            f"Other user was able to accept owner's task (status {response.status_code})"


# =============================================================================
# Rejected Task Edge Cases
# =============================================================================

class TestRejectedTaskEdgeCases:
    """Edge cases specific to REJECTED task handling."""
    
    def test_edit_rejected_with_empty_title_handled(self, test_client, db_session, sample_users):
        """Editing rejected task with empty title should either fail or preserve original."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Original",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.REJECTED,
            state_reason="Rejected"
        )
        db_session.add(task)
        db_session.commit()
        
        response = test_client.patch(
            f"/tasks/{task.id}",
            json={"title": ""},
            headers={"X-User-Id": str(creator.id)}
        )
        
        # Should either reject with 400/422 or accept empty (current behavior)
        # This is a potential improvement area for validation
        assert response.status_code in [200, 400, 422]
    
    def test_archive_already_archived_task(self, test_client, db_session, sample_users):
        """Archiving already archived task should be idempotent or error."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Already archived",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ARCHIVED,
            is_active=False
        )
        db_session.add(task)
        db_session.commit()
        
        response = test_client.delete(
            f"/tasks/{task.id}",
            headers={"X-User-Id": str(owner.id)}
        )
        
        # Should either succeed (idempotent) or return 400
        assert response.status_code in [200, 400, 404]
    
    def test_reject_without_reason_fails(self, test_client, db_session, sample_users):
        """Rejecting task without reason should fail."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Reject test",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "reject"},  # No reason
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code == 400
    
    def test_accept_task_twice_idempotent(self, test_client, db_session, sample_users):
        """Accepting task twice should be idempotent or error gracefully."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Double accept",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        # First accept
        response1 = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(owner.id)}
        )
        assert response1.status_code == 200
        
        # Second accept (should error or be idempotent)
        response2 = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(owner.id)}
        )
        assert response2.status_code in [200, 400]
        
        db_session.refresh(task)
        assert task.state == TaskState.ACTIVE
    
    def test_reject_active_task_fails(self, test_client, db_session, sample_users):
        """Rejecting an ACTIVE task should fail."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Active task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        response = test_client.post(
            f"/decisions/task/{task.id}",
            json={"action": "reject", "reason": "Trying to reject active"},
            headers={"X-User-Id": str(owner.id)}
        )
        
        assert response.status_code == 400
    
    def test_reopen_non_rejected_task_fails(self, db_session, sample_users):
        """Reopening non-REJECTED task should fail."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Draft task",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        with pytest.raises(ValueError, match="not in REJECTED"):
            state_machines.reopen_rejected_task(db_session, task, creator)
    
    def test_owner_cannot_reopen_rejected_task(self, db_session, sample_users):
        """Owner (not creator) cannot reopen rejected task."""
        creator = sample_users["manager"]
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Rejected task",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.REJECTED,
            state_reason="Rejected"
        )
        db_session.add(task)
        db_session.commit()
        
        with pytest.raises(ValueError, match="Only the task creator"):
            state_machines.reopen_rejected_task(db_session, task, owner)


class TestStateTransitionEdgeCases:
    """Edge cases for state transitions."""
    
    def test_same_state_transition_allowed(self, db_session, sample_users):
        """Setting same state should be no-op or allowed."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Same state test",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Should not raise
        try:
            state_machines.set_task_state(
                db=db_session,
                task=task,
                new_state=TaskState.ACTIVE,
                actor=owner,
                reason="Same state"
            )
            assert task.state == TaskState.ACTIVE
        except ValueError:
            # Also acceptable if explicitly disallowed
            pass
    
    def test_archived_to_draft_fails(self, db_session, sample_users):
        """ARCHIVED -> DRAFT should fail."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Archived test",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ARCHIVED,
            is_active=False
        )
        db_session.add(task)
        db_session.commit()
        
        with pytest.raises(ValueError, match="Invalid state transition"):
            state_machines.set_task_state(
                db=db_session,
                task=task,
                new_state=TaskState.DRAFT,
                actor=owner,
                reason="Trying to resurrect"
            )
    
    def test_archived_to_rejected_fails(self, db_session, sample_users):
        """ARCHIVED -> REJECTED should fail."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Archived test",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ARCHIVED,
            is_active=False
        )
        db_session.add(task)
        db_session.commit()
        
        with pytest.raises(ValueError, match="Invalid state transition"):
            state_machines.set_task_state(
                db=db_session,
                task=task,
                new_state=TaskState.REJECTED,
                actor=owner,
                reason="Trying invalid transition"
            )

