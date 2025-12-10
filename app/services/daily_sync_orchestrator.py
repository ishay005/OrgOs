"""
Daily Sync Orchestrator - Structured conversation flow with phases
"""
import logging
import json
from typing import List, Dict
from uuid import UUID
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import AsyncOpenAI

from app.models import (
    User, Task, AttributeAnswer, AttributeDefinition,
    DailySyncSession, DailySyncPhase, ChatMessage, PromptTemplate
)
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)


# ============================================================================
# Data Models for Daily Sync Inputs
# ============================================================================

class InsightQuestion(BaseModel):
    """A question Cortex wants Robin to ask the user"""
    id: str  # UUID as string
    text: str  # The actual question
    value: int  # Priority/importance (higher = more valuable)
    reason: str  # Internal reason (never shown to user)
    task_id: UUID | None = None
    attribute_name: str | None = None


class DailyUserContext(BaseModel):
    """User preferences and info"""
    name: str
    timezone: str
    notification_time: str
    manager_name: str | None
    employees: List[str]


class DailySituationContext(BaseModel):
    """Current work situation"""
    tasks_in_progress: List[Dict]
    tasks_blocked: List[Dict]
    upcoming_deadlines: List[Dict]
    risks: List[Dict]
    misalignments: List[Dict]
    important_items: List[str]


class RobinMessage(BaseModel):
    """A message from Robin"""
    text: str
    metadata: Dict | None = None


class StructuredUpdate(BaseModel):
    """An update to be applied to the database"""
    task_id: UUID | None
    target_user_id: UUID
    attribute_name: str
    value: str


class DailySyncTurnResult(BaseModel):
    """Result of processing one turn in Daily Sync"""
    messages: List[RobinMessage]
    updates: List[StructuredUpdate]
    new_phase: DailySyncPhase
    session: Dict  # Updated session data


# ============================================================================
# Session Management
# ============================================================================

def get_active_daily_session(db: Session, user_id: UUID) -> DailySyncSession | None:
    """Get active Daily Sync session for user"""
    return db.query(DailySyncSession).filter(
        DailySyncSession.user_id == user_id,
        DailySyncSession.is_active == True
    ).first()


def create_daily_session(
    db: Session,
    user_id: UUID,
    thread_id: UUID,
    insight_questions: List[InsightQuestion]
) -> DailySyncSession:
    """Create a new Daily Sync session"""
    # Convert insight questions to JSON-serializable dicts
    questions_json = []
    for q in insight_questions:
        q_dict = q.dict()
        # Convert UUID to string for JSON serialization
        if q_dict.get('task_id'):
            q_dict['task_id'] = str(q_dict['task_id'])
        questions_json.append(q_dict)
    
    session = DailySyncSession(
        user_id=user_id,
        thread_id=thread_id,
        phase=DailySyncPhase.OPENING_BRIEF,  # Start with opening brief
        insight_questions=questions_json,
        asked_question_ids=[],
        answered_question_ids=[],
        is_active=True
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(f"✅ Created Daily Sync session {session.id} for user {user_id}")
    return session


def update_daily_session(db: Session, session: DailySyncSession) -> None:
    """Update session in database"""
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)


def end_daily_session(db: Session, session: DailySyncSession) -> None:
    """End the Daily Sync session"""
    session.is_active = False
    session.phase = DailySyncPhase.DONE
    session.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"✅ Ended Daily Sync session {session.id}")


# ============================================================================
# Context Builders for Daily Sync
# ============================================================================

def get_daily_user_context(db: Session, user_id: UUID) -> DailyUserContext:
    """Build user context for Daily Sync"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return DailyUserContext(
            name="Unknown",
            timezone="UTC",
            notification_time="10:00",
            manager_name=None,
            employees=[]
        )
    
    manager = db.query(User).filter(User.id == user.manager_id).first() if user.manager_id else None
    employees = db.query(User).filter(User.manager_id == user_id).all()
    
    return DailyUserContext(
        name=user.name,
        timezone=user.timezone,
        notification_time=str(user.notification_time),
        manager_name=manager.name if manager else None,
        employees=[e.name for e in employees]
    )


def get_daily_situation_context(db: Session, user_id: UUID) -> DailySituationContext:
    """Build situation context for Daily Sync"""
    # Get user's tasks
    tasks = db.query(Task).filter(
        Task.owner_user_id == user_id,
        Task.is_active == True
    ).all()
    
    tasks_in_progress = []
    tasks_blocked = []
    all_tasks_summary = []
    
    status_attr = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == "status",
        AttributeDefinition.entity_type == "task"
    ).first()
    
    priority_attr = db.query(AttributeDefinition).filter(
        AttributeDefinition.name == "priority",
        AttributeDefinition.entity_type == "task"
    ).first()
    
    for task in tasks:
        task_info = {"title": task.title, "status": "Unknown", "priority": "Unknown"}
        
        # Get status
        if status_attr:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == status_attr.id,
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.refused == False
            ).order_by(AttributeAnswer.updated_at.desc()).first()
            
            if answer:
                task_info["status"] = answer.value
                if answer.value == "In progress":
                    tasks_in_progress.append({"title": task.title})
                elif answer.value == "Blocked":
                    tasks_blocked.append({"title": task.title})
        
        # Get priority
        if priority_attr:
            answer = db.query(AttributeAnswer).filter(
                AttributeAnswer.task_id == task.id,
                AttributeAnswer.attribute_id == priority_attr.id,
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.refused == False
            ).order_by(AttributeAnswer.updated_at.desc()).first()
            
            if answer:
                task_info["priority"] = answer.value
        
        all_tasks_summary.append(task_info)
    
    # Build important items list (high priority tasks)
    important_items = [
        f"{t['title']} ({t['status']}, Priority: {t['priority']})"
        for t in all_tasks_summary
        if t['priority'] in ['Critical', 'High']
    ]
    
    return DailySituationContext(
        tasks_in_progress=tasks_in_progress,
        tasks_blocked=tasks_blocked,
        upcoming_deadlines=[],
        risks=[],
        misalignments=[],
        important_items=important_items or [f"{len(tasks)} total tasks"]
    )


def get_insight_questions_for_daily_sync(db: Session, user_id: UUID) -> List[InsightQuestion]:
    """
    Get insight questions for the Daily Sync.
    These are high-value questions Cortex wants to ask.
    
    For now, we'll generate them based on pending questions.
    In the future, this could be a separate Cortex service.
    """
    from app.services.robin_orchestrator import _get_pending_sync
    
    pending = _get_pending_sync(db, user_id)
    
    insight_questions = []
    for i, p in enumerate(pending[:5]):  # Top 5 pending items
        # Get task title if applicable
        task_title = ""
        if p.task_id:
            task = db.query(Task).filter(Task.id == p.task_id).first()
            if task:
                task_title = task.title
        
        # Build question text
        question_text = f"What's the current {p.attribute_label.lower()} for {task_title}?" if task_title else f"What's your {p.attribute_label.lower()}?"
        
        # Assign value based on priority
        value = 100 - (i * 10)  # Higher priority = higher value
        
        insight_questions.append(InsightQuestion(
            id=f"{p.task_id}_{p.attribute_name}" if p.task_id else f"user_{p.attribute_name}",
            text=question_text,
            value=value,
            reason=p.reason,
            task_id=p.task_id,  # Will be converted to string when saving session
            attribute_name=p.attribute_name
        ))
    
    return insight_questions


# ============================================================================
# LLM Integration for Daily Sync
# ============================================================================

def _get_daily_sync_prompt(db: Session, phase: DailySyncPhase, has_pending: bool = False) -> tuple[str, dict]:
    """Load prompt and context config for a Daily Sync phase from database"""
    # Map phase to mode name
    mode_map = {
        DailySyncPhase.OPENING_BRIEF: "daily_opening_brief",
        DailySyncPhase.QUESTIONS: "daily_questions",  # Combined user + robin questions
        DailySyncPhase.SUMMARY: "daily_summary"
    }
    
    mode = mode_map.get(phase, "daily_morning_brief")
    
    # Load from database
    prompt = db.query(PromptTemplate).filter(
        PromptTemplate.mode == mode,
        PromptTemplate.has_pending == has_pending,
        PromptTemplate.is_active == True
    ).order_by(PromptTemplate.version.desc()).first()
    
    if prompt:
        logger.info(f"📝 Loaded Daily Sync prompt: {mode} v{prompt.version}")
        return prompt.prompt_text, prompt.context_config or {}
    else:
        logger.warning(f"⚠️  No prompt found for {mode}, using fallback")
        return f"Phase: {phase.value}. Respond appropriately.", {}


def _build_daily_sync_context(
    db: Session,
    user_ctx: DailyUserContext,
    situation_ctx: DailySituationContext,
    session: DailySyncSession,
    phase: DailySyncPhase,
    recent_messages: List[Dict]
) -> str:
    """Build context string for LLM based on phase"""
    sections = []
    
    # User info (always included)
    sections.append(f"=== USER INFO ===\nName: {user_ctx.name}")
    if user_ctx.manager_name:
        sections.append(f"Manager: {user_ctx.manager_name}")
    if user_ctx.employees:
        sections.append(f"Employees: {', '.join(user_ctx.employees)}")
    
    # Situation context (for morning brief and questions)
    if phase in [DailySyncPhase.OPENING_BRIEF, DailySyncPhase.QUESTIONS]:
        sections.append("\n=== SITUATION ===")
        if situation_ctx.tasks_in_progress:
            sections.append(f"In Progress: {', '.join([t['title'] for t in situation_ctx.tasks_in_progress])}")
        if situation_ctx.tasks_blocked:
            sections.append(f"Blocked: {', '.join([t['title'] for t in situation_ctx.tasks_blocked])}")
        if situation_ctx.important_items:
            sections.append(f"Important: {', '.join(situation_ctx.important_items)}")
        
        # If no specific situation data, at least mention there are tasks
        if not situation_ctx.tasks_in_progress and not situation_ctx.tasks_blocked and not situation_ctx.important_items:
            sections.append("(No active tasks in progress or blocked at this time)")
    
    # Insight questions (for questions phase when Robin asks)
    if phase == DailySyncPhase.QUESTIONS:
        sections.append("\n=== INSIGHT QUESTIONS ===")
        # Get unasked questions
        asked_ids = set(session.asked_question_ids)
        unasked = [q for q in session.insight_questions if q.get('id') not in asked_ids]
        
        if unasked:
            for q in unasked[:3]:  # Top 3 unasked
                sections.append(f"- {q.get('text')} (value: {q.get('value')})")
        else:
            sections.append("(All questions asked)")
    
    # Recent conversation history
    if recent_messages:
        sections.append("\n=== RECENT CONVERSATION ===")
        for msg in recent_messages[-3:]:  # Last 3 messages
            sender = msg.get('sender', 'unknown')
            text = msg.get('text', '')
            sections.append(f"{sender}: {text}")
    
    return "\n".join(sections)


def _get_recent_daily_sync_messages(db: Session, thread_id: UUID, limit: int = 5) -> List[Dict]:
    """Get recent messages from this Daily Sync session"""
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    return [
        {
            "sender": msg.sender,
            "text": msg.text,
            "created_at": msg.created_at.isoformat()
        }
        for msg in reversed(messages)
    ]


async def _call_llm_for_daily_sync(
    system_prompt: str,
    context: str,
    user_message: str | None
) -> Dict:
    """Call OpenAI LLM for Daily Sync response"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"CONTEXT:\n{context}"}
    ]
    
    if user_message:
        messages.append({"role": "user", "content": user_message})
    else:
        # Initial greeting or brief
        messages.append({"role": "user", "content": "BEGIN"})
    
    try:
        logger.info(f"🤖 Calling LLM with {len(messages)} messages")
        logger.info(f"🤖 Model: gpt-5-mini, max_tokens: 4000")
        
        response = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            max_completion_tokens=2000  # Higher limit for reasoning models
        )
        
        logger.info(f"🤖 API Response object: {response}")
        logger.info(f"🤖 Response choices: {response.choices}")
        logger.info(f"🤖 First choice message: {response.choices[0].message}")
        
        content = response.choices[0].message.content
        
        # Check if content is None or empty
        if content is None or content == "":
            logger.error(f"❌ LLM returned empty/None content! Response: {response}")
            return {
                "display_messages": ["Sorry, I didn't get a response from the AI. Please try again."],
                "updates": []
            }
        
        logger.info(f"✅ LLM response (full): {content}")
        
        # Parse JSON response
        try:
            parsed = json.loads(content)
            logger.info(f"✅ Parsed response: {parsed}")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}, content: {content}")
            # If not JSON, wrap as message
            return {
                "display_messages": [content],
                "updates": []
            }
    
    except Exception as e:
        logger.error(f"❌ LLM error: {e}")
        return {
            "display_messages": [f"Sorry, I encountered an error: {str(e)}"],
            "updates": []
        }


def _determine_next_phase(
    current_phase: DailySyncPhase,
    user_message: str | None,
    session: DailySyncSession,
    llm_response: Dict
) -> DailySyncPhase:
    """
    Determine next phase based on current phase and context.
    
    Simplified flow:
    1. OPENING_BRIEF → QUESTIONS (when user responds)
    2. QUESTIONS → SUMMARY (when conversation seems done)
    3. SUMMARY → DONE
    """
    
    if current_phase == DailySyncPhase.OPENING_BRIEF:
        # Stay in opening brief until user responds
        if user_message:
            return DailySyncPhase.QUESTIONS
        else:
            # Initial brief - stay in this phase
            return DailySyncPhase.OPENING_BRIEF
    
    elif current_phase == DailySyncPhase.QUESTIONS:
        # Check if user wants to wrap up
        if user_message:
            wrap_up_phrases = ['done', 'thanks', 'thats all', 'nothing else', 'no more', 'goodbye']
            if any(phrase in user_message.lower() for phrase in wrap_up_phrases):
                return DailySyncPhase.SUMMARY
        
        # Check if we've asked enough questions
        asked_count = len(session.asked_question_ids)
        total_count = len(session.insight_questions)
        
        if asked_count >= min(total_count, 5):  # Max 5 questions per session
            return DailySyncPhase.SUMMARY
        
        # Stay in questions phase
        return DailySyncPhase.QUESTIONS
    
    elif current_phase == DailySyncPhase.SUMMARY:
        # After summary, we're done
        return DailySyncPhase.DONE
    
    else:
        return current_phase


# ============================================================================
# Daily Sync Orchestrator - Main Function
# ============================================================================

async def handle_daily_sync_turn(
    db: Session,
    session: DailySyncSession,
    user_ctx: DailyUserContext,
    situation_ctx: DailySituationContext,
    user_message: str | None
) -> DailySyncTurnResult:
    """
    Process one turn in the Daily Sync conversation.
    
    Based on current phase and user message, generate Robin's response
    and determine next phase.
    """
    current_phase = session.phase
    logger.info(f"🔄 Daily Sync turn - Phase: {current_phase}, User message: {user_message}")
    
    # Determine which phase's prompt to use
    # If user is responding to opening brief, we should use questions prompt!
    if current_phase == DailySyncPhase.OPENING_BRIEF and user_message:
        # User responded to opening brief -> use questions phase prompt
        prompt_phase = DailySyncPhase.QUESTIONS
        logger.info(f"🔀 User responded to opening brief -> using QUESTIONS prompt")
    else:
        # Use current phase's prompt
        prompt_phase = current_phase
    
    # Determine if we have pending questions (for QUESTIONS phase)
    has_pending = (prompt_phase == DailySyncPhase.QUESTIONS and len(session.insight_questions) > 0)
    
    # Load prompt for the appropriate phase
    system_prompt, context_config = _get_daily_sync_prompt(db, prompt_phase, has_pending)
    
    # Build context
    recent_messages = _get_recent_daily_sync_messages(db, session.thread_id, limit=5)
    context = _build_daily_sync_context(
        db, user_ctx, situation_ctx, session, current_phase, recent_messages
    )
    
    # Call LLM
    llm_response = await _call_llm_for_daily_sync(system_prompt, context, user_message)
    
    # Build debug info (similar to regular Robin orchestrator)
    messages_for_llm = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"CONTEXT:\n{context}"},
        {"role": "user", "content": user_message if user_message else "BEGIN"}
    ]
    
    full_prompt_debug = {
        "model": "gpt-5-mini",
        "mode": f"daily_{prompt_phase.value}",  # Use prompt_phase, not current_phase!
        "messages": messages_for_llm
    }
    
    # Parse display messages - combine into one message with line breaks
    display_texts = llm_response.get("display_messages", [])
    logger.info(f"📝 Display texts from LLM: {display_texts}")
    
    if display_texts:
        # Join all messages with double line breaks for better readability
        combined_text = "\n\n".join(display_texts)
        logger.info(f"📝 Combined text length: {len(combined_text)}, text: {combined_text[:200]}")
        robin_messages = [RobinMessage(
            text=combined_text,
            metadata={
                "phase": prompt_phase.value,  # Use prompt_phase for consistency with debug mode
                "debug_prompt": full_prompt_debug,
                "full_response": llm_response
            }
        )]
    else:
        logger.warning(f"⚠️  No display_messages in LLM response!")
        robin_messages = []
    
    # Parse updates (TODO: apply to database)
    updates = []
    for update_data in llm_response.get("updates", []):
        updates.append(StructuredUpdate(**update_data))
    
    # Update session state for questions phase
    if current_phase == DailySyncPhase.QUESTIONS and not user_message:
        # Mark questions as asked
        asked_ids = set(session.asked_question_ids)
        for q in session.insight_questions[:3]:  # Top 3 unasked
            if q.get('id') not in asked_ids:
                asked_ids.add(q.get('id'))
        session.asked_question_ids = list(asked_ids)
    
    # Determine next phase
    logger.info(f"🔍 Before phase transition - Current: {current_phase}, User message: {'Yes' if user_message else 'No'}")
    next_phase = _determine_next_phase(current_phase, user_message, session, llm_response)
    
    logger.info(f"✅ Phase transition: {current_phase} → {next_phase}")
    logger.info(f"📊 Session will be updated with new phase: {next_phase}")
    
    return DailySyncTurnResult(
        messages=robin_messages,
        updates=updates,
        new_phase=next_phase,
        session={
            "id": str(session.id),
            "phase": next_phase.value,
            "asked_question_ids": session.asked_question_ids,
            "answered_question_ids": session.answered_question_ids
        }
    )

