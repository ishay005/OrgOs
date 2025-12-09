"""
Robin AI Assistant Orchestrator - Mode-Based with Pending Questions

Robin operates in 3 modes:
1. morning_brief - Daily brief, optionally ask up to 2 questions if relevant pending items exist
2. user_question - Answer user's question, optionally ask 1 follow-up if relevant pending item exists
3. collect_data - Explicitly collect data for pending items (ask up to 3 questions)

Key principle: Robin only asks questions when there are relevant pending items for that mode.
"""
import logging
import json
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.models import (
    User, Task, AttributeDefinition, AttributeAnswer, AlignmentEdge,
    ChatMessage, EntityType
)
from app.config import settings
from app.services.questions import get_pending_questions_for_user, PendingQuestion

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
# Mode Classification
# ============================================================================

def _classify_mode(user_message: str) -> str:
    """
    Classify the conversation mode based on user message.
    Returns: "morning_brief" | "collect_data" | "user_question"
    """
    msg_lower = user_message.lower().strip()
    
    # Explicit triggers
    if msg_lower in ["morning_brief", "brief", "morning brief"]:
        return "morning_brief"
    
    if msg_lower in ["collect_data", "collect", "update", "fill attributes"]:
        return "collect_data"
    
    # Default to user_question
    return "user_question"


# ============================================================================
# Context Building (Simplified per Mode)
# ============================================================================

def _get_user_snapshot(db: Session, user_id: UUID) -> dict:
    """Get basic user info: name, manager, employees"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}
    
    manager = db.query(User).filter(User.id == user.manager_id).first() if user.manager_id else None
    employees = db.query(User).filter(User.manager_id == user_id).all()
    
    return {
        "name": user.name,
        "manager": manager.name if manager else None,
        "employees": [e.name for e in employees] if employees else []
    }


def _get_task_snapshot(db: Session, user_id: UUID) -> List[dict]:
    """Get user's tasks and aligned users' tasks with key attributes"""
    # Get user's own tasks
    my_tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    # Get aligned users
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    aligned_user_ids = [a.target_user_id for a in alignments]
    
    # Get aligned users' tasks
    aligned_tasks = db.query(Task).filter(
        Task.owner_user_id.in_(aligned_user_ids),
        Task.is_active == True
    ).limit(10).all() if aligned_user_ids else []
    
    all_tasks = list(my_tasks) + list(aligned_tasks)
    
    # Build task summaries
    task_summaries = []
    for task in all_tasks[:15]:  # Limit to 15 tasks
        # Get key attributes
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
            "title": task.title,
            "owner": task.owner.name,
            "is_mine": task.owner_user_id == user_id,
            "attributes": attributes
        })
    
    return task_summaries


def _filter_pending_by_mode(
    pending: List[PendingQuestion],
    mode: str,
    task_snapshot: List[dict]
) -> List[PendingQuestion]:
    """
    Filter pending questions based on mode and context.
    
    morning_brief: Up to 2 items from top tasks
    user_question: Up to 1 item (would need topic matching, simplified here)
    collect_data: Up to 5 high-priority items
    """
    if mode == "morning_brief":
        # Get task titles from snapshot
        top_task_titles = [t["title"] for t in task_snapshot[:5]]
        # Filter pending to only those tasks
        filtered = [p for p in pending if _get_task_title_for_pending(p, task_snapshot) in top_task_titles]
        return filtered[:2]
    
    elif mode == "user_question":
        # In a full implementation, we'd match user's question to tasks/topics
        # For now, return at most 1 high-priority item
        return pending[:1]
    
    elif mode == "collect_data":
        # Return top 5 high-priority items
        return pending[:5]
    
    return []


def _get_task_title_for_pending(pending: PendingQuestion, task_snapshot: List[dict]) -> str:
    """Helper to get task title from snapshot"""
    # This is a simplified lookup; in practice, you'd match by task_id
    # For now, just return empty string
    return ""


# ============================================================================
# System Prompts (Mode-Specific, Short)
# ============================================================================

def _get_system_prompt(mode: str, has_relevant_pending: bool) -> str:
    """
    Return mode-specific system prompt based on whether relevant pending items exist.
    """
    
    if mode == "morning_brief":
        if has_relevant_pending:
            return """Mode: Morning brief with pending questions.

Your goals:
- Give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.
- You may ask at most two focused follow-up questions, but only about the tasks and attributes listed in the pending items.

Rules:
- Start with the brief (1–3 short bullet points or short paragraphs).
- Only then, if it clearly fits, embed at most two questions at the end.
- Do not ask about anything that is not in the pending list.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["brief text", "optional question 1", "optional question 2"],
  "updates": []
}"""
        else:
            return """Mode: Morning brief, no pending questions.

Your only goal is to give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.

Rules:
- Do not ask the user any questions.
- Be concise (1–3 short bullet points or short paragraphs).

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["brief text"],
  "updates": []
}"""
    
    elif mode == "user_question":
        if has_relevant_pending:
            return """Mode: Answer user question with a related follow-up.

Your goals:
- First, answer the user's question as clearly and directly as you can using the provided context.
- Then you may ask one short follow-up question, but only about one of the pending items shown in the context that is directly related to the user's question.

Rules:
- Always answer their question before asking anything back.
- Ask at most one follow-up question.
- The follow-up must be obviously related to their question and to one of the pending items.
- If none of the pending items fit naturally, skip the follow-up.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["answer", "optional follow-up question"],
  "updates": []
}"""
        else:
            return """Mode: Answer user question, no pending follow-up.

Your goal is to answer the user's question as clearly and directly as you can using the provided context.

Rules:
- Do not ask the user any follow-up questions.
- If you don't know something, say so briefly.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["answer"],
  "updates": []
}"""
    
    elif mode == "collect_data":
        if has_relevant_pending:
            return """Mode: Collect perception data for pending items.

Your goal is to update the missing or stale attributes for the tasks and attributes listed in the pending items in the context.

Rules:
- Ask the minimal number of questions needed to cover the pending items.
- Group related attributes for the same task into one question when possible (e.g. "For Apollo, what is the current status and main goal?").
- Stay strictly within the tasks and attributes listed in the pending items.
- Ask at most three questions in this turn.
- Keep each question short and clear.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["question 1", "question 2", "question 3"],
  "updates": []
}"""
        else:
            return """Mode: Collect perception data, but no pending items.

There are no pending items to update for this user right now.

Rules:
- Do not ask the user any questions.
- Optionally, you may say briefly that everything looks up to date, then stop.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["Everything looks up to date!"],
  "updates": []
}"""
    
    return ""


def _build_context_string(
    mode: str,
    user_snapshot: dict,
    task_snapshot: List[dict],
    pending_relevant: List[PendingQuestion]
) -> str:
    """
    Build context string based on mode.
    
    Most modes: user name, employees, manager, user tasks, aligned tasks
    collect_data: user name, only tasks/users related to pending items
    """
    
    if mode == "collect_data":
        # Simplified context: just the pending items
        pending_summary = []
        for p in pending_relevant:
            pending_summary.append({
                "task_title": f"Task ID {p.task_id}" if p.task_id else "User-level",
                "attribute": p.attribute_label,
                "reason": p.reason
            })
        
        return f"""USER: {user_snapshot.get('name', 'Unknown')}

PENDING ITEMS TO COLLECT:
{json.dumps(pending_summary, indent=2)}"""
    
    else:
        # For morning_brief and user_question: full context
        context = f"""USER: {user_snapshot.get('name', 'Unknown')}
MANAGER: {user_snapshot.get('manager', 'None')}
EMPLOYEES: {', '.join(user_snapshot.get('employees', [])) if user_snapshot.get('employees') else 'None'}

TASKS (showing {len(task_snapshot)}):
{json.dumps(task_snapshot, indent=2)}"""
        
        if pending_relevant:
            pending_summary = [
                {
                    "task_title": f"Task ID {p.task_id}" if p.task_id else "User-level",
                    "attribute": p.attribute_label,
                    "reason": p.reason
                }
                for p in pending_relevant
            ]
            context += f"\n\nRELEVANT PENDING ITEMS:\n{json.dumps(pending_summary, indent=2)}"
        
        return context


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
    1. Classifies the mode
    2. Gets pending questions and filters by relevance
    3. Builds mode-specific context
    4. Calls OpenAI with mode-specific prompt
    5. Parses the response into messages and structured updates
    """
    logger.info(f"Generating Robin reply for user {user_id}, message: '{user_message[:50]}...'")
    
    try:
        # Step 1: Classify mode
        mode = _classify_mode(user_message)
        logger.info(f"Classified mode: {mode}")
        
        # Step 2: Get pending questions
        # Note: get_pending_questions_for_user is async, but db is sync Session
        # We need to handle this by making our function work with sync session
        # For now, let's keep it simple and call it directly (will need AsyncSession wrapper)
        # Workaround: Use sync query in a helper
        pending = _get_pending_sync(db, user_id)
        logger.info(f"Found {len(pending)} pending questions")
        
        # Step 3: Build context
        user_snapshot = _get_user_snapshot(db, user_id)
        task_snapshot = _get_task_snapshot(db, user_id)
        
        # Step 4: Filter pending by mode
        pending_relevant = _filter_pending_by_mode(pending, mode, task_snapshot)
        has_relevant_pending = len(pending_relevant) > 0
        logger.info(f"Filtered to {len(pending_relevant)} relevant pending items")
        
        # Step 5: Build mode-specific context and prompt
        system_prompt = _get_system_prompt(mode, has_relevant_pending)
        context_str = _build_context_string(mode, user_snapshot, task_snapshot, pending_relevant)
        
        # Build messages for OpenAI
        openai_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"Context:\n{context_str}"},
            {"role": "user", "content": user_message}
        ]
        
        # Store debug info
        full_prompt_debug = {
            "model": "gpt-5-mini",
            "mode": mode,
            "has_relevant_pending": has_relevant_pending,
            "pending_count": len(pending_relevant),
            "messages": openai_messages
        }
        
        # Step 6: Call OpenAI
        logger.info(f"Calling OpenAI GPT-5 mini (mode={mode}, has_relevant_pending={has_relevant_pending})...")
        response = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=openai_messages,
            max_completion_tokens=2000
        )
        
        assistant_reply = response.choices[0].message.content
        logger.info(f"OpenAI response received: {assistant_reply[:100]}...")
        
        # Step 7: Parse JSON response
        try:
            # Extract JSON from response (might be wrapped in markdown)
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
            
            # Add debug info to first message
            if messages:
                if messages[0].metadata is None:
                    messages[0].metadata = {}
                messages[0].metadata["debug_prompt"] = full_prompt_debug
            
            return RobinReply(messages=messages, updates=updates)
            
        except json.JSONDecodeError as e:
            # Fallback: treat response as single message
            logger.warning(f"Failed to parse JSON: {e}")
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
        
        return RobinReply(
            messages=[RobinMessage(
                text="Sorry, I encountered an error. Please try again.",
                metadata={"error": str(e)}
            )],
            updates=[]
        )


def _get_pending_sync(db: Session, user_id: UUID) -> List[PendingQuestion]:
    """
    Sync wrapper to get pending questions.
    This replicates the logic from questions.py but uses sync Session.
    """
    from datetime import datetime, timedelta
    
    pending: List[PendingQuestion] = []
    staleness_days = 7
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    # Get aligned users
    alignments = db.query(AlignmentEdge).filter(
        AlignmentEdge.source_user_id == user_id
    ).all()
    aligned_user_ids = [a.target_user_id for a in alignments]
    
    # All users to consider
    all_target_user_ids = [user_id] + aligned_user_ids
    
    # Get all tasks
    tasks = db.query(Task).filter(
        Task.owner_user_id.in_(all_target_user_ids),
        Task.is_active == True
    ).all()
    
    # Get all task attributes
    attributes = db.query(AttributeDefinition).filter(
        AttributeDefinition.entity_type == EntityType.TASK
    ).all()
    
    # Check each (task, attribute) pair
    for task in tasks:
        for attr in attributes:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == task.owner_user_id,
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == attr.id,
                AttributeAnswer.refused == False
            ).order_by(AttributeAnswer.updated_at.desc()).first()
            
            reason = None
            if answer is None:
                reason = "missing"
            elif answer.updated_at < datetime.utcnow() - timedelta(days=staleness_days):
                reason = "stale"
            
            # Check misalignment (simplified: check if similarity score < 0.6 exists)
            if answer is not None:
                from app.models import SimilarityScore
                sim = db.query(SimilarityScore).filter(
                    (SimilarityScore.answer_a_id == answer.id) | 
                    (SimilarityScore.answer_b_id == answer.id),
                    SimilarityScore.similarity_score < 0.6
                ).first()
                if sim:
                    reason = "misaligned"
            
            if reason:
                priority = _compute_priority_sync(task, attr, reason)
                
                pending.append(PendingQuestion(
                    id=f"{task.id}_{attr.name}_{task.owner_user_id}",
                    target_user_id=task.owner_user_id,
                    task_id=task.id,
                    attribute_name=attr.name,
                    attribute_label=attr.label,
                    reason=reason,
                    priority=priority
                ))
    
    # Sort by priority
    pending.sort(key=lambda x: x.priority)
    
    return pending


def _compute_priority_sync(task: Task, attr: AttributeDefinition, reason: str) -> int:
    """Compute priority for pending question"""
    base = 100
    
    if reason == "missing":
        base -= 30
    elif reason == "misaligned":
        base -= 20
    elif reason == "stale":
        base -= 10
    
    important_attrs = ["priority", "status", "main_goal"]
    if attr.name in important_attrs:
        base -= 15
    
    return max(0, base)
