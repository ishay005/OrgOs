"""
Attribute Consensus Unit Tests

Tests the compute_attribute_consensus function and related logic:
- NO_DATA: No answers exist
- SINGLE_SOURCE: Only one person has answered
- ALIGNED: Multiple answers agree
- MISALIGNED: Multiple answers disagree
- Stale detection based on timestamps

Unit Size: Pure function with DB fixtures
Failure Modes:
- Wrong consensus state calculation
- Stale answers not detected
- Alignment threshold misconfiguration
- Edge cases with identical values but different cases
"""

import pytest
import uuid
from datetime import datetime, timedelta

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType, AttributeConsensusState
)
from app.services import state_machines
from app.services.similarity import _fallback_string_similarity as calculate_similarity


class TestConsensusStates:
    """Test different consensus state calculations."""
    
    def test_no_data_when_no_answers(self, db_session, sample_users, sample_attributes, sample_tasks):
        """NO_DATA when no answers exist for an attribute."""
        task = sample_tasks["task1"]
        attr = sample_attributes["main_goal"]
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        
        assert consensus.state == AttributeConsensusState.NO_DATA
        assert len(consensus.answers) == 0
    
    def test_single_source_with_one_answer(self, db_session, sample_users, sample_attributes, sample_tasks):
        """SINGLE_SOURCE when only one person has answered."""
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
        
        assert consensus.state == AttributeConsensusState.SINGLE_SOURCE
        assert len(consensus.answers) == 1
    
    def test_aligned_when_answers_match(self, db_session, sample_users, sample_attributes, sample_tasks):
        """ALIGNED when multiple answers have the same value."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        attr = sample_attributes["priority"]
        
        # Both give same answer
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
            answered_by_user_id=manager.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        
        assert consensus.state == AttributeConsensusState.ALIGNED
        assert consensus.similarity_score >= 0.9
    
    def test_misaligned_when_answers_differ(self, db_session, sample_users, sample_attributes, sample_tasks):
        """MISALIGNED when answers disagree."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        attr = sample_attributes["priority"]
        
        # Different answers
        answer1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Low"
        )
        answer2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Critical"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        
        assert consensus.state == AttributeConsensusState.MISALIGNED


class TestStaleDetection:
    """Test stale answer detection."""
    
    def test_old_answer_is_stale(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Answers older than threshold should be marked stale."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["priority"]
        
        # Create old answer (30 days ago) - set both created_at and updated_at
        old_date = datetime.utcnow() - timedelta(days=30)
        old_answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High",
            created_at=old_date,
            updated_at=old_date  # This is what staleness check uses
        )
        db_session.add(old_answer)
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name,
            staleness_days=14
        )
        
        assert consensus.is_stale == True
    
    def test_recent_answer_not_stale(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Recent answers should not be marked stale."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["priority"]
        
        # Create recent answer
        now = datetime.utcnow()
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High",
            created_at=now,
            updated_at=now
        )
        db_session.add(answer)
        db_session.commit()
        
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name,
            staleness_days=14
        )
        
        assert consensus.is_stale == False


class TestConsensusTransitions:
    """Test consensus state transitions when new answers are added."""
    
    def test_no_data_to_single_source(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Adding first answer transitions from NO_DATA to SINGLE_SOURCE."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        attr = sample_attributes["main_goal"]
        
        # Initial state: NO_DATA
        initial = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        assert initial.state == AttributeConsensusState.NO_DATA
        
        # Add answer
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Complete the project"
        )
        db_session.add(answer)
        db_session.commit()
        
        # Now: SINGLE_SOURCE
        after = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        assert after.state == AttributeConsensusState.SINGLE_SOURCE
    
    def test_single_source_to_aligned(self, db_session, sample_users, sample_attributes, sample_tasks):
        """Adding matching answer transitions to ALIGNED."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        manager = sample_users["manager"]
        attr = sample_attributes["priority"]
        
        # First answer
        answer1 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=owner.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        db_session.add(answer1)
        db_session.commit()
        
        initial = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        assert initial.state == AttributeConsensusState.SINGLE_SOURCE
        
        # Add matching answer
        answer2 = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=owner.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        db_session.add(answer2)
        db_session.commit()
        
        after = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=task.id,
            attribute_name=attr.name
        )
        assert after.state == AttributeConsensusState.ALIGNED


class TestSimilarityCalculation:
    """Test the underlying similarity calculation."""
    
    def test_exact_match_is_100_percent(self):
        """Exact string match should be 100% similar."""
        score = calculate_similarity("High", "High")
        assert score == 1.0
    
    def test_different_strings_lower_score(self):
        """Different strings should have lower similarity."""
        score = calculate_similarity("Critical", "Low")
        assert score < 0.5
    
    def test_case_insensitive_comparison(self):
        """Comparison should handle case differences."""
        score = calculate_similarity("High", "high")
        assert score >= 0.9
    
    def test_empty_strings(self):
        """Empty strings should be handled gracefully."""
        # When both are empty, returns 0.0 (no characters to compare)
        score = calculate_similarity("", "")
        assert score == 0.0
        
        # When one is empty, returns 0.0
        score = calculate_similarity("High", "")
        assert score == 0.0
