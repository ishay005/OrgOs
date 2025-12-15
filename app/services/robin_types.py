"""
Robin Types - Pydantic models for the new Robin architecture.
Used across call_robin(), MCP tools, and endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime


# =============================================================================
# Control Signals - Model-driven mode transitions
# =============================================================================

class ControlSignals(BaseModel):
    """
    Signals from Robin about session/conversation state.
    
    - conversation_done: True when Questions mode or Daily.summary should end
    - next_phase: For Daily mode, signals transition (e.g., "summary")
    """
    conversation_done: bool = False
    next_phase: Optional[Literal["summary"]] = None


# =============================================================================
# Structured Updates - Changes Robin wants to apply to OrgOs data
# =============================================================================

class StructuredUpdate(BaseModel):
    """
    A structured update Robin wants to apply to the OrgOs database.
    Maps to attribute_answers table.
    """
    task_id: Optional[str] = None  # Task UUID or null for user-level attributes
    target_user_id: str  # User name or ID - will be resolved by backend
    attribute_name: str  # Attribute name (e.g., "status", "priority")
    value: str  # The new value


# =============================================================================
# Robin Reply - Complete response from call_robin()
# =============================================================================

class RobinReply(BaseModel):
    """
    Complete response from Robin after processing a request.
    Returned by call_robin() to the endpoint handlers.
    """
    display_messages: list[str] = Field(default_factory=list)
    updates: list[StructuredUpdate] = Field(default_factory=list)
    control: ControlSignals = Field(default_factory=ControlSignals)
    
    # Metadata for debugging/logging
    mode: str
    submode: Optional[str] = None
    response_id: Optional[str] = None  # OpenAI response ID for conversation threading
    tool_calls_made: list[dict] = Field(default_factory=list)  # [{name, args, result}]
    raw_response: Optional[dict] = None


# =============================================================================
# LLM Response Schema - What we expect from the model
# =============================================================================

class LLMResponseSchema(BaseModel):
    """
    The JSON schema we enforce on the LLM response.
    This is sent as response_format to OpenAI.
    """
    display_messages: list[str] = Field(
        description="Natural language messages to show to the user, in order"
    )
    updates: list[StructuredUpdate] = Field(
        default_factory=list,
        description="Structured updates to apply to OrgOs data"
    )
    control: ControlSignals = Field(
        default_factory=ControlSignals,
        description="Control signals for session/mode transitions"
    )


# =============================================================================
# MCP Tool Schemas - Input/output for Cortex tools
# =============================================================================

class UserContext(BaseModel):
    """Context about the current user"""
    user_id: str
    name: str
    email: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    manager_name: Optional[str] = None
    manager_id: Optional[str] = None
    timezone: str = "UTC"
    employee_count: int = 0
    employee_names: list[str] = Field(default_factory=list)


class TaskContext(BaseModel):
    """Context about a task"""
    task_id: str
    title: str
    description: Optional[str] = None
    owner_name: str
    owner_id: str
    status: Optional[str] = None
    priority: Optional[str] = None
    main_goal: Optional[str] = None
    is_blocked: bool = False
    parent_title: Optional[str] = None
    children_titles: list[str] = Field(default_factory=list)
    dependency_titles: list[str] = Field(default_factory=list)


class DailyTaskContext(BaseModel):
    """Full task context for Daily/Morning Brief modes"""
    tasks_in_progress: list[TaskContext] = Field(default_factory=list)
    tasks_blocked: list[TaskContext] = Field(default_factory=list)
    tasks_high_priority: list[TaskContext] = Field(default_factory=list)
    tasks_owned: list[TaskContext] = Field(default_factory=list)
    tasks_relevant: list[TaskContext] = Field(default_factory=list)
    misalignment_count: int = 0
    top_misalignments: list[dict] = Field(default_factory=list)


class PendingQuestion(BaseModel):
    """A question that needs to be answered for perception mapping"""
    id: str
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    task_owner: Optional[str] = None
    attribute_name: str
    attribute_label: str
    question: str
    reason: str  # Why this question is valuable
    value: int = 0  # Priority/value score


class InsightQuestion(BaseModel):
    """An insight question for Daily Sync"""
    id: str
    text: str
    value: int
    reason: str
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    attribute_name: Optional[str] = None


class ObservationPayload(BaseModel):
    """Payload for recording an observation/update"""
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    target_user_id: Optional[str] = None
    target_user_name: Optional[str] = None
    attribute_name: str
    value: str
    source: str = "robin_conversation"
    notes: Optional[str] = None

