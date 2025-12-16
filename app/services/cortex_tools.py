"""
Cortex Tools - MCP tools for Robin to fetch context and record updates.

These tools wrap OrgOs backend intelligence and expose it to the LLM
via function calling, replacing manual context string building.
"""
import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, 
    TaskRelevantUser, EntityType, DailySyncSession, SimilarityScore,
    TaskState, TaskAlias, TaskMergeProposal, MergeProposalStatus,
    TaskDependencyV2, DependencyStatus, AlternativeDependencyProposal, AlternativeDepStatus,
    PendingDecision, PendingDecisionType
)
from app.services.robin_types import (
    UserContext, TaskContext, DailyTaskContext, 
    PendingQuestion, InsightQuestion, ObservationPayload
)
from app.services import state_machines

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions for OpenAI Function Calling
# =============================================================================

CORTEX_TOOLS = [
    # -------------------------------------------------------------------------
    # Existing Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_user_context",
            "description": "Get context about the current user including role, team, manager, and preferences.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_task_context",
            "description": "Get tasks relevant for Daily mode or Morning Brief - includes in-progress tasks, blocked items, priorities, and misalignments.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_questions_mode_context",
            "description": "Get context relevant for answering user questions - tasks and topics the user typically cares about.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_insight_questions_for_daily",
            "description": "Get the list of insight questions to ask during Daily Sync, ordered by value/priority.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_questions",
            "description": "Get questions that need answers for perception mapping and alignment tracking.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_observation",
            "description": "Record an observation or update from the conversation (task status, priority, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Name of the task being updated (optional for user-level attributes)"
                    },
                    "target_user_name": {
                        "type": "string",
                        "description": "Name of the user this observation is about"
                    },
                    "attribute_name": {
                        "type": "string",
                        "description": "Name of the attribute being set (e.g., 'status', 'priority')"
                    },
                    "value": {
                        "type": "string",
                        "description": "The new value for the attribute"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about why this was recorded"
                    }
                },
                "required": ["attribute_name", "value"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Org Structure / People Context Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_org_structure",
            "description": "Get the organizational structure - list of users with manager relationships. Optionally limit to a subtree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_user_id": {
                        "type": "string",
                        "description": "Optional: If provided, limit to this user and their reports (subtree)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Get detailed profile for a specific user including role, team, manager, timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to get profile for"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_neighbors",
            "description": "Get people around a user - manager, direct reports, peers, and collaborators.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to get neighbors for"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Task & Alignment Context Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_tasks_for_user",
            "description": "Get tasks the user owns or is relevant to. Useful for briefs and overviews.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user"
                    },
                    "role": {
                        "type": "string",
                        "enum": ["owner", "relevant", "all"],
                        "description": "Filter by relationship: 'owner' (only owned), 'relevant' (only where relevant), 'all' (both)"
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "If true, only return active tasks (default: true)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of tasks to return (default: 50)"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_detail",
            "description": "Get detailed info for a single task including hierarchy, dependencies, and key attributes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_alignment_summary",
            "description": "Get tasks/attributes where this user is most misaligned with others.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of misalignments to return (default: 10)"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_alignment_hotspots",
            "description": "For a task, see where the team is split - attributes with high disagreement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Data-Collection Utility Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_attribute_fill_status",
            "description": "Get missing or stale attributes for tasks relevant to this user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user"
                    },
                    "staleness_days": {
                        "type": "integer",
                        "description": "Days after which an answer is considered stale (default: 7)"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_attribute_answer",
            "description": "Insert or update an attribute answer for a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task"
                    },
                    "target_user_id": {
                        "type": "string",
                        "description": "The ID of the user this answer is about (usually task owner)"
                    },
                    "attribute_name": {
                        "type": "string",
                        "description": "Name of the attribute (e.g., 'status', 'priority')"
                    },
                    "value": {
                        "type": "string",
                        "description": "The value for the attribute"
                    },
                    "refused": {
                        "type": "boolean",
                        "description": "If true, marks the user as refusing to answer (default: false)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about this answer"
                    }
                },
                "required": ["task_id", "target_user_id", "attribute_name", "value"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Task State Machine Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_pending_decisions",
            "description": "Get pending decisions for the current user (task acceptance, merge consent, dependency acceptance, etc.)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "accept_task",
            "description": "Accept a DRAFT task that was suggested to the user. Transitions task to ACTIVE state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task to accept"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_task",
            "description": "Reject a DRAFT task that was suggested to the user. Requires a reason.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task to reject"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for rejection (required)"
                    }
                },
                "required": ["task_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_task_merge",
            "description": "Propose merging a DRAFT task into an existing task. Creates a merge proposal requiring second consent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_task_id": {
                        "type": "string",
                        "description": "The ID of the task to merge (source)"
                    },
                    "to_task_id": {
                        "type": "string",
                        "description": "The ID of the target task (destination)"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason why these tasks should be merged (required)"
                    }
                },
                "required": ["from_task_id", "to_task_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "accept_merge_proposal",
            "description": "Accept a merge proposal (second consent from original task creator).",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the merge proposal to accept"
                    }
                },
                "required": ["proposal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_merge_proposal",
            "description": "Reject a merge proposal. Requires a reason.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the merge proposal to reject"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for rejection (required)"
                    }
                },
                "required": ["proposal_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task_for_user",
            "description": "Create a new task for a user. If creator != owner, task starts as DRAFT.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the task"
                    },
                    "owner_user_id": {
                        "type": "string",
                        "description": "ID of the user who will own the task"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description"
                    },
                    "parent_task_id": {
                        "type": "string",
                        "description": "Optional parent task ID"
                    }
                },
                "required": ["title", "owner_user_id"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Dependency State Machine Tools
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "propose_dependency",
            "description": "Propose that one task depends on another. Creates PROPOSED status if different owners.",
            "parameters": {
                "type": "object",
                "properties": {
                    "downstream_task_id": {
                        "type": "string",
                        "description": "The ID of the task that has the dependency"
                    },
                    "upstream_task_id": {
                        "type": "string",
                        "description": "The ID of the task being depended on"
                    }
                },
                "required": ["downstream_task_id", "upstream_task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "accept_dependency",
            "description": "Accept a PROPOSED dependency (upstream task owner).",
            "parameters": {
                "type": "object",
                "properties": {
                    "dependency_id": {
                        "type": "string",
                        "description": "The ID of the dependency to accept"
                    }
                },
                "required": ["dependency_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_dependency",
            "description": "Reject a PROPOSED dependency (upstream task owner). Requires a reason.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dependency_id": {
                        "type": "string",
                        "description": "The ID of the dependency to reject"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for rejection (required)"
                    }
                },
                "required": ["dependency_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_alternative_dependency",
            "description": "When rejecting a dependency, propose an alternative upstream task instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "original_dependency_id": {
                        "type": "string",
                        "description": "The ID of the original dependency being rejected"
                    },
                    "suggested_upstream_task_id": {
                        "type": "string",
                        "description": "The ID of the alternative upstream task"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for suggesting this alternative (required)"
                    }
                },
                "required": ["original_dependency_id", "suggested_upstream_task_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "accept_alternative_dependency",
            "description": "Accept an alternative dependency proposal (downstream task owner).",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the alternative dependency proposal to accept"
                    }
                },
                "required": ["proposal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_alternative_dependency",
            "description": "Reject an alternative dependency proposal. Requires a reason.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the alternative dependency proposal to reject"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for rejection (required)"
                    }
                },
                "required": ["proposal_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_dependencies",
            "description": "Get confirmed and proposed dependencies for a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    
    # -------------------------------------------------------------------------
    # NEW: Attribute Consensus Tool
    # -------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_attribute_consensus",
            "description": "Get the consensus state for an attribute on a task (NO_DATA, SINGLE_SOURCE, ALIGNED, MISALIGNED).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task"
                    },
                    "attribute_name": {
                        "type": "string",
                        "description": "Name of the attribute (e.g., 'status', 'priority')"
                    }
                },
                "required": ["task_id", "attribute_name"]
            }
        }
    }
]


# =============================================================================
# Helper Functions
# =============================================================================

def _user_summary(user: User) -> dict:
    """Build a compact user summary dict"""
    return {
        "id": str(user.id),
        "name": user.name,
        "role": user.role,
        "team": user.team
    }


def _get_user_reports_recursive(db: Session, user_id: UUID, depth: int = 10) -> List[User]:
    """Get all reports (direct and indirect) for a user, up to depth levels"""
    if depth <= 0:
        return []
    
    direct_reports = db.query(User).filter(User.manager_id == user_id).all()
    all_reports = list(direct_reports)
    
    for report in direct_reports:
        all_reports.extend(_get_user_reports_recursive(db, report.id, depth - 1))
    
    return all_reports


def _get_task_attribute_value(db: Session, task: Task, attr_name: str, user_id: UUID = None) -> Optional[str]:
    """Get a specific attribute value for a task"""
    attr = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == attr_name,
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not attr:
        return None
    
    # If user_id specified, get their answer; otherwise get owner's answer
    target_user_id = user_id or task.owner_user_id
    
    answer = db.query(AttributeAnswer).filter(
        AttributeAnswer.task_id == task.id,
        AttributeAnswer.attribute_id == attr.id,
        AttributeAnswer.answered_by_user_id == target_user_id
    ).order_by(AttributeAnswer.updated_at.desc()).first()
    
    return answer.value if answer else None


# =============================================================================
# Tool Implementation Functions - EXISTING
# =============================================================================

def get_user_context(db: Session, user_id: UUID) -> UserContext:
    """
    Get context about the current user.
    
    Returns: role, team, manager, timezone, employee info
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return UserContext(user_id=str(user_id), name="Unknown")
    
    manager_name = None
    manager_id = None
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id).first()
        if manager:
            manager_name = manager.name
            manager_id = str(manager.id)
    
    employees = user.employees if hasattr(user, 'employees') else []
    employee_names = [e.name for e in employees]
    
    return UserContext(
        user_id=str(user.id),
        name=user.name,
        email=user.email,
        team=user.team,
        role=user.role,
        manager_name=manager_name,
        manager_id=manager_id,
        timezone=user.timezone or "UTC",
        employee_count=len(employees),
        employee_names=employee_names
    )


def _build_task_context(db: Session, task: Task) -> TaskContext:
    """Helper to build TaskContext from a Task model"""
    # Get attribute values
    status = _get_task_attribute_value(db, task, "status")
    priority = _get_task_attribute_value(db, task, "priority")
    main_goal = _get_task_attribute_value(db, task, "main_goal")
    
    # Get owner
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    owner_name = owner.name if owner else "Unknown"
    
    # Get parent
    parent_title = None
    if task.parent_id:
        parent = db.query(Task).filter(Task.id == task.parent_id).first()
        if parent:
            parent_title = parent.title
    
    # Get children
    children = task.children if hasattr(task, 'children') else []
    children_titles = [c.title for c in children if c.is_active]
    
    # Get dependencies
    dependencies = task.dependencies if hasattr(task, 'dependencies') else []
    dependency_titles = [d.title for d in dependencies if d.is_active]
    
    is_blocked = status == "Blocked" if status else False
    
    return TaskContext(
        task_id=str(task.id),
        title=task.title,
        description=task.description,
        owner_name=owner_name,
        owner_id=str(task.owner_user_id),
        status=status,
        priority=priority,
        main_goal=main_goal,
        is_blocked=is_blocked,
        parent_title=parent_title,
        children_titles=children_titles,
        dependency_titles=dependency_titles
    )


def get_daily_task_context(db: Session, user_id: UUID) -> DailyTaskContext:
    """
    Get tasks relevant for Daily mode or Morning Brief.
    
    Includes: in-progress tasks, blocked items, high priority, 
    owned tasks, relevant tasks, and misalignments.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return DailyTaskContext()
    
    # Get owned tasks
    owned_tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    # Get tasks where user is relevant
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user_id
    ).all()
    relevant_task_ids = [r.task_id for r in relevant_entries]
    
    relevant_tasks = db.query(Task).filter(
        Task.id.in_(relevant_task_ids),
        Task.is_active == True
    ).all() if relevant_task_ids else []
    
    # Build task contexts
    owned_contexts = [_build_task_context(db, t) for t in owned_tasks]
    relevant_contexts = [_build_task_context(db, t) for t in relevant_tasks 
                        if t.id not in [o.id for o in owned_tasks]]
    
    # Categorize
    in_progress = [t for t in owned_contexts if t.status == "In progress"]
    blocked = [t for t in owned_contexts if t.is_blocked]
    high_priority = [t for t in owned_contexts if t.priority in ["Critical", "High"]]
    
    # Get misalignment count (simplified - using sync query)
    try:
        # Count low similarity scores for this user
        low_scores = db.query(SimilarityScore).join(
            AttributeAnswer,
            or_(
                SimilarityScore.answer_a_id == AttributeAnswer.id,
                SimilarityScore.answer_b_id == AttributeAnswer.id
            )
        ).filter(
            and_(
                or_(
                    AttributeAnswer.answered_by_user_id == user_id,
                    AttributeAnswer.target_user_id == user_id
                ),
                SimilarityScore.similarity_score < 0.6
            )
        ).limit(10).all()
        
        misalignment_count = len(low_scores)
        top_misalignments = []
    except Exception as e:
        logger.warning(f"Could not get misalignments: {e}")
        misalignment_count = 0
        top_misalignments = []
    
    return DailyTaskContext(
        tasks_in_progress=in_progress,
        tasks_blocked=blocked,
        tasks_high_priority=high_priority,
        tasks_owned=owned_contexts,
        tasks_relevant=relevant_contexts,
        misalignment_count=misalignment_count,
        top_misalignments=top_misalignments
    )


def get_questions_mode_context(db: Session, user_id: UUID) -> DailyTaskContext:
    """
    Get context relevant for Questions mode.
    Similar to daily context but may be filtered differently.
    """
    # For now, reuse daily context - can be customized later
    return get_daily_task_context(db, user_id)


def get_insight_questions_for_daily(
    db: Session, 
    user_id: UUID, 
    session: Optional[DailySyncSession] = None
) -> list[InsightQuestion]:
    """
    Get insight questions for the Daily Sync session.
    
    If session exists, uses its cached insight_questions.
    Otherwise, generates fresh from pending questions.
    """
    if session and session.insight_questions:
        # Use cached questions from session
        return [
            InsightQuestion(
                id=q.get("id", ""),
                text=q.get("text", ""),
                value=q.get("value", 0),
                reason=q.get("reason", ""),
                task_id=q.get("task_id"),
                task_title=q.get("task_title"),
                attribute_name=q.get("attribute_name")
            )
            for q in session.insight_questions
        ]
    
    # Generate from pending questions
    pending = get_pending_questions(db, user_id)
    
    return [
        InsightQuestion(
            id=str(p.id),
            text=f"What is the {p.attribute_label} for '{p.task_title}'?",
            value=10,  # Default value
            reason=f"Missing {p.attribute_label} data for task owned by {p.task_owner}",
            task_id=str(p.task_id) if p.task_id else None,
            task_title=p.task_title,
            attribute_name=p.attribute_name
        )
        for p in pending[:10]  # Limit to top 10
    ]


def get_pending_questions(db: Session, user_id: UUID) -> list[PendingQuestion]:
    """
    Get questions that need answers for perception mapping.
    Uses sync queries for the cortex tool context.
    """
    pending = []
    staleness_days = 7
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    # Get tasks owned by user
    owned_tasks = db.query(Task).filter(
        and_(
            Task.owner_user_id == user_id,
            Task.is_active == True
        )
    ).all()
    
    # Get tasks where user is marked as relevant
    relevant_task_ids = [
        r.task_id for r in db.query(TaskRelevantUser.task_id).filter(
            TaskRelevantUser.user_id == user_id
        ).all()
    ]
    
    relevant_tasks = []
    if relevant_task_ids:
        relevant_tasks = db.query(Task).filter(
            and_(
                Task.id.in_(relevant_task_ids),
                Task.is_active == True
            )
        ).all()
    
    # Combine and dedupe
    task_ids_seen = set()
    tasks = []
    for t in list(owned_tasks) + list(relevant_tasks):
        if t.id not in task_ids_seen:
            task_ids_seen.add(t.id)
            tasks.append(t)
    
    # Get all task attributes
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == "task"
    ).all()
    
    # For each task and attribute, check if pending
    for task in tasks:
        # Get task owner for reference
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        owner_name = owner.name if owner else "Unknown"
        
        for attr in attributes:
            # Check if this user has answered this (task, attribute)
            answer = db.query(AttributeAnswer).filter(
                and_(
                    AttributeAnswer.answered_by_user_id == user_id,
                    AttributeAnswer.target_user_id == task.owner_user_id,
                    AttributeAnswer.task_id == task.id,
                    AttributeAnswer.attribute_id == attr.id,
                    AttributeAnswer.refused == False
                )
            ).order_by(AttributeAnswer.updated_at.desc()).first()
            
            # Determine reason
            reason = None
            if answer is None:
                reason = "missing"
            elif answer.updated_at < datetime.utcnow() - timedelta(days=staleness_days):
                reason = "stale"
            
            # If we have a reason, add to pending
            if reason:
                pending.append(
                    PendingQuestion(
                        id=f"{task.id}_{attr.name}_{task.owner_user_id}",
                        task_id=str(task.id),
                        task_title=task.title,
                        task_owner=owner_name,
                        attribute_name=attr.name,
                        attribute_label=attr.label,
                        question=f"What is the {attr.label} for '{task.title}'?",
                        reason=f"Need {attr.label} perception from you for alignment tracking ({reason})",
                        value=10
                    )
                )
    
    return pending[:20]  # Limit to top 20


def record_observation(
    db: Session,
    user_id: UUID,
    payload: ObservationPayload
) -> dict:
    """
    Record an observation or update from the conversation.
    
    This creates/updates an AttributeAnswer record.
    """
    from app.services.similarity_cache import calculate_and_store_scores_for_answer
    
    # Find the task
    task = None
    if payload.task_name:
        task = db.query(Task).filter(
            Task.title.ilike(payload.task_name),
            Task.is_active == True
        ).first()
    elif payload.task_id:
        task = db.query(Task).filter(Task.id == payload.task_id).first()
    
    if not task and payload.task_name:
        logger.warning(f"Task not found: {payload.task_name}")
        return {"success": False, "error": f"Task not found: {payload.task_name}"}
    
    # Find the target user
    target_user = None
    if payload.target_user_name:
        target_user = db.query(User).filter(
            User.name.ilike(payload.target_user_name)
        ).first()
    elif payload.target_user_id:
        target_user = db.query(User).filter(User.id == payload.target_user_id).first()
    
    if not target_user:
        # Default to task owner if no target specified
        if task:
            target_user = db.query(User).filter(User.id == task.owner_user_id).first()
        else:
            target_user = db.query(User).filter(User.id == user_id).first()
    
    if not target_user:
        return {"success": False, "error": "Target user not found"}
    
    # Find the attribute
    attribute = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == payload.attribute_name,
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not attribute:
        logger.warning(f"Attribute not found: {payload.attribute_name}")
        return {"success": False, "error": f"Attribute not found: {payload.attribute_name}"}
    
    # Create or update the answer
    existing = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == user_id,
        AttributeAnswer.target_user_id == target_user.id,
        AttributeAnswer.task_id == (task.id if task else None),
        AttributeAnswer.attribute_id == attribute.id
    ).first()
    
    if existing:
        existing.value = payload.value
        existing.refused = False
        db.commit()
        answer_id = existing.id
    else:
        new_answer = AttributeAnswer(
            answered_by_user_id=user_id,
            target_user_id=target_user.id,
            task_id=task.id if task else None,
            attribute_id=attribute.id,
            value=payload.value,
            refused=False
        )
        db.add(new_answer)
        db.commit()
        db.refresh(new_answer)
        answer_id = new_answer.id
    
    # Calculate similarity scores (async function, need to run in sync context)
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            calculate_and_store_scores_for_answer(answer_id, db)
        )
    except Exception as e:
        logger.warning(f"Could not calculate similarity scores: {e}")
    
    return {
        "success": True,
        "answer_id": str(answer_id),
        "task": task.title if task else None,
        "attribute": payload.attribute_name,
        "value": payload.value
    }


# =============================================================================
# NEW: Org Structure / People Context Tools
# =============================================================================

def get_org_structure(db: Session, root_user_id: Optional[UUID] = None) -> dict:
    """
    Return a simple org structure: list of users with manager relationships.
    
    If root_user_id is provided, limit to that user and their (recursive) reports.
    Otherwise return the whole org.
    
    Output:
    {
      "users": [
        {
          "id": str,
          "name": str,
          "role": str | None,
          "team": str | None,
          "manager_id": str | None
        },
        ...
      ]
    }
    """
    if root_user_id:
        # Get root user and all their reports
        root_user = db.query(User).filter(User.id == root_user_id).first()
        if not root_user:
            return {"users": []}
        
        reports = _get_user_reports_recursive(db, root_user_id)
        users = [root_user] + reports
    else:
        # Get all users
        users = db.query(User).all()
    
    return {
        "users": [
            {
                "id": str(u.id),
                "name": u.name,
                "role": u.role,
                "team": u.team,
                "manager_id": str(u.manager_id) if u.manager_id else None
            }
            for u in users
        ]
    }


def get_user_profile(db: Session, user_id: UUID) -> dict:
    """
    Return detailed profile for a user.
    
    Output:
    {
      "id": str,
      "name": str,
      "email": str | None,
      "role": str | None,
      "team": str | None,
      "manager_id": str | None,
      "manager_name": str | None,
      "timezone": str | None,
      "direct_reports_count": int,
      "tasks_owned_count": int,
      "tags": list[str]
    }
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}
    
    # Get manager name
    manager_name = None
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id).first()
        if manager:
            manager_name = manager.name
    
    # Count direct reports
    direct_reports_count = db.query(User).filter(User.manager_id == user.id).count()
    
    # Count tasks owned
    tasks_owned_count = db.query(Task).filter(
        Task.owner_user_id == user.id,
        Task.is_active == True
    ).count()
    
    # Derive tags from role/team
    tags = []
    if user.role:
        tags.append(user.role)
    if user.team:
        tags.append(f"Team: {user.team}")
    if direct_reports_count > 0:
        tags.append("Manager")
    
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "team": user.team,
        "manager_id": str(user.manager_id) if user.manager_id else None,
        "manager_name": manager_name,
        "timezone": user.timezone or "UTC",
        "direct_reports_count": direct_reports_count,
        "tasks_owned_count": tasks_owned_count,
        "tags": tags
    }


def get_user_neighbors(db: Session, user_id: UUID) -> dict:
    """
    Returns manager, direct reports, peers, and relevant collaborators for this user.
    
    Output:
    {
      "manager": { ...user_summary... } | None,
      "direct_reports": [ ...user_summary... ],
      "peers": [ ...user_summary... ],
      "relevant_collaborators": [ ...user_summary... ]
    }
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}
    
    result = {
        "manager": None,
        "direct_reports": [],
        "peers": [],
        "relevant_collaborators": []
    }
    
    # Manager
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id).first()
        if manager:
            result["manager"] = _user_summary(manager)
    
    # Direct reports
    direct_reports = db.query(User).filter(User.manager_id == user_id).all()
    result["direct_reports"] = [_user_summary(u) for u in direct_reports]
    
    # Peers (same manager, excluding self)
    if user.manager_id:
        peers = db.query(User).filter(
            User.manager_id == user.manager_id,
            User.id != user_id
        ).all()
        result["peers"] = [_user_summary(u) for u in peers]
    
    # Relevant collaborators (from tasks where this user is owner or relevant)
    collaborator_ids = set()
    
    # Get tasks owned by user and find relevant users
    owned_tasks = db.query(Task).filter(Task.owner_user_id == user_id).all()
    for task in owned_tasks:
        relevant_entries = db.query(TaskRelevantUser).filter(
            TaskRelevantUser.task_id == task.id
        ).all()
        for entry in relevant_entries:
            if entry.user_id != user_id:
                collaborator_ids.add(entry.user_id)
    
    # Get tasks where user is relevant and add owners
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.user_id == user_id
    ).all()
    for entry in relevant_entries:
        task = db.query(Task).filter(Task.id == entry.task_id).first()
        if task and task.owner_user_id != user_id:
            collaborator_ids.add(task.owner_user_id)
    
    # Exclude manager, direct reports, and peers
    excluded_ids = {user_id}
    if user.manager_id:
        excluded_ids.add(user.manager_id)
    excluded_ids.update(u.id for u in direct_reports)
    if user.manager_id:
        excluded_ids.update(p.id for p in peers)
    
    collaborator_ids = collaborator_ids - excluded_ids
    
    collaborators = db.query(User).filter(User.id.in_(collaborator_ids)).all() if collaborator_ids else []
    result["relevant_collaborators"] = [_user_summary(u) for u in collaborators]
    
    return result


# =============================================================================
# NEW: Task & Alignment Context Tools
# =============================================================================

def get_tasks_for_user(
    db: Session,
    user_id: UUID,
    role: str = "all",
    active_only: bool = True,
    limit: int = 50,
) -> dict:
    """
    Return a list of tasks mapped to this user.
    
    Output:
    {
      "tasks": [
        {
          "id": str,
          "title": str,
          "state": str,  # DRAFT, ACTIVE, ARCHIVED
          "status": str | None,
          "priority": str | None,
          "owner_id": str | None,
          "owner_name": str | None,
          "parent_id": str | None,
          "has_children": bool,
          "has_blockers": bool,
          "main_goal": str | None,
          "due_date": str | None
        },
        ...
      ]
    }
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"tasks": []}
    
    task_ids_seen = set()
    tasks = []
    
    # Get owned tasks
    if role in ["owner", "all"]:
        query = db.query(Task).filter(Task.owner_user_id == user_id)
        if active_only:
            query = query.filter(Task.is_active == True)
        owned_tasks = query.limit(limit).all()
        
        for t in owned_tasks:
            if t.id not in task_ids_seen:
                task_ids_seen.add(t.id)
                tasks.append(t)
    
    # Get tasks where user is relevant
    if role in ["relevant", "all"]:
        relevant_entries = db.query(TaskRelevantUser.task_id).filter(
            TaskRelevantUser.user_id == user_id
        ).all()
        relevant_task_ids = [r.task_id for r in relevant_entries]
        
        if relevant_task_ids:
            query = db.query(Task).filter(Task.id.in_(relevant_task_ids))
            if active_only:
                query = query.filter(Task.is_active == True)
            relevant_tasks = query.limit(limit).all()
            
            for t in relevant_tasks:
                if t.id not in task_ids_seen:
                    task_ids_seen.add(t.id)
                    tasks.append(t)
    
    # Build output
    result_tasks = []
    for task in tasks[:limit]:
        status = _get_task_attribute_value(db, task, "status")
        priority = _get_task_attribute_value(db, task, "priority")
        main_goal = _get_task_attribute_value(db, task, "main_goal")
        
        owner = db.query(User).filter(User.id == task.owner_user_id).first()
        owner_name = owner.name if owner else None
        
        children = task.children if hasattr(task, 'children') else []
        active_children = [c for c in children if c.is_active]
        
        result_tasks.append({
            "id": str(task.id),
            "title": task.title,
            "state": task.state.value if task.state else "ACTIVE",
            "status": status,
            "priority": priority,
            "owner_id": str(task.owner_user_id) if task.owner_user_id else None,
            "owner_name": owner_name,
            "parent_id": str(task.parent_id) if task.parent_id else None,
            "has_children": len(active_children) > 0,
            "has_blockers": status == "Blocked",
            "main_goal": main_goal,
            "due_date": None  # Add if/when due_date field exists
        })
    
    return {"tasks": result_tasks}


def get_task_detail(db: Session, task_id: UUID) -> dict:
    """
    Return detailed info for a task: hierarchy, dependencies, key attributes, state, aliases.
    
    Output:
    {
      "task": {
        "id": str,
        "title": str,
        "description": str | None,
        "state": str,  # DRAFT, ACTIVE, ARCHIVED
        "owner_id": str | None,
        "owner_name": str | None,
        "creator_id": str | None,
        "creator_name": str | None,
        "status": str | None,
        "priority": str | None,
        "main_goal": str | None,
        "parent_id": str | None,
        "parent_title": str | None,
        "children": [ { "id": str, "title": str } ],
        "dependencies": [ { "id": str, "title": str } ],
        "confirmed_dependencies": [ { "id": str, "title": str } ],
        "proposed_dependencies": [ { "id": str, "title": str, "status": str } ],
        "is_blocked": bool,
        "relevant_users": [ { "id": str, "name": str } ],
        "aliases": [ { "title": str, "creator_name": str } ]
      }
    }
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}
    
    # Get owner
    owner = db.query(User).filter(User.id == task.owner_user_id).first()
    owner_name = owner.name if owner else None
    
    # Get creator
    creator_name = None
    creator_id = None
    if task.created_by_user_id:
        creator = db.query(User).filter(User.id == task.created_by_user_id).first()
        if creator:
            creator_name = creator.name
            creator_id = str(creator.id)
    
    # Get task state
    task_state = task.state.value if hasattr(task, 'state') and task.state else "ACTIVE"
    
    # Get attributes
    status = _get_task_attribute_value(db, task, "status")
    priority = _get_task_attribute_value(db, task, "priority")
    main_goal = _get_task_attribute_value(db, task, "main_goal")
    
    # Get parent
    parent_title = None
    if task.parent_id:
        parent = db.query(Task).filter(Task.id == task.parent_id).first()
        if parent:
            parent_title = parent.title
    
    # Get children
    children = task.children if hasattr(task, 'children') else []
    children_list = [
        {"id": str(c.id), "title": c.title}
        for c in children if c.is_active
    ]
    
    # Get dependencies (legacy)
    dependencies = task.dependencies if hasattr(task, 'dependencies') else []
    dependencies_list = [
        {"id": str(d.id), "title": d.title}
        for d in dependencies if d.is_active
    ]
    
    # Get V2 dependencies (state machine)
    confirmed_deps = []
    proposed_deps = []
    try:
        from app.models import TaskDependencyV2, DependencyStatus
        
        # Outgoing confirmed dependencies
        outgoing = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == task_id,
            TaskDependencyV2.status == DependencyStatus.CONFIRMED
        ).all()
        for dep in outgoing:
            upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
            if upstream:
                confirmed_deps.append({"id": str(upstream.id), "title": upstream.title})
        
        # Outgoing proposed dependencies
        proposed = db.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == task_id,
            TaskDependencyV2.status == DependencyStatus.PROPOSED
        ).all()
        for dep in proposed:
            upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
            if upstream:
                proposed_deps.append({
                    "id": str(upstream.id),
                    "title": upstream.title,
                    "status": "PROPOSED",
                    "dependency_id": str(dep.id)
                })
    except Exception as e:
        logger.warning(f"Could not fetch V2 dependencies: {e}")
    
    # Get relevant users
    relevant_entries = db.query(TaskRelevantUser).filter(
        TaskRelevantUser.task_id == task_id
    ).all()
    relevant_users = []
    for entry in relevant_entries:
        u = db.query(User).filter(User.id == entry.user_id).first()
        if u:
            relevant_users.append({"id": str(u.id), "name": u.name})
    
    # Get aliases (for merged tasks)
    aliases = []
    try:
        from app.models import TaskAlias
        alias_entries = db.query(TaskAlias).filter(TaskAlias.canonical_task_id == task_id).all()
        for alias in alias_entries:
            alias_creator = db.query(User).filter(User.id == alias.alias_created_by_user_id).first()
            aliases.append({
                "title": alias.alias_title,
                "creator_name": alias_creator.name if alias_creator else "Unknown"
            })
    except Exception as e:
        logger.warning(f"Could not fetch aliases: {e}")
    
    return {
        "task": {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "state": task_state,
            "owner_id": str(task.owner_user_id) if task.owner_user_id else None,
            "owner_name": owner_name,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "status": status,
            "priority": priority,
            "main_goal": main_goal,
            "parent_id": str(task.parent_id) if task.parent_id else None,
            "parent_title": parent_title,
            "children": children_list,
            "dependencies": dependencies_list,
            "confirmed_dependencies": confirmed_deps,
            "proposed_dependencies": proposed_deps,
            "is_blocked": status == "Blocked",
            "relevant_users": relevant_users,
            "aliases": aliases
        }
    }


def get_user_alignment_summary(db: Session, user_id: UUID, limit: int = 10) -> dict:
    """
    Return tasks/attributes where this user's answers diverge most from others.
    
    Output:
    {
      "misalignments": [
        {
          "task_id": str,
          "task_title": str,
          "attribute_name": str,
          "my_value": str | None,
          "others_values": list[str],
          "similarity_score": float | None
        },
        ...
      ]
    }
    """
    # Get user's answers
    user_answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == user_id,
        AttributeAnswer.task_id.isnot(None)
    ).all()
    
    if not user_answers:
        return {"misalignments": []}
    
    misalignments = []
    
    for user_answer in user_answers:
        # Get similarity scores for this answer
        low_scores = db.query(SimilarityScore).filter(
            or_(
                SimilarityScore.answer_a_id == user_answer.id,
                SimilarityScore.answer_b_id == user_answer.id
            ),
            SimilarityScore.similarity_score < 0.7  # Threshold for misalignment
        ).order_by(SimilarityScore.similarity_score.asc()).limit(5).all()
        
        for score in low_scores:
            # Get the other answer
            other_answer_id = score.answer_b_id if score.answer_a_id == user_answer.id else score.answer_a_id
            other_answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.id == other_answer_id
            ).first()
            
            if not other_answer:
                continue
            
            # Get task and attribute info
            task = db.query(Task).filter(Task.id == user_answer.task_id).first()
            attr = db.query(AttributeDefinition).filter(
                AttributeDefinition.id == user_answer.attribute_id
            ).first()
            
            if not task or not attr:
                continue
            
            misalignments.append({
                "task_id": str(task.id),
                "task_title": task.title,
                "attribute_name": attr.name,
                "my_value": user_answer.value,
                "others_values": [other_answer.value] if other_answer.value else [],
                "similarity_score": score.similarity_score
            })
    
    # Sort by score (lowest first = most misaligned)
    misalignments.sort(key=lambda x: x.get("similarity_score") or 0)
    
    return {"misalignments": misalignments[:limit]}


def get_task_alignment_hotspots(db: Session, task_id: UUID) -> dict:
    """
    For a task, return attributes with high disagreement and example values.
    
    Output:
    {
      "task_id": str,
      "task_title": str,
      "hotspots": [
        {
          "attribute_name": str,
          "values": [
            {
              "value": str,
              "user_ids": [str],
              "user_names": [str]
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}
    
    # Get all answers for this task
    answers = db.query(AttributeAnswer).filter(
        AttributeAnswer.task_id == task_id
    ).all()
    
    # Group by attribute
    attr_groups = {}
    for answer in answers:
        attr_id = answer.attribute_id
        if attr_id not in attr_groups:
            attr_groups[attr_id] = []
        attr_groups[attr_id].append(answer)
    
    hotspots = []
    
    for attr_id, attr_answers in attr_groups.items():
        # Get attribute name
        attr = db.query(AttributeDefinition).filter(
            AttributeDefinition.id == attr_id
        ).first()
        if not attr:
            continue
        
        # Group by value
        value_groups = {}
        for ans in attr_answers:
            value = ans.value or "(no value)"
            if value not in value_groups:
                value_groups[value] = {"user_ids": [], "user_names": []}
            
            user = db.query(User).filter(User.id == ans.answered_by_user_id).first()
            value_groups[value]["user_ids"].append(str(ans.answered_by_user_id))
            value_groups[value]["user_names"].append(user.name if user else "Unknown")
        
        # Only include as hotspot if there's disagreement (multiple different values)
        if len(value_groups) > 1:
            hotspots.append({
                "attribute_name": attr.name,
                "values": [
                    {
                        "value": val,
                        "user_ids": data["user_ids"],
                        "user_names": data["user_names"]
                    }
                    for val, data in value_groups.items()
                ]
            })
    
    return {
        "task_id": str(task.id),
        "task_title": task.title,
        "hotspots": hotspots
    }


# =============================================================================
# NEW: Data-Collection Utility Tools
# =============================================================================

def get_attribute_fill_status(
    db: Session,
    user_id: UUID,
    staleness_days: int = 7
) -> dict:
    """
    For tasks relevant to this user, indicate which task attributes are
    missing or stale for this user.
    
    Output:
    {
      "items": [
        {
          "task_id": str,
          "task_title": str,
          "attribute_name": str,
          "status": "missing" | "stale"
        },
        ...
      ]
    }
    """
    # This reuses logic from get_pending_questions
    pending = get_pending_questions(db, user_id)
    
    items = []
    for p in pending:
        status = "stale" if "stale" in p.reason else "missing"
        items.append({
            "task_id": p.task_id,
            "task_title": p.task_title,
            "attribute_name": p.attribute_name,
            "status": status
        })
    
    return {"items": items}


def upsert_attribute_answer(
    db: Session,
    answered_by_user_id: UUID,
    task_id: UUID,
    target_user_id: UUID,
    attribute_name: str,
    value: str,
    refused: bool = False,
    notes: Optional[str] = None,
) -> dict:
    """
    Insert or update an AttributeAnswer row, and return a small summary.
    
    Output:
    {
      "status": "ok",
      "answer_id": str
    }
    """
    from app.services.similarity_cache import calculate_and_store_scores_for_answer
    
    # Resolve attribute
    attribute = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == attribute_name,
        AttributeDefinition.entity_type == EntityType.TASK
    ).first()
    
    if not attribute:
        return {"status": "error", "error": f"Attribute not found: {attribute_name}"}
    
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"status": "error", "error": f"Task not found: {task_id}"}
    
    # Verify target user exists
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        return {"status": "error", "error": f"Target user not found: {target_user_id}"}
    
    # Check for existing answer
    existing = db.query(AttributeAnswer).filter(
        AttributeAnswer.answered_by_user_id == answered_by_user_id,
        AttributeAnswer.target_user_id == target_user_id,
        AttributeAnswer.task_id == task_id,
        AttributeAnswer.attribute_id == attribute.id
    ).first()
    
    if existing:
        existing.value = value
        existing.refused = refused
        existing.updated_at = datetime.utcnow()
        db.commit()
        answer_id = existing.id
    else:
        new_answer = AttributeAnswer(
            answered_by_user_id=answered_by_user_id,
            target_user_id=target_user_id,
            task_id=task_id,
            attribute_id=attribute.id,
            value=value,
            refused=refused
        )
        db.add(new_answer)
        db.commit()
        db.refresh(new_answer)
        answer_id = new_answer.id
    
    # Calculate similarity scores (async function, need to run in sync context)
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            calculate_and_store_scores_for_answer(answer_id, db)
        )
    except Exception as e:
        logger.warning(f"Could not calculate similarity scores: {e}")
    
    return {
        "status": "ok",
        "answer_id": str(answer_id),
        "task_title": task.title,
        "attribute": attribute_name,
        "value": value
    }


# =============================================================================
# Tool Executor - Dispatches tool calls from LLM
# =============================================================================

def execute_tool(
    db: Session,
    user_id: UUID,
    tool_name: str,
    tool_args: dict,
    daily_session: Optional[DailySyncSession] = None
) -> dict:
    """
    Execute a Cortex tool and return the result as a dict.
    
    This is called when the LLM makes a tool call.
    """
    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
    
    # -------------------------------------------------------------------------
    # Existing tools
    # -------------------------------------------------------------------------
    if tool_name == "get_user_context":
        result = get_user_context(db, user_id)
        return result.model_dump()
    
    elif tool_name == "get_daily_task_context":
        result = get_daily_task_context(db, user_id)
        return result.model_dump()
    
    elif tool_name == "get_questions_mode_context":
        result = get_questions_mode_context(db, user_id)
        return result.model_dump()
    
    elif tool_name == "get_insight_questions_for_daily":
        result = get_insight_questions_for_daily(db, user_id, daily_session)
        return {"questions": [q.model_dump() for q in result]}
    
    elif tool_name == "get_pending_questions":
        result = get_pending_questions(db, user_id)
        return {"questions": [q.model_dump() for q in result]}
    
    elif tool_name == "record_observation":
        payload = ObservationPayload(**tool_args)
        return record_observation(db, user_id, payload)
    
    # -------------------------------------------------------------------------
    # NEW: Org Structure / People Context Tools
    # -------------------------------------------------------------------------
    elif tool_name == "get_org_structure":
        root_user_id = None
        if tool_args.get("root_user_id"):
            root_user_id = UUID(tool_args["root_user_id"])
        return get_org_structure(db, root_user_id)
    
    elif tool_name == "get_user_profile":
        target_user_id = UUID(tool_args["user_id"])
        return get_user_profile(db, target_user_id)
    
    elif tool_name == "get_user_neighbors":
        target_user_id = UUID(tool_args["user_id"])
        return get_user_neighbors(db, target_user_id)
    
    # -------------------------------------------------------------------------
    # NEW: Task & Alignment Context Tools
    # -------------------------------------------------------------------------
    elif tool_name == "get_tasks_for_user":
        target_user_id = UUID(tool_args["user_id"])
        role = tool_args.get("role", "all")
        active_only = tool_args.get("active_only", True)
        limit = tool_args.get("limit", 50)
        return get_tasks_for_user(db, target_user_id, role, active_only, limit)
    
    elif tool_name == "get_task_detail":
        target_task_id = UUID(tool_args["task_id"])
        return get_task_detail(db, target_task_id)
    
    elif tool_name == "get_user_alignment_summary":
        target_user_id = UUID(tool_args["user_id"])
        limit = tool_args.get("limit", 10)
        return get_user_alignment_summary(db, target_user_id, limit)
    
    elif tool_name == "get_task_alignment_hotspots":
        target_task_id = UUID(tool_args["task_id"])
        return get_task_alignment_hotspots(db, target_task_id)
    
    # -------------------------------------------------------------------------
    # NEW: Data-Collection Utility Tools
    # -------------------------------------------------------------------------
    elif tool_name == "get_attribute_fill_status":
        target_user_id = UUID(tool_args["user_id"])
        staleness_days = tool_args.get("staleness_days", 7)
        return get_attribute_fill_status(db, target_user_id, staleness_days)
    
    elif tool_name == "upsert_attribute_answer":
        target_task_id = UUID(tool_args["task_id"])
        target_user_id = UUID(tool_args["target_user_id"])
        attribute_name = tool_args["attribute_name"]
        value = tool_args["value"]
        refused = tool_args.get("refused", False)
        notes = tool_args.get("notes")
        return upsert_attribute_answer(
            db=db,
            answered_by_user_id=user_id,
            task_id=target_task_id,
            target_user_id=target_user_id,
            attribute_name=attribute_name,
            value=value,
            refused=refused,
            notes=notes
        )
    
    # -------------------------------------------------------------------------
    # NEW: Task State Machine Tools
    # -------------------------------------------------------------------------
    elif tool_name == "get_pending_decisions":
        decisions = state_machines.get_pending_decisions_for_user(db, user_id)
        return {
            "decisions": [
                {
                    "id": str(d.id),
                    "type": d.decision_type.value,
                    "entity_type": d.entity_type,
                    "entity_id": str(d.entity_id),
                    "description": d.description,
                    "created_at": d.created_at.isoformat() if d.created_at else None
                }
                for d in decisions
            ]
        }
    
    elif tool_name == "accept_task":
        task = db.query(Task).filter(Task.id == UUID(tool_args["task_id"])).first()
        if not task:
            return {"error": "Task not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.accept_task(db, task, actor)
            return {"status": "ok", "task_id": str(result.id), "new_state": result.state.value}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "reject_task":
        task = db.query(Task).filter(Task.id == UUID(tool_args["task_id"])).first()
        if not task:
            return {"error": "Task not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.reject_task(db, task, actor, tool_args["reason"])
            return {"status": "ok", "task_id": str(result.id), "new_state": result.state.value}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "propose_task_merge":
        from_task = db.query(Task).filter(Task.id == UUID(tool_args["from_task_id"])).first()
        to_task = db.query(Task).filter(Task.id == UUID(tool_args["to_task_id"])).first()
        if not from_task or not to_task:
            return {"error": "Task not found"}
        proposer = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.propose_task_merge(db, from_task, to_task, proposer, tool_args["reason"])
            return {"status": "ok", "proposal_id": str(result.id)}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "accept_merge_proposal":
        proposal = db.query(TaskMergeProposal).filter(TaskMergeProposal.id == UUID(tool_args["proposal_id"])).first()
        if not proposal:
            return {"error": "Merge proposal not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.accept_merge_proposal(db, proposal, actor)
            return {"status": "ok", "proposal_id": str(result.id), "merged": True}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "reject_merge_proposal":
        proposal = db.query(TaskMergeProposal).filter(TaskMergeProposal.id == UUID(tool_args["proposal_id"])).first()
        if not proposal:
            return {"error": "Merge proposal not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.reject_merge_proposal(db, proposal, actor, tool_args["reason"])
            return {"status": "ok", "proposal_id": str(result.id)}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "create_task_for_user":
        owner = db.query(User).filter(User.id == UUID(tool_args["owner_user_id"])).first()
        if not owner:
            return {"error": "Owner user not found"}
        creator = db.query(User).filter(User.id == user_id).first()
        parent_id = UUID(tool_args["parent_task_id"]) if tool_args.get("parent_task_id") else None
        try:
            result = state_machines.create_task_with_state(
                db=db,
                title=tool_args["title"],
                owner=owner,
                creator=creator,
                description=tool_args.get("description"),
                parent_id=parent_id
            )
            return {
                "status": "ok",
                "task_id": str(result.id),
                "title": result.title,
                "state": result.state.value
            }
        except ValueError as e:
            return {"error": str(e)}
    
    # -------------------------------------------------------------------------
    # NEW: Dependency State Machine Tools
    # -------------------------------------------------------------------------
    elif tool_name == "propose_dependency":
        downstream = db.query(Task).filter(Task.id == UUID(tool_args["downstream_task_id"])).first()
        upstream = db.query(Task).filter(Task.id == UUID(tool_args["upstream_task_id"])).first()
        if not downstream or not upstream:
            return {"error": "Task not found"}
        requester = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.propose_dependency(db, requester, downstream, upstream)
            return {
                "status": "ok",
                "dependency_id": str(result.id),
                "dep_status": result.status.value
            }
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "accept_dependency":
        dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == UUID(tool_args["dependency_id"])).first()
        if not dep:
            return {"error": "Dependency not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.accept_dependency(db, dep, actor)
            return {"status": "ok", "dependency_id": str(result.id), "dep_status": result.status.value}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "reject_dependency":
        dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == UUID(tool_args["dependency_id"])).first()
        if not dep:
            return {"error": "Dependency not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.reject_dependency(db, dep, actor, tool_args["reason"])
            return {"status": "ok", "dependency_id": str(result.id), "dep_status": result.status.value}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "propose_alternative_dependency":
        dep = db.query(TaskDependencyV2).filter(TaskDependencyV2.id == UUID(tool_args["original_dependency_id"])).first()
        if not dep:
            return {"error": "Dependency not found"}
        suggested = db.query(Task).filter(Task.id == UUID(tool_args["suggested_upstream_task_id"])).first()
        if not suggested:
            return {"error": "Suggested upstream task not found"}
        proposer = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.propose_alternative_dependency(db, dep, suggested, proposer, tool_args["reason"])
            return {"status": "ok", "proposal_id": str(result.id)}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "accept_alternative_dependency":
        proposal = db.query(AlternativeDependencyProposal).filter(
            AlternativeDependencyProposal.id == UUID(tool_args["proposal_id"])
        ).first()
        if not proposal:
            return {"error": "Alternative dependency proposal not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            proposal_result, dep_result = state_machines.accept_alternative_dependency(db, proposal, actor)
            return {
                "status": "ok",
                "proposal_id": str(proposal_result.id),
                "new_dependency_id": str(dep_result.id)
            }
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "reject_alternative_dependency":
        proposal = db.query(AlternativeDependencyProposal).filter(
            AlternativeDependencyProposal.id == UUID(tool_args["proposal_id"])
        ).first()
        if not proposal:
            return {"error": "Alternative dependency proposal not found"}
        actor = db.query(User).filter(User.id == user_id).first()
        try:
            result = state_machines.reject_alternative_dependency(db, proposal, actor, tool_args["reason"])
            return {"status": "ok", "proposal_id": str(result.id)}
        except ValueError as e:
            return {"error": str(e)}
    
    elif tool_name == "get_task_dependencies":
        task_id = UUID(tool_args["task_id"])
        outgoing, incoming = state_machines.get_confirmed_dependencies_for_task(db, task_id)
        proposed = state_machines.get_proposed_dependencies_for_task(db, task_id)
        
        def dep_to_dict(dep):
            downstream = db.query(Task).filter(Task.id == dep.downstream_task_id).first()
            upstream = db.query(Task).filter(Task.id == dep.upstream_task_id).first()
            return {
                "id": str(dep.id),
                "downstream_task_id": str(dep.downstream_task_id),
                "downstream_title": downstream.title if downstream else None,
                "upstream_task_id": str(dep.upstream_task_id),
                "upstream_title": upstream.title if upstream else None,
                "status": dep.status.value
            }
        
        return {
            "task_id": str(task_id),
            "outgoing_confirmed": [dep_to_dict(d) for d in outgoing],
            "incoming_confirmed": [dep_to_dict(d) for d in incoming],
            "proposed": [dep_to_dict(d) for d in proposed]
        }
    
    # -------------------------------------------------------------------------
    # NEW: Attribute Consensus Tool
    # -------------------------------------------------------------------------
    elif tool_name == "get_attribute_consensus":
        task_id = UUID(tool_args["task_id"])
        attribute_name = tool_args["attribute_name"]
        result = state_machines.compute_attribute_consensus(db, "task", task_id, attribute_name)
        return {
            "state": result.state.value,
            "is_stale": result.is_stale,
            "similarity_score": result.similarity_score,
            "answers": [
                {
                    "user_id": a.user_id,
                    "user_name": a.user_name,
                    "value": a.value,
                    "updated_at": a.updated_at.isoformat() if a.updated_at else None
                }
                for a in result.answers
            ]
        }
    
    else:
        logger.warning(f"Unknown tool: {tool_name}")
        return {"error": f"Unknown tool: {tool_name}"}
