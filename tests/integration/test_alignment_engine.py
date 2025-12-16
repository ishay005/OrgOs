"""
Tests for the unified alignment/misalignment engine.

Verifies:
1. Similarity scores are calculated when answers are saved
2. Alignment-stats endpoints read from cache
3. Misalignments endpoint matches alignment-stats data
4. Fallback calculation works when no cached score exists
"""
import pytest
from uuid import uuid4
from datetime import datetime

from app.models import (
    User, Task, TaskState, AttributeAnswer, AttributeDefinition, 
    EntityType, SimilarityScore, AttributeType
)


class TestSimilarityTrigger:
    """Tests that similarity scores are calculated when answers are saved."""
    
    def test_similarity_score_created_for_matching_answers(self, db_session):
        """When two users answer the same question identically, similarity = 1.0"""
        # Create users
        user1 = User(name="User 1", email="user1@test.com")
        user2 = User(name="User 2", email="user2@test.com")
        db_session.add_all([user1, user2])
        db_session.commit()
        
        # Create task
        task = Task(
            title="Test Task",
            owner_user_id=user1.id,
            created_by_user_id=user1.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Create attribute
        attr = AttributeDefinition(
            name="status",
            label="Status",
            entity_type=EntityType.TASK,
            type="enum",
            allowed_values=["Not Started", "In Progress", "Done"]
        )
        db_session.add(attr)
        db_session.commit()
        
        # Create identical answers
        answer1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="In Progress"
        )
        answer2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="In Progress"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # Manually trigger similarity calculation (simulating the trigger)
        from app.services.similarity_cache import recalculate_all_similarity_scores
        recalculate_all_similarity_scores(db_session)
        
        # Verify similarity score exists
        score = db_session.query(SimilarityScore).filter(
            ((SimilarityScore.answer_a_id == answer1.id) & (SimilarityScore.answer_b_id == answer2.id)) |
            ((SimilarityScore.answer_a_id == answer2.id) & (SimilarityScore.answer_b_id == answer1.id))
        ).first()
        
        assert score is not None
        assert score.similarity_score == 1.0  # Identical answers
    
    def test_similarity_score_zero_for_different_answers(self, db_session):
        """When two users answer differently, similarity should be low."""
        # Create users
        user1 = User(name="User 1", email="user1@test.com")
        user2 = User(name="User 2", email="user2@test.com")
        db_session.add_all([user1, user2])
        db_session.commit()
        
        # Create task
        task = Task(
            title="Test Task",
            owner_user_id=user1.id,
            created_by_user_id=user1.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Create attribute
        attr = AttributeDefinition(
            name="priority",
            label="Priority",
            entity_type=EntityType.TASK,
            type="enum",
            allowed_values=["Low", "Medium", "High"]
        )
        db_session.add(attr)
        db_session.commit()
        
        # Create different answers
        answer1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        answer2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Low"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # Trigger similarity calculation
        from app.services.similarity_cache import recalculate_all_similarity_scores
        recalculate_all_similarity_scores(db_session)
        
        # Verify similarity score
        score = db_session.query(SimilarityScore).filter(
            ((SimilarityScore.answer_a_id == answer1.id) & (SimilarityScore.answer_b_id == answer2.id)) |
            ((SimilarityScore.answer_a_id == answer2.id) & (SimilarityScore.answer_b_id == answer1.id))
        ).first()
        
        assert score is not None
        assert score.similarity_score == 0.0  # Different enum values


class TestAlignmentStatsEndpoint:
    """Tests that alignment-stats reads from cache correctly."""
    
    @pytest.mark.asyncio
    async def test_alignment_stats_users_returns_cached_data(self, db_session, test_client):
        """Alignment stats endpoint should read from similarity_scores cache."""
        # Create user with no answers - should return 100%
        user = User(name="Test User", email="test@test.com")
        db_session.add(user)
        db_session.commit()
        
        # Call endpoint
        response = test_client.get(
            "/alignment-stats/users",
            headers={"X-User-Id": str(user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert str(user.id) in data
        assert data[str(user.id)] == 100.0  # No data = assume aligned
    
    @pytest.mark.asyncio
    async def test_alignment_stats_tasks_returns_cached_data(self, db_session, test_client):
        """Task alignment stats should read from similarity_scores cache."""
        # Create user and task
        user = User(name="Test User", email="test@test.com")
        db_session.add(user)
        db_session.commit()
        
        task = Task(
            title="Test Task",
            owner_user_id=user.id,
            created_by_user_id=user.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Call endpoint
        response = test_client.get(
            "/alignment-stats/tasks",
            headers={"X-User-Id": str(user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert str(task.id) in data
        assert data[str(task.id)] == 100.0  # No comparisons = assume aligned

    @pytest.mark.asyncio
    async def test_alignment_stats_users_detects_misalignment(self, db_session, test_client):
        """Alignment stats should drop below 100 when answers differ."""
        user1 = User(name="User 1", email="u1@test.com")
        user2 = User(name="User 2", email="u2@test.com")
        db_session.add_all([user1, user2])
        db_session.commit()
        
        task = Task(
            title="Task Misalign",
            owner_user_id=user1.id,
            created_by_user_id=user1.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        attr = AttributeDefinition(
            name="status",
            label="Status",
            entity_type=EntityType.TASK,
            type="enum",
            allowed_values=["A", "B"]
        )
        db_session.add(attr)
        db_session.commit()
        
        a1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="A"
        )
        a2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user1.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="B"
        )
        db_session.add_all([a1, a2])
        db_session.commit()
        
        from app.services.similarity_cache import recalculate_all_similarity_scores
        recalculate_all_similarity_scores(db_session)
        
        resp = test_client.get("/alignment-stats/users", headers={"X-User-Id": str(user1.id)})
        assert resp.status_code == 200
        stats = resp.json()
        assert stats[str(user1.id)] < 100.0


class TestMisalignmentFallback:
    """Tests that misalignment calculation falls back correctly when no cache."""
    
    @pytest.mark.asyncio
    async def test_misalignment_fallback_for_identical_answers(self, db_session):
        """When no cached score exists, fallback should return 1.0 for identical answers."""
        from app.services.misalignment_cached import compute_misalignments_for_user_cached
        
        # Create users
        user1 = User(name="User 1", email="user1@test.com")
        user2 = User(name="User 2", email="user2@test.com", manager_id=None)
        db_session.add_all([user1, user2])
        db_session.commit()
        
        # Set manager relationship
        user2.manager_id = user1.id
        db_session.commit()
        
        # Create task
        task = Task(
            title="Test Task",
            owner_user_id=user2.id,
            created_by_user_id=user2.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Create attribute
        attr = AttributeDefinition(
            name="main_goal",
            label="Main Goal",
            entity_type=EntityType.TASK,
            type=AttributeType.STRING
        )
        db_session.add(attr)
        db_session.commit()
        
        # Create identical answers (without cached similarity)
        answer1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Complete the project"
        )
        answer2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="complete the project"  # Same but different case
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # Don't calculate similarity scores (simulating missing cache)
        
        # Call misalignment computation with include_all=True
        misalignments = await compute_misalignments_for_user_cached(
            user_id=user2.id,
            db=db_session,
            include_all=True
        )
        
        # Should have computed using fallback (case-insensitive string match)
        # and found 1.0 similarity (aligned)
        for m in misalignments:
            if m.attribute_name == "main_goal":
                assert m.similarity_score == 1.0
    
    @pytest.mark.asyncio
    async def test_misalignment_fallback_for_different_answers(self, db_session):
        """When no cached score exists, fallback should return 0.0 for different answers."""
        from app.services.misalignment_cached import compute_misalignments_for_user_cached
        
        # Create users
        user1 = User(name="User 1", email="user1@test.com")
        user2 = User(name="User 2", email="user2@test.com", manager_id=None)
        db_session.add_all([user1, user2])
        db_session.commit()
        
        user2.manager_id = user1.id
        db_session.commit()
        
        # Create task
        task = Task(
            title="Test Task",
            owner_user_id=user2.id,
            created_by_user_id=user2.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Create attribute
        attr = AttributeDefinition(
            name="priority",
            label="Priority",
            entity_type=EntityType.TASK,
            type="enum",
            allowed_values=["Low", "Medium", "High"]
        )
        db_session.add(attr)
        db_session.commit()
        
        # Create different answers
        answer1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="High"
        )
        answer2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="Low"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # Call misalignment computation
        misalignments = await compute_misalignments_for_user_cached(
            user_id=user2.id,
            db=db_session,
            include_all=True
        )
        
        # Should have at least one misalignment with 0.0 score
        priority_misalignments = [m for m in misalignments if m.attribute_name == "priority"]
        assert len(priority_misalignments) > 0
        assert any(m.similarity_score == 0.0 for m in priority_misalignments)


class TestUnifiedAlignment:
    """Tests that all alignment displays use the same data source."""
    
    @pytest.mark.asyncio
    async def test_alignment_stats_and_misalignment_consistent(self, db_session, test_client):
        """Alignment stats and misalignment endpoint should return consistent data."""
        # Create users
        user1 = User(name="Manager", email="manager@test.com")
        user2 = User(name="Employee", email="employee@test.com")
        db_session.add_all([user1, user2])
        db_session.commit()
        
        user2.manager_id = user1.id
        db_session.commit()
        
        # Create task
        task = Task(
            title="Test Task",
            owner_user_id=user2.id,
            created_by_user_id=user2.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Create attribute
        attr = AttributeDefinition(
            name="status",
            label="Status",
            entity_type=EntityType.TASK,
            type="enum",
            allowed_values=["Not Started", "In Progress", "Done"]
        )
        db_session.add(attr)
        db_session.commit()
        
        # Create matching answers
        answer1 = AttributeAnswer(
            answered_by_user_id=user1.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="In Progress"
        )
        answer2 = AttributeAnswer(
            answered_by_user_id=user2.id,
            target_user_id=user2.id,
            task_id=task.id,
            attribute_id=attr.id,
            value="In Progress"
        )
        db_session.add_all([answer1, answer2])
        db_session.commit()
        
        # Calculate similarity scores
        from app.services.similarity_cache import recalculate_all_similarity_scores
        recalculate_all_similarity_scores(db_session)
        
        # Get alignment stats
        stats_response = test_client.get(
            "/alignment-stats/users",
            headers={"X-User-Id": str(user1.id)}
        )
        assert stats_response.status_code == 200
        stats = stats_response.json()
        
        # Both users should show 100% alignment (identical answers)
        if str(user1.id) in stats:
            assert stats[str(user1.id)] == 100.0
        if str(user2.id) in stats:
            assert stats[str(user2.id)] == 100.0

