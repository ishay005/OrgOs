"""
Database seeding for initial ontology (AttributeDefinitions)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.models import AttributeDefinition, EntityType, AttributeType


def seed_task_attributes(db: Session):
    """Seed initial task attributes"""
    task_attributes = [
        {
            "entity_type": EntityType.TASK,
            "name": "priority",
            "label": "Priority",
            "type": AttributeType.ENUM,
            "allowed_values": ["Critical", "High", "Medium", "Low"],
            "description": "How important this task is right now.",
            "is_required": False,
        },
        {
            "entity_type": EntityType.TASK,
            "name": "status",
            "label": "Status",
            "type": AttributeType.ENUM,
            "allowed_values": ["Not started", "In progress", "Blocked", "Done"],
            "description": "Current state of the task.",
            "is_required": False,
        },
        {
            "entity_type": EntityType.TASK,
            "name": "perceived_owner",
            "label": "Perceived owner",
            "type": AttributeType.STRING,
            "description": "Who you believe is ultimately responsible for this task.",
            "is_required": False,
        },
        {
            "entity_type": EntityType.TASK,
            "name": "impact_size",
            "label": "Expected impact size",
            "type": AttributeType.INT,
            "description": "Perceived impact if this succeeds (1–5).",
            "is_required": False,
        },
        {
            "entity_type": EntityType.TASK,
            "name": "main_goal",
            "label": "Main goal",
            "type": AttributeType.STRING,
            "description": "In your own words, what is the main goal of this task? (free-text field; when comparing answers, use semantic similarity)",
            "is_required": False,
        },
        {
            "entity_type": EntityType.TASK,
            "name": "resources",
            "label": "Resources",
            "type": AttributeType.STRING,
            "description": "Links, documents, or resources related to this task",
            "is_required": False,
        },
    ]
    
    for attr_data in task_attributes:
        # Check if already exists
        existing = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == attr_data["entity_type"],
            AttributeDefinition.name == attr_data["name"]
        ).first()
        
        if not existing:
            attr = AttributeDefinition(**attr_data)
            db.add(attr)
    
    db.commit()


def seed_user_attributes(db: Session):
    """Seed initial user attributes (optional)"""
    user_attributes = [
        {
            "entity_type": EntityType.USER,
            "name": "role_title",
            "label": "Role Title",
            "type": AttributeType.STRING,
            "description": "User's role or job title",
            "is_required": False,
        },
        {
            "entity_type": EntityType.USER,
            "name": "primary_team",
            "label": "Primary Team",
            "type": AttributeType.STRING,
            "description": "User's primary team",
            "is_required": False,
        },
        {
            "entity_type": EntityType.USER,
            "name": "main_domain",
            "label": "Main Domain",
            "type": AttributeType.STRING,
            "description": "User's main domain or area of expertise",
            "is_required": False,
        },
        {
            "entity_type": EntityType.USER,
            "name": "decision_scope",
            "label": "Decision Scope",
            "type": AttributeType.ENUM,
            "allowed_values": ["Individual", "Team", "Cross-team", "Org-wide"],
            "description": "Scope of decision-making authority",
            "is_required": False,
        },
        {
            "entity_type": EntityType.USER,
            "name": "perceived_load",
            "label": "Perceived Load",
            "type": AttributeType.ENUM,
            "allowed_values": ["Underloaded", "Balanced", "Overloaded"],
            "description": "Perceived workload",
            "is_required": False,
        },
    ]
    
    for attr_data in user_attributes:
        # Check if already exists
        existing = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == attr_data["entity_type"],
            AttributeDefinition.name == attr_data["name"]
        ).first()
        
        if not existing:
            attr = AttributeDefinition(**attr_data)
            db.add(attr)
    
    db.commit()


def seed_database(db: Session):
    """Seed all initial data"""
    seed_task_attributes(db)
    seed_user_attributes(db)

