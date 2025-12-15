"""
Pydantic schemas for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime, time


# User schemas
class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    timezone: Optional[str] = "UTC"
    notification_time: Optional[str] = "10:00"
    manager_id: Optional[UUID] = None


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: Optional[str] = None
    timezone: str
    notification_time: time
    manager_id: Optional[UUID] = None
    manager_name: Optional[str] = None
    employee_count: int = 0
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True


# Alignment schemas
class AlignmentCreate(BaseModel):
    target_user_id: UUID
    align: bool


class AlignmentResponse(BaseModel):
    target_user_id: UUID
    target_user_name: str


# Task schemas
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    children: Optional[List[str]] = None  # List of task titles (create if don't exist)
    dependencies: Optional[List[UUID]] = None  # List of task IDs


class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    owner_user_id: UUID
    owner_name: str
    parent_id: Optional[UUID]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TaskGraphNode(BaseModel):
    """Task node for graph visualization"""
    id: UUID
    title: str
    description: Optional[str]
    owner_name: str
    parent_id: Optional[UUID]
    children_ids: List[UUID]
    dependency_ids: List[UUID]


# Attribute schemas
class AttributeDefinitionResponse(BaseModel):
    id: UUID
    entity_type: str
    name: str
    label: str
    type: str
    description: Optional[str]
    allowed_values: Optional[List[str]]
    is_required: bool
    
    class Config:
        from_attributes = True


# Misalignment schemas
class MisalignmentResponse(BaseModel):
    other_user_id: UUID
    other_user_name: str
    task_id: UUID
    task_title: str
    attribute_id: UUID
    attribute_name: str
    attribute_label: str
    your_value: str
    their_value: str
    similarity_score: float


# Org Chart schemas
class OrgChartNode(BaseModel):
    id: UUID
    name: str
    email: Optional[str] = None
    team: Optional[str] = None
    role: Optional[str] = None
    manager_id: Optional[UUID] = None
    employee_count: int
    task_count: int
    
    class Config:
        from_attributes = True


class OrgChartResponse(BaseModel):
    users: List[OrgChartNode]

