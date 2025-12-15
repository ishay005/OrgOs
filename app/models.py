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
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    owner = relationship("User", back_populates="tasks_owned", foreign_keys=[owner_user_id])
    answers = relationship("AttributeAnswer", back_populates="task")
    questions = relationship("QuestionLog", back_populates="task")
    
    # Parent-child relationships
    parent = relationship("Task", remote_side=[id], foreign_keys=[parent_id], backref="children")
    
    # Dependencies (many-to-many)
    dependencies = relationship(
        "Task",
        secondary="task_dependencies",
        primaryjoin="Task.id==TaskDependency.task_id",
        secondaryjoin="Task.id==TaskDependency.depends_on_task_id",
        backref="dependent_tasks"
    )
    
    # Relevant users (who need to be aligned on this task)
    relevant_user_associations = relationship("TaskRelevantUser", back_populates="task", cascade="all, delete-orphan")
    
    @property
    def relevant_users(self):
        """Get list of users who need to be aligned on this task"""
        return [assoc.user for assoc in self.relevant_user_associations]


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
    
    # OpenAI conversation ID for multi-turn context (for future Assistants API)
    conversation_id = Column(String, nullable=True)
    
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
    
    # OpenAI conversation ID for multi-turn context
    conversation_id = Column(String, nullable=True)
    
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

