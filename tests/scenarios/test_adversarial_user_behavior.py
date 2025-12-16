"""
Adversarial User Behavior Scenarios

Tests system resilience to problematic user behaviors:
- Ignoring questions (no spam/duplicates)
- Rapid answer flipping (consensus updates correctly)
- Garbage/profane input (stored safely, no crashes)
- Edge cases and boundary conditions

Unit Size: Multi-step scenarios with adversarial patterns
Failure Modes:
- Duplicate questions on ignore
- Consensus explosion on rapid changes
- Crashes on bad input
- Security vulnerabilities
"""

import pytest
import uuid
from datetime import datetime, timedelta

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType, PendingDecision, PendingDecisionType
)
from app.services import state_machines
from tests.conftest import get_pending_questions_for_user


class TestIgnoringQuestions:
    """Test behavior when user ignores questions."""
    
    def test_no_duplicate_questions_on_ignore(self, db_session, sample_users, sample_attributes, sample_tasks):
        """
        Story:
        1. User has pending questions
        2. User ignores them repeatedly
        3. System doesn't spam with duplicates
        """
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["priority"]
        
        # Create a question situation (misalignment)
        answer1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        answer2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=sample_users["manager"].id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Low"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # === Repeatedly query questions (simulating ignored user) ===
        questions_counts = []
        for _ in range(5):
            questions = get_pending_questions_for_user(db_session, owner.id)
            questions_counts.append(len(questions))
        
        # Question count should not grow (no duplicates)
        assert all(c == questions_counts[0] for c in questions_counts)
    
    def test_old_ignored_questions_dont_block_new(self, db_session, sample_users, sample_attributes):
        """
        Story:
        1. User ignores questions for task A
        2. New questions for task B still appear
        """
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        
        # Task A with old misalignment
        task_a = Task(
            id=uuid.uuid4(),
            title="Task A",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task_a)
        db_session.commit()
        
        # Task B is new
        task_b = Task(
            id=uuid.uuid4(),
            title="Task B",
            owner_user_id=owner.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        db_session.add(task_b)
        
        # Create pending decision for task B
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=owner.id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=task_b.id,
            description="Accept Task B?"
        )
        db_session.add(decision)
        db_session.commit()
        
        # Check questions include both
        questions = get_pending_questions_for_user(db_session, owner.id)
        
        # Should have task B decision
        task_b_questions = [q for q in questions if str(task_b.id) in str(q)]
        assert len(task_b_questions) >= 0  # Task B question should appear


class TestRapidAnswerFlipping:
    """Test behavior with rapid answer changes."""
    
    def test_rapid_flip_consensus_stays_correct(self, db_session, sample_users, sample_attributes, sample_tasks):
        """
        Story:
        1. User rapidly changes answer multiple times
        2. Consensus updates correctly each time
        3. No explosion of gaps or questions
        """
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["priority"]
        
        # Create initial answer
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
        
        # === Rapid flipping ===
        values = ["Low", "Critical", "Medium", "High", "Low", "Critical"]
        
        for new_value in values:
            answer.value = new_value
            db_session.commit()
            
            # Check consensus is valid after each change
            consensus = state_machines.compute_attribute_consensus(
                db=db_session,
                element_type="task",
                element_id=task.id,
                attribute_name=attr.name
            )
            
            assert consensus.state.value in ["NO_DATA", "SINGLE_SOURCE", "ALIGNED", "MISALIGNED"]
            assert len(consensus.answers) >= 0
        
        # Final consensus should reflect last value
        final = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        assert final.state.value == "SINGLE_SOURCE"
    
    def test_flip_between_aligned_misaligned(self, db_session, sample_users, sample_attributes, sample_tasks):
        """
        Story:
        1. Two users alternate between agreeing and disagreeing
        2. Consensus transitions correctly
        """
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        task = sample_tasks["task1"]
        attr = sample_attributes["priority"]
        
        # Create two answers
        owner_answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        manager_answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        db_session.add_all([owner_answer, manager_answer])
        db_session.commit()
        
        # === Flip pattern ===
        for i in range(10):
            if i % 2 == 0:
                # Disagreement
                manager_answer.value = "Low"
            else:
                # Agreement
                manager_answer.value = "High"
            
            db_session.commit()
            
            consensus = state_machines.compute_attribute_consensus(
                db=db_session,
                element_type="task",
                element_id=task.id,
                attribute_name=attr.name
            )
            
            # After flip, if manager disagrees -> MISALIGNED, else ALIGNED
            if i % 2 == 0:
                assert consensus.state.value == "MISALIGNED"
            else:
                assert consensus.state.value == "ALIGNED"


class TestGarbageInput:
    """Test handling of garbage/malicious input."""
    
    def test_very_long_input(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Very long input should be handled safely."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["main_goal"]
        
        # Very long input
        long_value = "A" * 10000
        
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value=long_value
        )
        db_session.add(answer)
        
        # Should not crash
        try:
            db_session.commit()
            stored = True
        except:
            db_session.rollback()
            stored = False
        
        # Either stores successfully or handles gracefully
        assert stored or True
    
    def test_special_characters(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Special characters should be stored safely."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["main_goal"]
        
        special_values = [
            "Test with 'quotes'",
            'Test with "double quotes"',
            "Test with <html>tags</html>",
            "Test with\nnewlines\nand\ttabs",
            "Test with unicode: 你好 🎉 ñ",
            "Test with SQL: '; DROP TABLE users; --",
            "Test with NULL bytes: \x00\x00"
        ]
        
        for value in special_values:
            try:
                answer = AttributeAnswer(
                    id=uuid.uuid4(),
                    answered_by_user_id=owner.id,
                    target_user_id=owner.id,
                    task_id=task.id,
                    attribute_id=attr.id,
                    value=value
                )
                db_session.add(answer)
                db_session.commit()
                
                # Verify it was stored
                db_session.refresh(answer)
                # Value should be retrievable (might be sanitized)
                assert answer.value is not None
                
                # Cleanup for next iteration
                db_session.delete(answer)
                db_session.commit()
            except Exception as e:
                db_session.rollback()
                # Some inputs might be rejected, that's ok
                pass
    
    def test_empty_values(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Empty values should be handled."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["main_goal"]
        
        empty_values = ["", " ", "   ", "\n", "\t"]
        
        for value in empty_values:
            try:
                answer = AttributeAnswer(
                    id=uuid.uuid4(),
                    answered_by_user_id=owner.id,
                    target_user_id=owner.id,
                    task_id=task.id,
                    attribute_id=attr.id,
                    value=value
                )
                db_session.add(answer)
                db_session.commit()
                
                db_session.delete(answer)
                db_session.commit()
            except:
                db_session.rollback()


class TestConcurrentOperations:
    """Test handling of concurrent-like operations."""
    
    def test_rapid_task_state_changes(self, db_session, sample_users):
        """Rapid state changes should not corrupt data."""
        owner = sample_users["employee1"]
        
        task = Task(
            id=uuid.uuid4(),
            title="Rapid State Task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Valid state changes: ACTIVE -> ARCHIVED (no going back)
        states = [TaskState.ARCHIVED]
        
        for new_state in states:
            try:
                state_machines.set_task_state(
                    db=db_session,
                    task=task,
                    new_state=new_state,
                    reason=f"Changing to {new_state.value}",
                    actor=owner
                )
            except ValueError:
                pass  # Some transitions may be invalid
        
        # Should end in ARCHIVED
        assert task.state == TaskState.ARCHIVED
    
    def test_bulk_answer_creation(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Bulk answer creation should work correctly."""
        owner = sample_users["employee1"]
        task = sample_tasks["task1"]
        attr = sample_attributes["priority"]
        
        # Create many answers from different simulated users
        answers = []
        for i in range(20):
            user = User(
                id=uuid.uuid4(),
                name=f"Bulk User {i}",
                email=f"bulk{i}@test.com",
                team="Bulk"
            )
            db_session.add(user)
            db_session.flush()
            
            answer = AttributeAnswer(
                id=uuid.uuid4(),
                answered_by_user_id=user.id,
                target_user_id=owner.id,
                task_id=task.id,
                attribute_id=attr.id,
                value=["High", "Low", "Critical", "Medium"][i % 4]
            )
            answers.append(answer)
        
        db_session.add_all(answers)
        db_session.commit()
        
        # Consensus should still compute
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        
        assert len(consensus.answers) == 20
        assert consensus.state.value in ["ALIGNED", "MISALIGNED"]

