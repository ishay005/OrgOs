"""
Robin AI Assistant Orchestrator

Robin is an AI assistant that helps users align their work by:
1. Providing status summaries and morning briefs
2. Asking targeted questions to fill task attributes
3. Parsing free-text answers into structured data updates
"""
import logging
import json
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import AsyncOpenAI

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, AlignmentEdge,
    ChatMessage, EntityType
)
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)


# ============================================================================
# Data Models
# ============================================================================

class StructuredUpdate(BaseModel):
    """Represents a structured update to be applied to the database"""
    task_id: Optional[UUID] = None
    target_user_id: UUID  # Whose perception is being updated
    attribute_name: str   # Matches AttributeDefinition.name
    value: str            # Raw value


class RobinMessage(BaseModel):
    """A message from Robin to display in the chat"""
    text: str
    metadata: Optional[dict] = None


class RobinReply(BaseModel):
    """Complete reply from Robin including messages and structured updates"""
    messages: list[RobinMessage]
    updates: list[StructuredUpdate]


# ============================================================================
# Context Building
# ============================================================================

def _build_user_context(db: Session, user_id: UUID) -> dict:
    """Build context about the user for Robin"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}
    
    # Get aligned users
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    aligned_user_ids = [a.target_user_id for a in alignments]
    aligned_users = db.query(User).filter(User.id.in_(aligned_user_ids)).all() if aligned_user_ids else []
    
    # Get manager
    manager = db.query(User).filter(User.id == user.manager_id).first() if user.manager_id else None
    
    # Get team members (if user is a manager)
    team_members = db.query(User).filter(User.manager_id == user_id).all()
    
    return {
        "user_name": user.name,
        "user_id": str(user_id),
        "manager": manager.name if manager else None,
        "aligned_users": [{"id": str(u.id), "name": u.name} for u in aligned_users],
        "team_members": [{"id": str(u.id), "name": u.name} for u in team_members]
    }


def _build_task_context(db: Session, user_id: UUID) -> list[dict]:
    """Build context about relevant tasks"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    # Get user's own tasks
    my_tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    # Get aligned users' tasks (limited to avoid context overflow)
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    aligned_user_ids = [a.target_user_id for a in alignments]
    
    aligned_tasks = db.query(Task).filter(
        Task.owner_user_id.in_(aligned_user_ids),
        Task.is_active == True
    ).limit(10).all() if aligned_user_ids else []
    
    all_tasks = my_tasks + aligned_tasks
    
    # Build task summaries with key attributes
    task_summaries = []
    for task in all_tasks[:15]:  # Limit to 15 tasks total
        # Get key attributes for this task
        answers = db.query(AttributeAnswer).filter(
            AttributeAnswer.task_id == task.id,
            AttributeAnswer.answered_by_user_id == task.owner_user_id,
            AttributeAnswer.target_user_id == task.owner_user_id,
            AttributeAnswer.refused == False
        ).all()
        
        attributes = {}
        for answer in answers:
            attr = db.query(AttributeDefinition).filter(
                AttributeDefinition.id == answer.attribute_id
            ).first()
            if attr:
                attributes[attr.name] = answer.value
        
        task_summaries.append({
            "id": str(task.id),
            "title": task.title,
            "description": task.description or "",
            "owner": task.owner.name,
            "is_mine": task.owner_user_id == user_id,
            "attributes": attributes
        })
    
    return task_summaries


def _find_pending_attributes(db: Session, user_id: UUID) -> list[dict]:
    """Find attributes that need to be filled or updated"""
    # Get all task attributes
    task_attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    # Get user's tasks and aligned users' tasks
    my_tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    aligned_user_ids = [a.target_user_id for a in alignments]
    
    aligned_tasks = db.query(Task).filter(
        Task.owner_user_id.in_(aligned_user_ids),
        Task.is_active == True
    ).limit(5).all() if aligned_user_ids else []
    
    pending = []
    
    # Check for missing answers on own tasks
    for task in my_tasks[:5]:  # Limit to avoid overwhelming
        for attr in task_attributes:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == user_id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).first()
            
            if not answer:
                pending.append({
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "attribute_name": attr.name,
                    "attribute_label": attr.label,
                    "target_user_id": str(user_id),
                    "is_about_self": True
                })
                if len(pending) >= 5:  # Limit to 5 pending items
                    return pending
    
    # Check for missing answers about aligned users' tasks
    for task in aligned_tasks:
        for attr in task_attributes:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == task.owner_user_id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).first()
            
            if not answer:
                pending.append({
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "attribute_name": attr.name,
                    "attribute_label": attr.label,
                    "target_user_id": str(task.owner_user_id),
                    "is_about_self": False
                })
                if len(pending) >= 5:
                    return pending
    
    return pending


def _build_chat_history_context(db: Session, thread_id: UUID, limit: int = 10) -> list[dict]:
    """Get recent chat history for context"""
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    # Reverse to get chronological order
    messages = list(reversed(messages))
    
    return [
        {
            "sender": msg.sender if isinstance(msg.sender, str) else msg.sender.value,
            "text": msg.text[:200]  # Truncate long messages
        }
        for msg in messages
    ]


# ============================================================================
# System Prompt
# ============================================================================

ROBIN_SYSTEM_PROMPT = """You are Robin, an AI assistant helping team members align their work.

Your role:
- Provide concise status summaries and morning briefs
- Ask targeted questions to fill or update task attributes
- Parse free-text answers into structured data updates
- Never be fluffy - always be practical and concise

Available task attributes you can update:
- priority: Critical, High, Medium, Low
- status: Not started, In progress, Blocked, Done
- perceived_owner: Name of the person responsible
- main_goal: Free-text description of the task's goal
- And other attributes as defined in the ontology

When responding, you have TWO outputs:
1. Natural language messages to show the user
2. Structured updates to apply to the database

Output format - you MUST respond with valid JSON in this exact structure:
{
  "display_messages": ["message 1", "message 2"],
  "updates": [
    {
      "task_id": "uuid-or-null",
      "target_user_id": "uuid",
      "attribute_name": "status",
      "value": "In progress"
    }
  ]
}

Special commands:
- "morning_brief": Summarize active tasks and highlight blockers
- "status": Quick overview of task status
- User free-text: Parse and extract structured updates

Key rules:
1. ALWAYS output valid JSON with "display_messages" and "updates" fields
2. Keep messages SHORT (1-2 sentences each)
3. Only create updates when you're confident about the values
4. If task_id is not clear, use null
5. target_user_id is the person whose perception is being updated (usually the user)
6. Be proactive - suggest next steps, ask clarifying questions"""


# ============================================================================
# Main Orchestrator Function
# ============================================================================

async def generate_robin_reply(
    user_id: UUID,
    thread_id: UUID,
    user_message: str,
    db: Session
) -> RobinReply:
    """
    Generate Robin's reply to a user message.
    
    This function:
    1. Builds context about the user, tasks, and pending items
    2. Calls OpenAI to generate a response
    3. Parses the response into messages and structured updates
    4. Returns a RobinReply object
    """
    logger.info(f"Generating Robin reply for user {user_id}, message: '{user_message[:50]}...'")
    
    try:
        # Build context
        user_context = _build_user_context(db, user_id)
        task_context = _build_task_context(db, user_id)
        pending_attributes = _find_pending_attributes(db, user_id)
        chat_history = _build_chat_history_context(db, thread_id)
        
        # Build context string for the LLM
        context_str = f"""
USER CONTEXT:
{json.dumps(user_context, indent=2)}

TASKS (showing {len(task_context)} most relevant):
{json.dumps(task_context, indent=2)}

PENDING ATTRIBUTES (need to be filled):
{json.dumps(pending_attributes, indent=2)}

RECENT CHAT HISTORY:
{json.dumps(chat_history, indent=2)}
"""
        
        # Build the full messages array for OpenAI
        openai_messages = [
            {"role": "system", "content": ROBIN_SYSTEM_PROMPT},
            {"role": "system", "content": f"Context:\n{context_str}"},
            {"role": "user", "content": user_message}
        ]
        
        # Call OpenAI
        logger.info(f"Calling OpenAI GPT-5 mini for user {user_id}...")
        response = await client.chat.completions.create(
            model="gpt-5-mini",  # Latest model: 400K context, $0.25/1M input, $2/1M output
            messages=openai_messages,
            # temperature not specified - GPT-5 mini only supports default value of 1
            max_completion_tokens=2000  # GPT-5 mini uses max_completion_tokens instead of max_tokens
        )
        
        assistant_reply = response.choices[0].message.content
        logger.info(f"OpenAI response received: {assistant_reply[:100]}...")
        
        # Store the full prompt for debugging
        full_prompt_debug = {
            "model": "gpt-5-mini",
            "messages": openai_messages,
            "user_context": user_context,
            "task_count": len(task_context),
            "pending_count": len(pending_attributes)
        }
        
        # Parse JSON response
        try:
            # Extract JSON from response (might be wrapped in markdown code blocks)
            json_str = assistant_reply
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(json_str)
            
            # Extract messages
            messages = [
                RobinMessage(text=msg)
                for msg in parsed.get("display_messages", [])
            ]
            
            # Extract updates
            updates = []
            for upd in parsed.get("updates", []):
                try:
                    # Parse UUIDs
                    task_id = UUID(upd["task_id"]) if upd.get("task_id") and upd["task_id"] != "null" else None
                    target_user_id = UUID(upd["target_user_id"])
                    
                    updates.append(StructuredUpdate(
                        task_id=task_id,
                        target_user_id=target_user_id,
                        attribute_name=upd["attribute_name"],
                        value=upd["value"]
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse update: {upd}, error: {e}")
            
            logger.info(f"Parsed {len(messages)} messages and {len(updates)} updates")
            
            # Add debug info to the first message
            if messages:
                if messages[0].metadata is None:
                    messages[0].metadata = {}
                messages[0].metadata["debug_prompt"] = full_prompt_debug
            
            return RobinReply(messages=messages, updates=updates)
            
        except json.JSONDecodeError as e:
            # Fallback: treat entire response as a single message
            logger.warning(f"Failed to parse JSON from OpenAI response: {e}")
            logger.warning(f"Response was: {assistant_reply}")
            
            return RobinReply(
                messages=[RobinMessage(
                    text=assistant_reply,
                    metadata={
                        "parse_error": True,
                        "debug_prompt": full_prompt_debug
                    }
                )],
                updates=[]
            )
    
    except Exception as e:
        logger.error(f"Error in generate_robin_reply: {e}", exc_info=True)
        
        # Return error message to user
        return RobinReply(
            messages=[RobinMessage(
                text="Sorry, I encountered an error. Please try again.",
                metadata={"error": str(e)}
            )],
            updates=[]
        )

