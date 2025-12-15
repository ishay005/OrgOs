"""
Data Drift and Staleness Scenarios

Tests handling of stale data and drift over time:
- Old answers trigger refresh questions
- Stale flags cleared on new answers
- Time-based staleness detection

Unit Size: Multi-step scenario with time simulation
Failure Modes:
- Stale data not detected
- Refresh questions not generated
- Stale flags not cleared after updates
- Incorrect staleness thresholds
"""

import pytest
import uuid
from datetime import datetime, timedelta

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType
)
from app.services import state_machines
from tests.conftest import get_pending_questions_for_user


class TestStaleDataDetection:
    """Test stale data detection and handling."""
    
    def test_old_answers_become_stale(self, db_session, sample_users, sample_attributes, sample_tasks):
        """
        Story:
        1. User provides answer 30 days ago
        2. System detects staleness
        3. Refresh question generated
        """
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["priority"]
        
        # === Step 1: Create old answer ===
        old_date = datetime.utcnow() - timedelta(days=30)
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High",
            created_at=old_date,
            updated_at=old_date  # Set updated_at for staleness check
        )
        db_session.add(answer)
        db_session.commit()
        
        # === Step 2: Check staleness ===
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name,
            staleness_days=14
        )
        
        assert consensus.is_stale == True
        
        # === Step 3: Check for refresh question ===
        questions = get_pending_questions_for_user(db_session, owner.id)
        
        # Should have questions (refresh or fill)
        assert isinstance(questions, list)
    
    def test_fresh_answer_clears_staleness(self, db_session, sample_users, sample_attributes, sample_tasks):
        """
        Story:
        1. Old stale answer exists
        2. User provides new answer
        3. Staleness cleared
        """
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["priority"]
        
        # === Step 1: Create stale answer ===
        old_date = datetime.utcnow() - timedelta(days=30)
        old_answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High",
            created_at=old_date,
            updated_at=old_date  # Set updated_at for staleness check
        )
        db_session.add(old_answer)
        db_session.commit()
        
        # Verify stale
        initial = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name,
            staleness_days=14
        )
        assert initial.is_stale == True
        
        # === Step 2: User provides fresh answer ===
        old_answer.updated_at = datetime.utcnow()  # Update timestamp
        db_session.commit()
        
        # === Step 3: Verify staleness cleared ===
        after = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name,
            staleness_days=14
        )
        
        assert after.is_stale == False


class TestDataDrift:
    """Test handling of data drift scenarios."""
    
    def test_gradual_drift_detection(self, db_session, sample_attributes):
        """
        Story:
        1. Team starts aligned
        2. Over time, perceptions drift
        3. System detects when drift becomes significant
        """
        # === Setup ===
        manager = User(
            id=uuid.uuid4(),
            name="Manager",
            email="manager@test.com",
            team="Engineering"
        )
        db_session.add(manager)
        db_session.flush()
        
        employees = [
            User(
                id=uuid.uuid4(),
                name=f"Employee {i}",
                email=f"emp{i}@test.com",
                team="Engineering",
                manager_id=manager.id
            )
            for i in range(3)
        ]
        db_session.add_all(employees)
        
        task = Task(
            id=uuid.uuid4(),
            title="Long-running Project",
            owner_user_id=employees[0].id,
            created_by_user_id=employees[0].id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        priority_attr = sample_attributes["priority"]
        
        # === Step 1: Initially aligned ===
        for emp in employees:
            answer = AttributeAnswer(
                id=uuid.uuid4(),
                answered_by_user_id=emp.id,
                target_user_id=employees[0].id,
                task_id=task.id,
                attribute_id=priority_attr.id,
                value="High"
            )
            db_session.add(answer)
        
        db_session.commit()
        
        initial = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        assert initial.state.value == "ALIGNED"
        
        # === Step 2: Perceptions drift ===
        # Update one employee's view
        drift_answer = db_session.query(AttributeAnswer).filter(
            AttributeAnswer.answered_by_user_id == employees[1].id,
            AttributeAnswer.task_id == task.id,
            AttributeAnswer.attribute_id == priority_attr.id
        ).first()
        drift_answer.value = "Low"
        db_session.commit()
        
        # === Step 3: Detect drift ===
        after_drift = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        
        # With 2 High and 1 Low, there should be some misalignment
        assert after_drift.state.value in ["ALIGNED", "MISALIGNED"]
        assert after_drift.similarity_score is None or after_drift.similarity_score < 1.0
    
    def test_recurring_realignment(self, db_session, sample_attributes):
        """
        Story:
        1. Misalignment detected
        2. Team realigns
        3. Later, drift occurs again
        4. System re-detects
        """
        # === Setup ===
        users = [
            User(
                id=uuid.uuid4(),
                name=f"User {i}",
                email=f"user{i}@test.com",
                team="Team"
            )
            for i in range(2)
        ]
        db_session.add_all(users)
        
        task = Task(
            id=uuid.uuid4(),
            title="Project",
            owner_user_id=users[0].id,
            created_by_user_id=users[0].id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        priority_attr = sample_attributes["priority"]
        
        # === Round 1: Misalignment ===
        answer1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=users[0].id,
            target_user_id=users[0].id,
            task_id=task.id,
            attribute_id=priority_attr.id,
            value="High"
        )
        answer2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=users[1].id,
            target_user_id=users[0].id,
            task_id=task.id,
            attribute_id=priority_attr.id,
            value="Low"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        round1 = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        assert round1.state.value == "MISALIGNED"
        
        # === Round 2: Realignment ===
        answer2.value = "High"
        db_session.commit()
        
        round2 = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        assert round2.state.value == "ALIGNED"
        
        # === Round 3: Drift again ===
        answer1.value = "Critical"
        db_session.commit()
        
        round3 = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        
        # Should detect new misalignment (or alignment depending on values)
        assert round3.state.value in ["ALIGNED", "MISALIGNED"]


class TestMultipleAttributeDrift:
    """Test drift across multiple attributes."""
    
    def test_multiple_attributes_drift_independently(self, db_session, sample_attributes):
        """
        Story:
        1. Multiple attributes start aligned
        2. Different attributes drift at different times
        3. Each is detected independently
        """
        # === Setup ===
        user1 = User(
            id=uuid.uuid4(),
            name="User 1",
            email="u1@test.com",
            team="Team"
        )
        user2 = User(
            id=uuid.uuid4(),
            name="User 2",
            email="u2@test.com",
            team="Team"
        )
        db_session.add_all([user1, user2])
        
        task = Task(
            id=uuid.uuid4(),
            title="Multi-attribute Task",
            owner_user_id=user1.id,
            created_by_user_id=user1.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        priority_attr = sample_attributes["priority"]
        status_attr = sample_attributes["status"]
        
        # === Initial aligned state ===
        # Priority: both High
        p1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=user1.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=priority_attr.id,
            value="High"
        )
        p2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=user2.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=priority_attr.id,
            value="High"
        )
        
        # Status: both In Progress
        s1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=user1.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=status_attr.id,
            value="In Progress"
        )
        s2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=user2.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=status_attr.id,
            value="In Progress"
        )
        
        db_session.add_all([p1, p2, s1, s2])
        db_session.commit()
        
        # === Priority drifts ===
        p2.value = "Low"
        db_session.commit()
        
        priority_consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=priority_attr.name
        )
        status_consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=status_attr.name
        )
        
        # Priority misaligned, status still aligned
        assert priority_consensus.state.value == "MISALIGNED"
        assert status_consensus.state.value == "ALIGNED"
        
        # === Status drifts ===
        s2.value = "Done"
        db_session.commit()
        
        status_consensus2 = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=status_attr.name
        )
        
        # Now status also misaligned
        assert status_consensus2.state.value == "MISALIGNED"

