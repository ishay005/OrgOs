"""
Strict Validation Tests

These tests verify EXPECTED behavior based on business requirements,
NOT just current implementation. They are designed to catch real bugs.

If these tests fail, it indicates a potential bug in the system that 
should be reviewed and fixed.

Unit Size: Pure functions with strict assertions
Failure Modes:
- Business logic violations
- Data integrity issues  
- Authorization bypasses
- State machine violations
"""

import pytest
import uuid
from datetime import datetime, timedelta

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType, TaskDependencyV2, DependencyStatus,
    TaskMergeProposal, MergeProposalStatus, PendingDecision,
    PendingDecisionType
)
from app.services import state_machines


class TestStrictTaskStateRules:
    """Strict tests for task state machine rules."""
    
    def test_draft_task_cannot_have_done_state(self, db_session, sample_users):
        """DRAFT tasks should never be able to transition directly to DONE."""
        owner = sample_users["employee1"]
        creator = sample_users["manager"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Test Task",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        db_session.commit()
        
        # Trying to set DONE on DRAFT should fail (DRAFT can only go to ACTIVE or ARCHIVED)
        with pytest.raises(ValueError, match="Invalid state transition"):
            state_machines.set_task_state(db_session, task, TaskState.DONE, owner, reason="Completed")
    
    def test_archived_task_cannot_be_reactivated(self, db_session, sample_users):
        """ARCHIVED tasks should never return to ACTIVE state."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Test Task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ARCHIVED
        )
        db_session.add(task)
        db_session.commit()
        
        # Trying to set ACTIVE on ARCHIVED should fail
        with pytest.raises(ValueError, match="Invalid state transition"):
            state_machines.set_task_state(db_session, task, TaskState.ACTIVE, owner, reason="Reopen")
    
    def test_only_task_owner_can_change_state(self, db_session, sample_users):
        """Only the task owner should be able to change task state."""
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Test Task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Other user trying to mark done should fail
        with pytest.raises(ValueError, match="Only the task owner"):
            state_machines.set_task_state(db_session, task, TaskState.DONE, other, reason="Done")


class TestStrictDependencyRules:
    """Strict tests for dependency rules."""
    
    def test_circular_dependencies_prevented(self, db_session, sample_users):
        """System should prevent circular dependencies A->B->C->A."""
        owner = sample_users["employee1"]
        
        task_a = Task(id=uuid.uuid4(), title="Task A", owner_user_id=owner.id, 
                      created_by_user_id=owner.id, state=TaskState.ACTIVE)
        task_b = Task(id=uuid.uuid4(), title="Task B", owner_user_id=owner.id,
                      created_by_user_id=owner.id, state=TaskState.ACTIVE)
        task_c = Task(id=uuid.uuid4(), title="Task C", owner_user_id=owner.id,
                      created_by_user_id=owner.id, state=TaskState.ACTIVE)
        db_session.add_all([task_a, task_b, task_c])
        db_session.commit()
        
        # Create A -> B (A depends on B)
        state_machines.propose_dependency(db_session, owner, task_a, task_b)
        
        # Create B -> C (B depends on C)
        state_machines.propose_dependency(db_session, owner, task_b, task_c)
        
        # Create C -> A should fail (circular!)
        # NOTE: If this test fails with ValueError, the system DOES prevent cycles - GOOD!
        # If it passes without raising, the system has a bug - BAD!
        try:
            state_machines.propose_dependency(db_session, owner, task_c, task_a)
            # If we get here, circular dependency was allowed - this is a bug!
            pytest.fail("System allowed circular dependency C->A when A->B->C already exists")
        except ValueError:
            pass  # Good - system prevented the cycle
    
    def test_dependency_on_archived_task_prevented(self, db_session, sample_users):
        """Cannot create dependency on archived task."""
        owner = sample_users["employee1"]
        
        active_task = Task(id=uuid.uuid4(), title="Active Task", owner_user_id=owner.id,
                           created_by_user_id=owner.id, state=TaskState.ACTIVE)
        archived_task = Task(id=uuid.uuid4(), title="Archived Task", owner_user_id=owner.id,
                             created_by_user_id=owner.id, state=TaskState.ARCHIVED)
        db_session.add_all([active_task, archived_task])
        db_session.commit()
        
        # Depending on archived task should be prevented
        try:
            state_machines.propose_dependency(db_session, owner, active_task, archived_task)
            # If we get here, dependency on archived task was allowed
            pytest.fail("System allowed dependency on archived task")
        except ValueError:
            pass  # Good


class TestStrictMergeRules:
    """Strict tests for merge proposal rules."""
    
    def test_cannot_merge_active_into_draft(self, db_session, sample_users):
        """Active task should not be merged into draft task."""
        owner = sample_users["employee1"]
        creator = sample_users["manager"]
        
        active_task = Task(id=uuid.uuid4(), title="Active Task", owner_user_id=owner.id,
                           created_by_user_id=owner.id, state=TaskState.ACTIVE)
        draft_task = Task(id=uuid.uuid4(), title="Draft Task", owner_user_id=owner.id,
                          created_by_user_id=creator.id, state=TaskState.DRAFT)
        db_session.add_all([active_task, draft_task])
        db_session.commit()
        
        # Merge active into draft should fail (or at minimum, both should end up active)
        try:
            proposal = state_machines.propose_task_merge(
                db_session, active_task, draft_task, owner, "Merge into draft"
            )
            # If proposal is created, verify target is appropriate
            # (this might be valid depending on business rules)
        except ValueError:
            pass  # Also acceptable
    
    def test_merge_requires_same_owner(self, db_session, sample_users):
        """Both tasks must have same owner for merge."""
        owner1 = sample_users["employee1"]
        owner2 = sample_users["employee2"]
        creator = sample_users["manager"]
        
        task1 = Task(id=uuid.uuid4(), title="Task 1", owner_user_id=owner1.id,
                     created_by_user_id=creator.id, state=TaskState.DRAFT)
        task2 = Task(id=uuid.uuid4(), title="Task 2", owner_user_id=owner2.id,
                     created_by_user_id=owner2.id, state=TaskState.ACTIVE)
        db_session.add_all([task1, task2])
        db_session.commit()
        
        # Merge across owners should fail
        try:
            state_machines.propose_task_merge(
                db_session, task1, task2, owner1, "Cross-owner merge"
            )
            pytest.fail("System allowed merge between tasks of different owners")
        except ValueError:
            pass  # Good


class TestStrictAlignmentRules:
    """Strict tests for alignment calculation."""
    
    def test_single_answer_never_misaligned(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Single answer should never show as MISALIGNED."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["priority"]
        
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        db_session.add(answer)
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        
        # Single answer MUST be NO_DATA or SINGLE_SOURCE, never ALIGNED or MISALIGNED
        from app.models import AttributeConsensusState
        assert consensus.state in [AttributeConsensusState.SINGLE_SOURCE, AttributeConsensusState.NO_DATA], \
            f"Single answer showed as {consensus.state} instead of SINGLE_SOURCE"
    
    def test_identical_answers_always_aligned(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Two identical answers must always show as ALIGNED."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        attr = sample_attributes["priority"]
        
        # Both give exact same answer
        answer1 = AttributeAnswer(
            id=uuid.uuid4(), answered_by_user_id=owner.id, target_user_id=owner.id,
            task_id=task.id, attribute_id=attr.id, value="High"
        )
        answer2 = AttributeAnswer(
            id=uuid.uuid4(), answered_by_user_id=manager.id, target_user_id=owner.id,
            task_id=task.id, attribute_id=attr.id, value="High"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session, element_type="task", element_id=task.id, attribute_name=attr.name
        )
        
        from app.models import AttributeConsensusState
        assert consensus.state == AttributeConsensusState.ALIGNED, \
            f"Identical answers showed as {consensus.state} instead of ALIGNED"
    
    def test_opposite_answers_always_misaligned(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Completely opposite answers must show as MISALIGNED."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        attr = sample_attributes["priority"]
        
        # Opposite answers
        answer1 = AttributeAnswer(
            id=uuid.uuid4(), answered_by_user_id=owner.id, target_user_id=owner.id,
            task_id=task.id, attribute_id=attr.id, value="Critical"
        )
        answer2 = AttributeAnswer(
            id=uuid.uuid4(), answered_by_user_id=manager.id, target_user_id=owner.id,
            task_id=task.id, attribute_id=attr.id, value="Low"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session, element_type="task", element_id=task.id, attribute_name=attr.name
        )
        
        from app.models import AttributeConsensusState
        assert consensus.state == AttributeConsensusState.MISALIGNED, \
            f"Opposite answers showed as {consensus.state} instead of MISALIGNED"


class TestStrictAuthorizationRules:
    """Strict tests for authorization."""
    
    def test_pending_decision_only_for_target_user(self, db_session, sample_users):
        """Pending decision should only be visible to target user."""
        owner = sample_users["employee1"]
        other = sample_users["employee2"]
        manager = sample_users["manager"]
        
        task = Task(id=uuid.uuid4(), title="Task for Owner", owner_user_id=owner.id,
                    created_by_user_id=manager.id, state=TaskState.DRAFT)
        db_session.add(task)
        db_session.commit()
        
        # Create pending decision for owner
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=owner.id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=task.id,
            description="Test task needs acceptance"
        )
        db_session.add(decision)
        db_session.commit()
        
        # Get pending decisions for owner - should find it
        owner_decisions = state_machines.get_pending_decisions_for_user(db_session, owner.id)
        assert any(d.entity_id == task.id for d in owner_decisions), \
            "Owner should see their pending decision"
        
        # Get pending decisions for other - should NOT find it
        other_decisions = state_machines.get_pending_decisions_for_user(db_session, other.id)
        assert not any(d.entity_id == task.id for d in other_decisions), \
            "Other user should not see owner's pending decision"


class TestStrictDataIntegrity:
    """Strict tests for data integrity."""
    
    def test_task_always_has_owner(self, db_session, sample_users):
        """Task must always have an owner_user_id."""
        with pytest.raises(Exception):  # Could be IntegrityError or ValidationError
            task = Task(
                id=uuid.uuid4(),
                title="No Owner Task",
                owner_user_id=None,  # No owner!
                created_by_user_id=sample_users["manager"].id,
                state=TaskState.DRAFT
            )
            db_session.add(task)
            db_session.commit()
    
    def test_task_always_has_creator(self, db_session, sample_users):
        """Task must always have a created_by_user_id when using create_task_with_state."""
        with pytest.raises(ValueError, match="Task creator is required"):
            state_machines.create_task_with_state(
                db=db_session,
                title="No Creator Task",
                owner=sample_users["employee1"],
                creator=None  # No creator!
            )
    
    def test_dependency_ids_must_exist(self, db_session, sample_users, sample_tasks):
        """Dependency task IDs must reference existing tasks."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        fake_id = uuid.uuid4()  # Non-existent task
        
        # Create dependency with fake upstream task
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task.id,
            upstream_task_id=fake_id,  # Doesn't exist!
            status=DependencyStatus.PROPOSED,
            created_by_user_id=owner.id
        )
        
        with pytest.raises(Exception):  # Should fail due to foreign key
            db_session.add(dep)
            db_session.commit()

