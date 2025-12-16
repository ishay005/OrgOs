import uuid
from datetime import datetime, time
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, Time, 
    ForeignKey, Enum as SQLEnum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class EntityType(str, enum.Enum):
    TASK = "task"
    USER = "user"


class AttributeType(str, enum.Enum):
    STRING = "string"
    ENUM = "enum"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATE = "date"


class MessageSender(str, enum.Enum):
    USER = "user"
    ROBIN = "robin"
    SYSTEM = "system"


# =============================================================================
# Task State Machine Enums
# =============================================================================

class TaskState(str, enum.Enum):
    """
    Task lifecycle states.
    
    DRAFT: Task exists but owner has not acknowledged yet (created by someone else).
    ACTIVE: Owner has acknowledged/accepted the task. It's in the live OrgMap.
    REJECTED: Owner rejected the suggested task; sent back to creator for action.
    ARCHIVED: Old/irrelevant; kept only for history or after merge.
    """
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class DependencyStatus(str, enum.Enum):
    """
    Dependency edge states.
    
    PROPOSED: Downstream requested dependency; upstream has not accepted.
    CONFIRMED: Upstream accepted; this is an active dependency in OrgMap.
    REJECTED: Upstream explicitly rejected, with reason.
    REMOVED: Previously existing dependency was removed (for history).
    """
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    REMOVED = "REMOVED"


class MergeProposalStatus(str, enum.Enum):
    """Status of a task merge proposal."""
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AlternativeDepStatus(str, enum.Enum):
    """Status of an alternative dependency proposal."""
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AttributeConsensusState(str, enum.Enum):
    """
    Consensus states for attribute values.
    
    NO_DATA: No answers exist for this attribute.
    SINGLE_SOURCE: Only one user has provided an answer.
    ALIGNED: Multiple answers exist and they are consistent.
    MISALIGNED: Multiple answers exist but they conflict.
    """
    NO_DATA = "NO_DATA"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    ALIGNED = "ALIGNED"
    MISALIGNED = "MISALIGNED"


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    team = Column(String, nullable=True)  # Team name for grouping
    role = Column(String, nullable=True)  # User's role/title (e.g., "Developer", "Team Lead", "VP")
    timezone = Column(String, default="UTC")
    notification_time = Column(Time, default=time(10, 0))
    manager_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Team hierarchy
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    manager = relationship("User", remote_side=[id], foreign_keys=[manager_id], backref="employees")
    tasks_owned = relationship("Task", back_populates="owner", foreign_keys="Task.owner_user_id")
    answers_given = relationship("AttributeAnswer", foreign_keys="AttributeAnswer.answered_by_user_id", back_populates="answered_by_user")
    answers_about = relationship("AttributeAnswer", foreign_keys="AttributeAnswer.target_user_id", back_populates="target_user")
    questions_answered = relationship("QuestionLog", foreign_keys="QuestionLog.answered_by_user_id", back_populates="answered_by_user")
    questions_about = relationship("QuestionLog", foreign_keys="QuestionLog.target_user_id", back_populates="target_user")
    daily_sync_sessions = relationship("DailySyncSession", back_populates="user")


class TaskDependency(Base):
    """Junction table for task dependencies (many-to-many)"""
    __tablename__ = "task_dependencies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskRelevantUser(Base):
    """Junction table for users who need to be aligned on a task"""
    __tablename__ = "task_relevant_users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    added_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="relevant_user_associations")
    user = relationship("User", foreign_keys=[user_id])
    added_by = relationship("User", foreign_keys=[added_by_user_id])


class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Who created this task in the system
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    
    # Task state machine
    state = Column(
        SQLEnum(TaskState, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskState.ACTIVE
    )
    state_changed_at = Column(DateTime, nullable=True)
    state_reason = Column(Text, nullable=True)  # Reason for state change (e.g., rejection reason)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    owner = relationship("User", back_populates="tasks_owned", foreign_keys=[owner_user_id])
    creator = relationship("User", foreign_keys=[created_by_user_id])
    answers = relationship("AttributeAnswer", back_populates="task")
    questions = relationship("QuestionLog", back_populates="task")
    
    # Parent-child relationships
    parent = relationship("Task", remote_side=[id], foreign_keys=[parent_id], backref="children")
    
    # Dependencies (many-to-many) - legacy relationship, use TaskDependencyV2 for state machine
    dependencies = relationship(
        "Task",
        secondary="task_dependencies",
        primaryjoin="Task.id==TaskDependency.task_id",
        secondaryjoin="Task.id==TaskDependency.depends_on_task_id",
        backref="dependent_tasks"
    )
    
    # Relevant users (who need to be aligned on this task)
    relevant_user_associations = relationship("TaskRelevantUser", back_populates="task", cascade="all, delete-orphan")
    
    # Aliases (for merged tasks)
    aliases = relationship("TaskAlias", back_populates="canonical_task", foreign_keys="TaskAlias.canonical_task_id")
    
    @property
    def relevant_users(self):
        """Get list of users who need to be aligned on this task"""
        return [assoc.user for assoc in self.relevant_user_associations]
    
    @property
    def is_draft(self):
        return self.state == TaskState.DRAFT
    
    @property
    def is_canonical(self):
        """True if this task is not merged into another (i.e., it's a first-class node)"""
        return self.state != TaskState.ARCHIVED or not hasattr(self, '_merged_into')


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(SQLEnum(EntityType), nullable=False)
    name = Column(String, nullable=False)
    label = Column(String, nullable=False)
    type = Column(SQLEnum(AttributeType), nullable=False)
    description = Column(Text, nullable=True)
    allowed_values = Column(JSON, nullable=True)
    is_required = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    answers = relationship("AttributeAnswer", back_populates="attribute")
    questions = relationship("QuestionLog", back_populates="attribute")


class AttributeAnswer(Base):
    __tablename__ = "attribute_answers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answered_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    attribute_id = Column(UUID(as_uuid=True), ForeignKey("attribute_definitions.id"), nullable=False)
    value = Column(String, nullable=True)
    refused = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    answered_by_user = relationship("User", foreign_keys=[answered_by_user_id], back_populates="answers_given")
    target_user = relationship("User", foreign_keys=[target_user_id], back_populates="answers_about")
    task = relationship("Task", back_populates="answers")
    attribute = relationship("AttributeDefinition", back_populates="answers")


class QuestionLog(Base):
    __tablename__ = "question_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answered_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    attribute_id = Column(UUID(as_uuid=True), ForeignKey("attribute_definitions.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    answered_by_user = relationship("User", foreign_keys=[answered_by_user_id], back_populates="questions_answered")
    target_user = relationship("User", foreign_keys=[target_user_id], back_populates="questions_about")
    task = relationship("Task", back_populates="questions")
    attribute = relationship("AttributeDefinition", back_populates="questions")


class SimilarityScore(Base):
    """
    Pre-calculated similarity scores between attribute answer pairs.
    Updated whenever answers change to avoid recalculating on every request.
    """
    __tablename__ = "similarity_scores"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # The two answers being compared
    answer_a_id = Column(UUID(as_uuid=True), ForeignKey("attribute_answers.id"), nullable=False)
    answer_b_id = Column(UUID(as_uuid=True), ForeignKey("attribute_answers.id"), nullable=False)
    
    # Pre-calculated similarity score (0.0 to 1.0)
    similarity_score = Column(Float, nullable=False)
    
    # Metadata
    calculated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    answer_a = relationship("AttributeAnswer", foreign_keys=[answer_a_id])
    answer_b = relationship("AttributeAnswer", foreign_keys=[answer_b_id])


class ChatThread(Base):
    """
    Chat conversation thread between a user and Robin assistant.
    Each user has exactly one thread for their ongoing conversation with Robin.
    """
    __tablename__ = "chat_threads"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="chat_thread")
    messages = relationship("ChatMessage", back_populates="thread", cascade="all, delete-orphan")


class ChatMessage(Base):
    """
    Individual message in a chat thread.
    Can be from user, Robin assistant, or system.
    """
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("chat_threads.id"), nullable=False)
    sender = Column(String, nullable=False)  # Changed from SQLEnum to String
    text = Column(Text, nullable=False)
    msg_metadata = Column("metadata", JSON, nullable=True)  # For structured info like questions, updates
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    thread = relationship("ChatThread", back_populates="messages")


class PromptTemplate(Base):
    """
    Dynamic prompt templates for Robin.
    Allows editing prompts and context configuration through the UI.
    """
    __tablename__ = "prompt_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mode = Column(String, nullable=False)  # morning_brief, user_question, collect_data
    has_pending = Column(Boolean, nullable=False)  # Whether there are pending questions
    
    # The actual prompt text
    prompt_text = Column(Text, nullable=False)
    
    # Context configuration (JSON)
    # {
    #   "history_size": 3,
    #   "include_tasks": true,
    #   "include_pending": true,
    #   "include_user_info": true,
    #   "include_manager": true,
    #   "include_employees": true
    # }
    context_config = Column(JSON, nullable=False, default={})
    
    # Versioning
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String, nullable=True)  # User who created this version
    notes = Column(Text, nullable=True)  # Optional notes about this version
    
    def __repr__(self):
        return f"<PromptTemplate mode={self.mode} has_pending={self.has_pending} v{self.version} active={self.is_active}>"


class DailySyncPhase(str, enum.Enum):
    """Phases of the Daily Sync conversation flow"""
    OPENING_BRIEF = "opening_brief"  # Initial brief when starting Daily Sync
    QUESTIONS = "questions"  # User questions + Robin questions combined
    SUMMARY = "summary"
    DONE = "done"


class DailySyncSession(Base):
    """Tracks an active Daily Sync session for a user"""
    __tablename__ = "daily_sync_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('chat_threads.id'), nullable=False)
    phase = Column(SQLEnum(DailySyncPhase, values_callable=lambda x: [e.value for e in x]), nullable=False, default=DailySyncPhase.OPENING_BRIEF)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # OpenAI Responses API: last response ID for conversation threading
    # When continuing a conversation, pass this as previous_response_id
    last_response_id = Column(String, nullable=True)
    
    # Store snapshot of insight questions for this session (as JSON)
    # Format: [{"id": "uuid", "text": "...", "value": 10, "reason": "..."}, ...]
    insight_questions = Column(JSON, nullable=False, default=[])
    
    # Track which questions have been asked and answered (list of IDs)
    asked_question_ids = Column(JSON, nullable=False, default=[])
    answered_question_ids = Column(JSON, nullable=False, default=[])
    
    # Relationships
    user = relationship("User", back_populates="daily_sync_sessions")
    thread = relationship("ChatThread")
    
    __table_args__ = (
        Index('idx_daily_sync_active', 'user_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<DailySyncSession user={self.user_id} phase={self.phase} active={self.is_active}>"


class QuestionsSession(Base):
    """
    Tracks an active Questions mode session for a user.
    Questions mode is free-form conversation with model-driven termination.
    """
    __tablename__ = "questions_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('chat_threads.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # OpenAI Responses API: last response ID for conversation threading
    last_response_id = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", backref="questions_sessions")
    thread = relationship("ChatThread")
    
    __table_args__ = (
        Index('idx_questions_session_active', 'user_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<QuestionsSession user={self.user_id} active={self.is_active}>"


class MessageDebugData(Base):
    """Stores debug information (prompt + response) for Robin messages"""
    __tablename__ = "message_debug_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey('chat_messages.id'), nullable=False, unique=True)
    
    # Full prompt sent to LLM (includes system prompt, context, user message)
    full_prompt = Column(JSON, nullable=False)
    
    # Full response from LLM (parsed JSON with display_messages and updates)
    full_response = Column(JSON, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    message = relationship("ChatMessage", backref="debug_data")
    
    __table_args__ = (
        Index('idx_message_debug_message_id', 'message_id'),
    )
    
    def __repr__(self):
        return f"<MessageDebugData message_id={self.message_id}>"


# =============================================================================
# Task Merge & Alias Models
# =============================================================================

class TaskAlias(Base):
    """
    Tracks aliases for merged tasks.
    When task X is merged into task Y, we create a TaskAlias record.
    The canonical task (Y) shows its aliases in OrgMap views.
    """
    __tablename__ = "task_aliases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    alias_title = Column(String, nullable=False)
    alias_created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    merged_from_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)  # Original task before merge
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    canonical_task = relationship("Task", foreign_keys=[canonical_task_id], back_populates="aliases")
    alias_creator = relationship("User", foreign_keys=[alias_created_by_user_id])
    merged_from_task = relationship("Task", foreign_keys=[merged_from_task_id])
    
    __table_args__ = (
        Index('idx_task_alias_canonical', 'canonical_task_id'),
    )
    
    def __repr__(self):
        return f"<TaskAlias '{self.alias_title}' -> Task {self.canonical_task_id}>"


class TaskMergeProposal(Base):
    """
    Proposal to merge one task into another.
    Requires double-consent: owner proposes, creator of source task must accept.
    """
    __tablename__ = "task_merge_proposals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # The task that would be merged/aliased (source)
    from_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    # The canonical target (destination)
    to_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    
    # Who proposed the merge (usually owner of from_task or to_task)
    proposed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    proposal_reason = Column(Text, nullable=False)  # REQUIRED: why they think they are the same
    
    # Status
    status = Column(
        SQLEnum(MergeProposalStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MergeProposalStatus.PROPOSED
    )
    
    # Rejection info
    rejected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejected_reason = Column(Text, nullable=True)  # REQUIRED when status = REJECTED
    
    # Acceptance info
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    from_task = relationship("Task", foreign_keys=[from_task_id])
    to_task = relationship("Task", foreign_keys=[to_task_id])
    proposed_by = relationship("User", foreign_keys=[proposed_by_user_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_user_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])
    
    __table_args__ = (
        Index('idx_merge_proposal_from_task', 'from_task_id'),
        Index('idx_merge_proposal_status', 'status'),
    )
    
    def __repr__(self):
        return f"<TaskMergeProposal {self.from_task_id} -> {self.to_task_id} ({self.status})>"


# =============================================================================
# Dependency State Machine Models
# =============================================================================

class TaskDependencyV2(Base):
    """
    Enhanced task dependency with state machine.
    downstream_task depends on upstream_task.
    """
    __tablename__ = "task_dependencies_v2"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # The task that has the dependency (depends on upstream)
    downstream_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    # The task being depended on
    upstream_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    
    # State machine
    status = Column(
        SQLEnum(DependencyStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DependencyStatus.PROPOSED
    )
    
    # Who proposed this dependency
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Acceptance info
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    
    # Rejection info
    rejected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_reason = Column(Text, nullable=True)  # REQUIRED when status = REJECTED
    
    # Removal info
    removed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    removed_at = Column(DateTime, nullable=True)
    removed_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    downstream_task = relationship("Task", foreign_keys=[downstream_task_id])
    upstream_task = relationship("Task", foreign_keys=[upstream_task_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_user_id])
    removed_by = relationship("User", foreign_keys=[removed_by_user_id])
    
    __table_args__ = (
        Index('idx_dep_v2_downstream', 'downstream_task_id'),
        Index('idx_dep_v2_upstream', 'upstream_task_id'),
        Index('idx_dep_v2_status', 'status'),
    )
    
    def __repr__(self):
        return f"<TaskDependencyV2 {self.downstream_task_id} -> {self.upstream_task_id} ({self.status})>"


class AlternativeDependencyProposal(Base):
    """
    Proposal to replace one dependency with another.
    When upstream owner rejects A->B, they can suggest A->C instead.
    Requires downstream owner to accept.
    """
    __tablename__ = "alternative_dependency_proposals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # The original dependency being replaced
    original_dependency_id = Column(UUID(as_uuid=True), ForeignKey("task_dependencies_v2.id"), nullable=False)
    
    # Task relationships
    downstream_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)  # A
    original_upstream_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)  # B
    suggested_upstream_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)  # C
    
    # Who proposed the alternative
    proposed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    proposal_reason = Column(Text, nullable=False)  # REQUIRED
    
    # Status
    status = Column(
        SQLEnum(AlternativeDepStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AlternativeDepStatus.PROPOSED
    )
    
    # Rejection info
    rejected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejected_reason = Column(Text, nullable=True)  # REQUIRED when REJECTED
    
    # Acceptance info
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    original_dependency = relationship("TaskDependencyV2", foreign_keys=[original_dependency_id])
    downstream_task = relationship("Task", foreign_keys=[downstream_task_id])
    original_upstream_task = relationship("Task", foreign_keys=[original_upstream_task_id])
    suggested_upstream_task = relationship("Task", foreign_keys=[suggested_upstream_task_id])
    proposed_by = relationship("User", foreign_keys=[proposed_by_user_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_user_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])
    
    __table_args__ = (
        Index('idx_alt_dep_status', 'status'),
        Index('idx_alt_dep_downstream', 'downstream_task_id'),
    )
    
    def __repr__(self):
        return f"<AlternativeDependencyProposal {self.downstream_task_id}: {self.original_upstream_task_id} -> {self.suggested_upstream_task_id} ({self.status})>"


# =============================================================================
# Pending Decision Model (for task decisions, merge consent, dependency consent)
# =============================================================================

class PendingDecisionType(str, enum.Enum):
    """Types of decisions awaiting user action."""
    TASK_ACCEPTANCE = "TASK_ACCEPTANCE"  # Owner needs to accept/reject a suggested task
    MERGE_CONSENT = "MERGE_CONSENT"  # Creator needs to accept/reject a merge proposal
    DEPENDENCY_ACCEPTANCE = "DEPENDENCY_ACCEPTANCE"  # Upstream owner needs to accept/reject dependency
    ALTERNATIVE_DEP_ACCEPTANCE = "ALTERNATIVE_DEP_ACCEPTANCE"  # Downstream owner needs to accept/reject alternative


class PendingDecision(Base):
    """
    Tracks decisions that require user action.
    This drives the question system for double-consent flows.
    """
    __tablename__ = "pending_decisions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who needs to make the decision
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # What type of decision
    decision_type = Column(
        SQLEnum(PendingDecisionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    
    # Reference to the entity requiring decision (polymorphic reference)
    entity_type = Column(String, nullable=False)  # "task", "merge_proposal", "dependency", "alt_dependency"
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Human-readable description
    description = Column(Text, nullable=False)
    
    # Is this decision still pending?
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolution = Column(String, nullable=True)  # "accepted", "rejected", "merged"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    
    __table_args__ = (
        Index('idx_pending_decision_user', 'user_id', 'is_resolved'),
        Index('idx_pending_decision_entity', 'entity_type', 'entity_id'),
    )
    
    def __repr__(self):
        return f"<PendingDecision {self.decision_type} for user {self.user_id} resolved={self.is_resolved}>"

