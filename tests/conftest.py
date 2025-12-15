"""
OrgOs Test Configuration

This module provides fixtures and configuration for the entire test suite:
- Test database isolation (transaction rollback per test)
- Fake OpenAI client for mocking LLM calls
- Test FastAPI client
- Sample data fixtures

All tests use these fixtures to ensure:
1. Complete isolation from production data
2. Zero real OpenAI API calls (unless explicitly enabled)
3. Clean state between tests via transaction rollback
"""

import os
import uuid
from datetime import datetime
from typing import Generator, Any, Optional
from unittest.mock import MagicMock, AsyncMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

# Set test environment before importing app modules
os.environ["APP_ENV"] = "test"
# Use the existing database - tests use transaction rollback for isolation
# Don't override DATABASE_URL - let it use the existing one from .env

# Import after setting environment
from app.database import Base, get_db
from app.main import app
from app.models import (
    User, Task, TaskState, AttributeDefinition, AttributeAnswer, 
    EntityType, AttributeType, TaskDependency, TaskRelevantUser,
    TaskMergeProposal, MergeProposalStatus, TaskDependencyV2, DependencyStatus,
    TaskAlias, AlternativeDependencyProposal, AlternativeDepStatus,
    PendingDecision, PendingDecisionType, PromptTemplate
)
from app.config import settings


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """
    Create a test database engine.
    Uses the existing database with transaction rollback for isolation.
    All test data is rolled back after each test - NO DATA IS PERSISTED.
    """
    from app.config import settings
    
    # Use the same database as the app - tests are isolated via transaction rollback
    test_db_url = settings.database_url
    
    # Convert to psycopg format if needed
    if test_db_url.startswith("postgresql://"):
        test_db_url = test_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    engine = create_engine(
        test_db_url,
        pool_pre_ping=True,
        echo=False
    )
    
    yield engine
    
    # Don't drop tables - we're using transaction rollback for isolation


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """
    Provide a database session with transaction rollback.
    
    Each test gets a fresh session that is rolled back after the test,
    ensuring complete isolation between tests.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestSessionLocal()
    
    # Begin a nested transaction for savepoint
    nested = connection.begin_nested()
    
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_client(db_session) -> Generator[TestClient, None, None]:
    """
    Provide a FastAPI test client configured with the test database.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


# ============================================================================
# Fake OpenAI Client
# ============================================================================

class FakeOpenAIResponse:
    """Mock OpenAI API response object."""
    
    def __init__(
        self,
        text: str = '{"display_messages": ["Hello! How can I help you today?"], "updates": [], "control": {"conversation_done": false, "next_phase": null}}',
        response_id: str = None,
        tool_calls: list = None
    ):
        self.id = response_id or f"resp_{uuid.uuid4().hex[:16]}"
        self.output = [FakeOutputItem(text)]
        self.output_text = text
        if tool_calls:
            for tc in tool_calls:
                self.output.append(FakeToolCallItem(tc))


class FakeOutputItem:
    """Mock output item in OpenAI response."""
    
    def __init__(self, text: str):
        self.type = "message"
        self.content = [FakeContentItem(text)]


class FakeContentItem:
    """Mock content item."""
    
    def __init__(self, text: str):
        self.type = "output_text"
        self.text = text


class FakeToolCallItem:
    """Mock tool call item."""
    
    def __init__(self, tool_data: dict):
        self.type = "function_call"
        self.name = tool_data.get("name", "unknown_tool")
        self.arguments = tool_data.get("arguments", "{}")
        self.call_id = tool_data.get("call_id", f"call_{uuid.uuid4().hex[:8]}")


class FakeOpenAIClient:
    """
    Fake OpenAI client that returns deterministic responses.
    
    This replaces the real OpenAI client in tests to:
    1. Avoid API costs
    2. Provide deterministic behavior
    3. Allow testing without network access
    """
    
    def __init__(self):
        self.responses = MagicMock()
        self.responses.create = AsyncMock(side_effect=self._create_response)
        self._call_count = 0
        self._custom_responses = []
    
    async def _create_response(self, **kwargs) -> FakeOpenAIResponse:
        """Generate a fake response based on the input."""
        self._call_count += 1
        
        # If custom responses are queued, use them
        if self._custom_responses:
            return self._custom_responses.pop(0)
        
        # Generate contextual response based on input
        input_data = kwargs.get("input", [])
        mode = "general"
        
        # Detect mode from input
        for item in input_data if isinstance(input_data, list) else []:
            if isinstance(item, dict):
                content = item.get("content", "")
                if "morning brief" in content.lower() or "daily" in content.lower():
                    mode = "daily"
                elif "question" in content.lower():
                    mode = "questions"
        
        responses = {
            "daily": '{"display_messages": ["Good morning! Here is your daily brief.", "You have 3 tasks to review."], "updates": [], "control": {"conversation_done": false, "next_phase": "questions"}}',
            "questions": '{"display_messages": ["I understand. Let me help you with that."], "updates": [], "control": {"conversation_done": false, "next_phase": null}}',
            "general": '{"display_messages": ["Hello! How can I assist you today?"], "updates": [], "control": {"conversation_done": false, "next_phase": null}}'
        }
        
        return FakeOpenAIResponse(text=responses.get(mode, responses["general"]))
    
    def queue_response(self, response: FakeOpenAIResponse):
        """Queue a specific response for the next call."""
        self._custom_responses.append(response)
    
    def get_call_count(self) -> int:
        """Get the number of API calls made."""
        return self._call_count
    
    def reset(self):
        """Reset the mock state."""
        self._call_count = 0
        self._custom_responses.clear()


@pytest.fixture
def fake_openai_client():
    """Provide a fake OpenAI client for testing."""
    return FakeOpenAIClient()


@pytest.fixture(autouse=True)
def mock_openai(monkeypatch, fake_openai_client):
    """
    Automatically mock OpenAI client for all tests.
    
    This fixture is autouse=True, so it applies to every test automatically.
    Real OpenAI tests must be run separately with RUN_OPENAI_INTEGRATION_TESTS=1.
    """
    # Mock the client in robin_core
    monkeypatch.setattr("app.services.robin_core.client", fake_openai_client)
    
    # Also mock in other services that use OpenAI
    try:
        monkeypatch.setattr("app.services.robin_orchestrator.client", fake_openai_client)
    except AttributeError:
        pass
    
    try:
        monkeypatch.setattr("app.services.daily_sync_orchestrator.client", fake_openai_client)
    except AttributeError:
        pass
    
    return fake_openai_client


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_users(db_session) -> dict:
    """Create sample users for testing."""
    manager = User(
        id=uuid.uuid4(),
        name="Test Manager",
        email="manager@test.com",
        team="Engineering",
        timezone="UTC"
    )
    db_session.add(manager)
    db_session.flush()
    
    employee1 = User(
        id=uuid.uuid4(),
        name="Test Employee 1",
        email="employee1@test.com",
        team="Engineering",
        timezone="UTC",
        manager_id=manager.id
    )
    
    employee2 = User(
        id=uuid.uuid4(),
        name="Test Employee 2",
        email="employee2@test.com",
        team="Engineering",
        timezone="UTC",
        manager_id=manager.id
    )
    
    external_user = User(
        id=uuid.uuid4(),
        name="External User",
        email="external@test.com",
        team="Product",
        timezone="UTC"
    )
    
    db_session.add_all([employee1, employee2, external_user])
    db_session.commit()
    
    return {
        "manager": manager,
        "employee1": employee1,
        "employee2": employee2,
        "external": external_user
    }


@pytest.fixture
def sample_attributes(db_session) -> dict:
    """Get or create sample attribute definitions for testing."""
    # Try to get existing attributes first (they may exist in the DB)
    priority = db_session.query(AttributeDefinition).filter(
        AttributeDefinition.name == "priority",
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not priority:
        priority = AttributeDefinition(
            entity_type=EntityType.TASK,
            name="priority",
            label="Priority",
            type=AttributeType.ENUM,
            allowed_values=["Critical", "High", "Medium", "Low"],
            is_required=True
        )
        db_session.add(priority)
    
    status = db_session.query(AttributeDefinition).filter(
        AttributeDefinition.name == "status",
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not status:
        status = AttributeDefinition(
            entity_type=EntityType.TASK,
            name="status",
            label="Status",
            type=AttributeType.ENUM,
            allowed_values=["Not Started", "In Progress", "Blocked", "Done"],
            is_required=True
        )
        db_session.add(status)
    
    main_goal = db_session.query(AttributeDefinition).filter(
        AttributeDefinition.name == "main_goal",
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not main_goal:
        main_goal = AttributeDefinition(
            entity_type=EntityType.TASK,
            name="main_goal",
            label="Main Goal",
            type=AttributeType.STRING,
            is_required=False
        )
        db_session.add(main_goal)
    
    db_session.flush()  # Ensure IDs are assigned
    
    return {
        "priority": priority,
        "status": status,
        "main_goal": main_goal
    }


@pytest.fixture
def sample_tasks(db_session, sample_users) -> dict:
    """Create sample tasks for testing."""
    task1 = Task(
        id=uuid.uuid4(),
        title="Test Task 1",
        description="First test task",
        owner_user_id=sample_users["employee1"].id,
        created_by_user_id=sample_users["employee1"].id,
        state=TaskState.ACTIVE
    )
    
    task2 = Task(
        id=uuid.uuid4(),
        title="Test Task 2",
        description="Second test task",
        owner_user_id=sample_users["employee2"].id,
        created_by_user_id=sample_users["employee2"].id,
        state=TaskState.ACTIVE
    )
    
    # Task created for someone else (DRAFT state)
    task3 = Task(
        id=uuid.uuid4(),
        title="Suggested Task",
        description="Task suggested by manager",
        owner_user_id=sample_users["employee1"].id,
        created_by_user_id=sample_users["manager"].id,
        state=TaskState.DRAFT
    )
    
    db_session.add_all([task1, task2, task3])
    db_session.commit()
    
    return {
        "task1": task1,
        "task2": task2,
        "suggested_task": task3
    }


@pytest.fixture
def sample_task_with_answers(db_session, sample_users, sample_attributes, sample_tasks) -> dict:
    """Create a task with attribute answers for alignment testing."""
    task = sample_tasks["task1"]
    owner = sample_users["employee1"]
    manager = sample_users["manager"]
    priority_attr = sample_attributes["priority"]
    
    # Owner's answer
    owner_answer = AttributeAnswer(
        id=uuid.uuid4(),
        answered_by_user_id=owner.id,
        target_user_id=owner.id,
        task_id=task.id,
        attribute_id=priority_attr.id,
        value="High"
    )
    
    # Manager's answer (different - creates misalignment)
    manager_answer = AttributeAnswer(
        id=uuid.uuid4(),
        answered_by_user_id=manager.id,
        target_user_id=owner.id,
        task_id=task.id,
        attribute_id=priority_attr.id,
        value="Critical"
    )
    
    db_session.add_all([owner_answer, manager_answer])
    db_session.commit()
    
    return {
        "task": task,
        "owner_answer": owner_answer,
        "manager_answer": manager_answer
    }


# ============================================================================
# Sync Wrappers for Async Functions
# ============================================================================

def get_pending_questions_for_user(db_session: Session, user_id) -> list:
    """
    Synchronous wrapper to get pending questions for testing.
    In production, the async version is used. For tests, we query directly.
    """
    from app.models import (
        Task, AttributeDefinition, AttributeAnswer, 
        SimilarityScore, TaskRelevantUser, PendingDecision
    )
    from app.config import settings
    
    pending = []
    
    # Get user
    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    # Get tasks owned by user
    owned_tasks = db_session.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True,
        Task.state.in_([TaskState.ACTIVE, TaskState.DRAFT])
    ).all()
    
    # Get tasks user is relevant to
    relevant_entries = db_session.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user_id
    ).all()
    relevant_task_ids = [entry.task_id for entry in relevant_entries]
    
    relevant_tasks = db_session.query(Task).filter(
        Task.id.in_(relevant_task_ids),
        Task.is_active == True
    ).all() if relevant_task_ids else []
    
    # Combine unique tasks
    all_tasks = {t.id: t for t in (owned_tasks + relevant_tasks)}.values()
    
    # Get all attribute definitions
    attributes = db_session.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    for task in all_tasks:
        for attr in attributes:
            # Check if user has answered
            existing = db_session.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.answered_by_user_id == user_id
            ).first()
            
            if not existing:
                # Missing answer
                pending.append({
                    "id": f"{task.id}_{attr.name}_{user_id}",
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "attribute": attr.name,
                    "attribute_label": attr.label,
                    "type": "fill",
                    "reason": "missing",
                    "priority": 1 if attr.is_required else 2
                })
            else:
                # Check for misalignment
                other_answers = db_session.query(AttributeAnswer).filter(
                    AttributeAnswer.task_id == task.id,
                    AttributeAnswer.attribute_id == attr.id,
                    AttributeAnswer.answered_by_user_id != user_id
                ).all()
                
                for other in other_answers:
                    if other.value != existing.value:
                        pending.append({
                            "id": f"{task.id}_{attr.name}_{user_id}_align",
                            "task_id": str(task.id),
                            "task_title": task.title,
                            "attribute": attr.name,
                            "attribute_label": attr.label,
                            "type": "alignment",
                            "reason": "misaligned",
                            "priority": 3
                        })
                        break
    
    # Add pending decisions
    pending_decisions = db_session.query(PendingDecision).filter(
        PendingDecision.user_id == user_id,
        PendingDecision.resolved_at.is_(None)
    ).all()
    
    for decision in pending_decisions:
        pending.append({
            "id": str(decision.id),
            "decision_type": decision.decision_type.value if hasattr(decision.decision_type, 'value') else str(decision.decision_type),
            "entity_type": decision.entity_type,
            "entity_id": str(decision.entity_id),
            "description": decision.description,
            "type": "decision",
            "priority": 0
        })
    
    # Sort by priority
    pending.sort(key=lambda x: x.get("priority", 99))
    
    return pending


# ============================================================================
# Helper Functions
# ============================================================================

def create_user(db_session, name: str, email: str = None, team: str = "Engineering", manager=None) -> User:
    """Helper to create a user."""
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email or f"{name.lower().replace(' ', '_')}@test.com",
        team=team,
        timezone="UTC",
        manager_id=manager.id if manager else None
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_task(
    db_session, 
    title: str, 
    owner: User, 
    created_by: User = None,
    state: TaskState = None,
    parent: Task = None
) -> Task:
    """Helper to create a task."""
    created_by = created_by or owner
    if state is None:
        state = TaskState.ACTIVE if created_by.id == owner.id else TaskState.DRAFT
    
    task = Task(
        id=uuid.uuid4(),
        title=title,
        description=f"Test task: {title}",
        owner_user_id=owner.id,
        created_by_user_id=created_by.id,
        state=state,
        parent_id=parent.id if parent else None
    )
    db_session.add(task)
    db_session.flush()
    return task


def create_attribute_answer(
    db_session,
    task: Task,
    attribute: AttributeDefinition,
    value: str,
    answered_by: User,
    target_user: User = None
) -> AttributeAnswer:
    """Helper to create an attribute answer."""
    answer = AttributeAnswer(
        id=uuid.uuid4(),
        answered_by_user_id=answered_by.id,
        target_user_id=(target_user or answered_by).id,
        task_id=task.id,
        attribute_id=attribute.id,
        value=value
    )
    db_session.add(answer)
    db_session.flush()
    return answer

