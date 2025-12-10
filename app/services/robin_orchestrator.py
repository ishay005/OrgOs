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

def _get_user_snapshot(db: Session, user_id: UUID, context_config: dict = None) -> dict:
    """Get user info based on context_config filters"""
    if context_config is None:
        context_config = {}
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {}
    
    snapshot = {
        "name": user.name,
        "manager": None,
        "employees": [],
        "aligned_users": [],
        "all_users": []
    }
    
    # Manager is always included (per requirement)
    if user.manager_id:
        manager = db.query(User).filter(User.id == user.manager_id).first()
        snapshot["manager"] = manager.name if manager else None
    
    # Employees list (optional)
    if context_config.get('include_employees', True):
        employees = db.query(User).filter(User.manager_id == user_id).all()
        snapshot["employees"] = [e.name for e in employees] if employees else []
    
    # Aligned users list (optional)
    if context_config.get('include_aligned_users', False):
        alignments = db.query(AlignmentEdge).filter(
            AlignmentEdge.source_user_id == user_id
        ).all()
        aligned_ids = [a.target_user_id for a in alignments]
        if aligned_ids:
            aligned_users = db.query(User).filter(User.id.in_(aligned_ids)).all()
            snapshot["aligned_users"] = [u.name for u in aligned_users]
    
    # All org users (optional)
    if context_config.get('include_all_users', False):
        all_users = db.query(User).all()
        snapshot["all_users"] = [u.name for u in all_users if u.id != user_id]
    
    return snapshot


def _get_task_snapshot(db: Session, user_id: UUID, context_config: dict = None) -> List[dict]:
    """Get tasks based on context_config filters"""
    if context_config is None:
        context_config = {}
    
    # Get user info
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    
    all_tasks = []
    
    # 1. Personal Tasks (owned by user)
    if context_config.get('include_personal_tasks', True):
        my_tasks = db.query(Task).filter(
            Task.owner_user_id == user_id,
            Task.is_active == True
        ).all()
        all_tasks.extend(my_tasks)
    
    # 2. Manager's Tasks
    if context_config.get('include_manager_tasks', False) and user.manager_id:
        manager_tasks = db.query(Task).filter(
            Task.owner_user_id == user.manager_id,
            Task.is_active == True
        ).all()
        all_tasks.extend(manager_tasks)
    
    # 3. Employee Tasks
    if context_config.get('include_employee_tasks', False):
        employee_ids = [emp.id for emp in user.employees]
        if employee_ids:
            employee_tasks = db.query(Task).filter(
                Task.owner_user_id.in_(employee_ids),
                Task.is_active == True
            ).all()
            all_tasks.extend(employee_tasks)
    
    # 4. Aligned Users' Tasks
    if context_config.get('include_aligned_tasks', False):
        alignments = db.query(AlignmentEdge).filter(
            AlignmentEdge.source_user_id == user_id
        ).all()
        aligned_user_ids = [a.target_user_id for a in alignments]
        
        if aligned_user_ids:
            aligned_tasks = db.query(Task).filter(
                Task.owner_user_id.in_(aligned_user_ids),
                Task.is_active == True
            ).all()
            all_tasks.extend(aligned_tasks)
    
    # 5. All Org Tasks
    if context_config.get('include_all_org_tasks', False):
        all_org_tasks = db.query(Task).filter(
            Task.is_active == True
        ).all()
        all_tasks = all_org_tasks  # Override with all tasks
    
    # Remove duplicates (keep unique by task.id)
    seen_ids = set()
    unique_tasks = []
    for task in all_tasks:
        if task.id not in seen_ids:
            seen_ids.add(task.id)
            unique_tasks.append(task)
    
    # Build task summaries
    task_summaries = []
    for task in unique_tasks[:20]:  # Limit to 20 tasks
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

def _get_system_prompt(mode: str, has_relevant_pending: bool, db: Session) -> tuple[str, dict]:
    """
    Return mode-specific system prompt and context config from database.
    Falls back to hardcoded prompts if database lookup fails.
    
    Returns: (prompt_text, context_config)
    """
    # Try to load from database first
    try:
        from app.models import PromptTemplate
        prompt = db.query(PromptTemplate).filter(
            PromptTemplate.mode == mode,
            PromptTemplate.has_pending == has_relevant_pending,
            PromptTemplate.is_active == True
        ).order_by(PromptTemplate.version.desc()).first()
        
        if prompt:
            logger.info(f"📝 Loaded prompt from DB: mode={mode}, has_pending={has_relevant_pending}, v{prompt.version}")
            context_config = prompt.context_config if prompt.context_config else {}
            return prompt.prompt_text, context_config
        else:
            logger.warning(f"⚠️  No DB prompt found for mode={mode}, has_pending={has_relevant_pending}, using fallback")
    except Exception as e:
        logger.warning(f"⚠️  Error loading prompt from DB: {e}, using fallback")
    
    # Default context config for fallback prompts
    default_config = {
        "history_size": 3 if mode == "user_question" else 2,
        "include_personal_tasks": True,
        "include_manager_tasks": False,
        "include_employee_tasks": True,
        "include_aligned_tasks": False,
        "include_all_org_tasks": False,
        "include_user_info": True,
        "include_manager": True,
        "include_employees": True,
        "include_aligned_users": False,
        "include_all_users": False,
        "include_pending": True
    }
    
    # Fallback to hardcoded prompts
    if mode == "morning_brief":
        if has_relevant_pending:
            return ("""Mode: Morning brief with pending questions.

Your goals:
- Give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.
- You may ask at most two focused follow-up questions, but only about the tasks and attributes listed in the pending items.
- If the user provides information in response, create updates for it.



Rules:
- Start with the brief (1–3 short bullet points or short paragraphs).
- Only then, if it clearly fits, embed at most two questions at the end.
- When user provides task information, create an update in the updates array.

🚫 NEVER ASK ABOUT:
- Attributes NOT in the "RELEVANT PENDING ITEMS" section

✅ ONLY ASK ABOUT attributes actually listed in RELEVANT PENDING ITEMS section with their exact names:
- priority, status, main_goal, perceived_owner, impact_size, resources

Output format - you MUST respond with valid JSON:

When giving brief or asking:
{
  "display_messages": ["brief text", "optional question 1", "optional question 2"],
  "updates": []
}

When receiving answers:
{
  "display_messages": ["Thanks, updated!"],
  "updates": [
    {
      "task_id": "task-uuid",
      "target_user_id": "user-uuid",
      "attribute_name": "status",
      "value": "Done"
    }
  ]
}""", default_config)
        else:
            return ("""Mode: Morning brief, no pending questions.

Your only goal is to give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.

Rules:
- Do not ask the user any questions.
- Be concise (1–3 short bullet points or short paragraphs).

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["brief text"],
  "updates": []
}""", default_config)
    
    elif mode == "user_question":
        if has_relevant_pending:
            return ("""Mode: Answer user question.

⚠️ CRITICAL: If user provides task information (status, priority, goal, etc.) → ADD TO "updates" array!

Goals:
1. Answer their question clearly in MAX 100 words
2. If they gave info → create update
3. Optionally ask 1 related follow-up ONLY about attributes in "RELEVANT PENDING ITEMS"

🚫 NEVER ASK ABOUT:
- Attributes NOT in the "RELEVANT PENDING ITEMS" section

✅ ONLY ASK ABOUT attributes actually listed in RELEVANT PENDING ITEMS section with their exact names:
- priority, status, main_goal, perceived_owner, impact_size, resources

Output format - VALID JSON:
{
  "display_messages": ["your answer"],
  "updates": [{"task_id": "uuid", "target_user_id": "uuid", "attribute_name": "status", "value": "Done"}]
}

EXAMPLE - User provides info:
(Context: Dana answering about her own task "Implement OAuth 2.0 provider")
User: "The OAuth task is done"
You respond:
{
  "display_messages": ["Great! I've marked OAuth as Done."],
  "updates": [
    {
      "task_id": "Implement OAuth 2.0 provider",
      "target_user_id": "Dana Cohen",
      "attribute_name": "status",
      "value": "Done"
    }
  ]
}

Rules:
- Include updates ONLY when user gives information
- Empty updates [] if just answering/asking
- Use TASK NAMES and USER NAMES from context (not UUIDs!)
- task_id: exact task name from TASKS section
- target_user_id: TASK OWNER name (who the question is about), from TASKS section "owner" field
- To CREATE A NEW TASK: use attribute_name="create_task", task_id=null, value=task_title
- attribute_name must be EXACT: "priority", "status", "main_goal", "perceived_owner", "impact_size", "resources"
""", default_config)
        else:
            return ("""Mode: Answer user question, no pending follow-up.

Your goal is to answer the user's question as clearly and directly as you can using the provided context.

Rules:
- Answer in MAX 100 words - be concise!
- Do not ask the user any follow-up questions.
- If you don't know something, say so briefly.
- When user provides task information (status, priority, etc.), create an update in the updates array.
- When user wants to CREATE A NEW TASK, use attribute_name="create_task" and value=task_title.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["answer"],
  "updates": [
    {
      "task_id": null,
      "target_user_id": "current-user-name",
      "attribute_name": "create_task",
      "value": "Task Title Here"
    }
  ]
}

TASK CREATION EXAMPLE:
User: "add a task to develop the OrgOs app"
You respond:
{
  "display_messages": ["Task 'develop the OrgOs app' added."],
  "updates": [
    {
      "task_id": null,
      "target_user_id": "USER_NAME_FROM_CONTEXT",
      "attribute_name": "create_task",
      "value": "develop the OrgOs app"
    }
  ]
}

IMPORTANT: Only include updates when the user has actually provided information. Leave updates empty if just answering questions.""", default_config)
    
    elif mode == "collect_data":
        if has_relevant_pending:
            return ("""Mode: Collect perception data for pending items.

⚠️ CRITICAL RULE: If the user provides ANY information (like "Done", "High", "Blocked", etc.), you MUST include it in the "updates" array. Never leave "updates" empty when user answers!

Your goal: Update missing/stale attributes for tasks in the pending items.

KEEP ALL RESPONSES UNDER 100 WORDS!

How to respond:
1. If ASKING a question → "updates": []
2. If user GIVES information → "updates": [{task_id, target_user_id, attribute_name, value}]

Output format - VALID JSON ONLY:
{
  "display_messages": ["your message here"],
  "updates": [{"task_id": "uuid", "target_user_id": "uuid", "attribute_name": "status", "value": "Done"}]
}

EXAMPLE 1 - Asking:
User: "collect_data"
You respond:
{
  "display_messages": ["What is the status of Q1 Engineering Strategy?"],
  "updates": []
}

EXAMPLE 2 - Receiving answer (CRITICAL!):
(Context shows: Q1 Engineering Strategy owned by Sarah Feldman, Dana is answering)
User: "Done"
You MUST respond:
{
  "display_messages": ["Perfect, marked as Done!"],
  "updates": [
    {
      "task_id": "Q1 Engineering Strategy",
      "target_user_id": "Sarah Feldman",
      "attribute_name": "status",
      "value": "Done"
    }
  ]
}

CRITICAL: 
- task_id = task name from pending items
- target_user_id = THE PERSON THE TASK/ATTRIBUTE IS ABOUT (usually the task owner), NOT the person answering!
- Use names directly from context - you don't need UUIDs!

EXAMPLE 3 - User confirms with "yes":
(Previous context: Dana answering about Sarah Feldman's "Q1 Engineering Strategy")
User: "yes, it's done"  
You MUST respond:
{
  "display_messages": ["Great, updating to Done!"],
  "updates": [
    {
      "task_id": "Q1 Engineering Strategy",
      "target_user_id": "Sarah Feldman",
      "attribute_name": "status",
      "value": "Done"
    }
  ]
}

Rules:
- NEVER say "I've updated" unless you actually include it in "updates"!
- If user says a status/priority/value → ADD TO UPDATES
- task_id: Use TASK NAME from pending items
- target_user_id: Use TASK OWNER name (from pending items "task" field or TASKS section owner)
- attribute_name EXACT options (lowercase): "status", "priority", "main_goal", "perceived_owner", "impact_size", "resources"
- 🚫 NEVER use made-up attributes not in this list!
- IMPORTANT: target_user_id is WHO THE QUESTION IS ABOUT (task owner), NOT who is answering!
- Don't use UUIDs - use actual names!
- ONLY ask about attributes shown in "PENDING ITEMS TO COLLECT" section""", default_config)
        else:
            return ("""Mode: Collect perception data, but no pending items.

There are no pending items to update for this user right now.

Rules:
- Keep response under 100 words.
- Do not ask the user any questions.
- Say briefly that everything looks up to date.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["Everything looks up to date!"],
  "updates": []
}""", default_config)
    
    return ("", default_config)


def _get_recent_chat_messages(db: Session, thread_id: UUID, limit: int) -> List[dict]:
    """Get recent chat messages for context"""
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    # Reverse to get chronological order
    messages = list(reversed(messages))
    
    return [
        {
            "sender": msg.sender,
            "text": msg.text[:200]  # Truncate long messages
        }
        for msg in messages
    ]


def _build_context_string(
    mode: str,
    user_snapshot: dict,
    task_snapshot: List[dict],
    pending_relevant: List[PendingQuestion],
    db: Session,
    thread_id: UUID,
    recent_messages: List[dict],
    context_config: dict = None
) -> str:
    """
    Build context string based on mode and context_config.
    
    context_config controls what to include in the context:
    - Task filters: include_personal_tasks, include_manager_tasks, include_employee_tasks, 
      include_aligned_tasks, include_all_org_tasks
    - User filters: include_employees, include_aligned_users, include_all_users
    - User info and manager are always included
    
    Most modes: user name, employees, manager, user tasks, aligned tasks
    collect_data: user name, only tasks/users related to pending items
    
    Includes recent chat history:
    - user_question mode: last 3 messages
    - other modes: last 2 messages
    """
    # Use defaults if no config provided
    if context_config is None:
        context_config = {}
    
    # Helper function to get task title and owner by ID
    def get_task_info(task_id: UUID) -> tuple:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            owner = db.query(User).filter(User.id == task.owner_user_id).first()
            return (task.title, owner.name if owner else "Unknown")
        return ("Unknown Task", "Unknown")
    
    if mode == "collect_data":
        # Simplified context: just the pending items with task names AND owners
        pending_summary = []
        for p in pending_relevant:
            if p.task_id:
                task_title, task_owner = get_task_info(p.task_id)
            else:
                task_title = "User-level"
                # Get target user name
                target_user = db.query(User).filter(User.id == p.target_user_id).first()
                task_owner = target_user.name if target_user else "Unknown"
            
            pending_summary.append({
                "task": task_title,
                "task_owner": task_owner,
                "attribute": p.attribute_label,
                "reason": p.reason
            })
        
        context = f"""USER: {user_snapshot.get('name', 'Unknown')}

PENDING ITEMS TO COLLECT:
{json.dumps(pending_summary, indent=2)}"""
        
        # Add recent chat history (last 2 messages for collect_data)
        if recent_messages:
            context += f"\n\nRECENT CHAT HISTORY:\n{json.dumps(recent_messages, indent=2)}"
        
        return context
    
    else:
        # For morning_brief and user_question: full context
        context = f"""USER: {user_snapshot.get('name', 'Unknown')}
MANAGER: {user_snapshot.get('manager', 'None')}
EMPLOYEES: {', '.join(user_snapshot.get('employees', [])) if user_snapshot.get('employees') else 'None'}

TASKS (showing {len(task_snapshot)}):
{json.dumps(task_snapshot, indent=2)}"""
        
        if pending_relevant:
            pending_summary = []
            for p in pending_relevant:
                if p.task_id:
                    task_title, task_owner = get_task_info(p.task_id)
                else:
                    task_title = "User-level"
                    target_user = db.query(User).filter(User.id == p.target_user_id).first()
                    task_owner = target_user.name if target_user else "Unknown"
                
                pending_summary.append({
                    "task": task_title,
                    "task_owner": task_owner,
                    "attribute": p.attribute_label,
                    "reason": p.reason
                })
            context += f"\n\nRELEVANT PENDING ITEMS:\n{json.dumps(pending_summary, indent=2)}"
        
        # Add recent chat history (last 3 messages for user_question, last 2 for morning_brief)
        if recent_messages:
            context += f"\n\nRECENT CHAT HISTORY:\n{json.dumps(recent_messages, indent=2)}"
        
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
        
        # Step 2.5: Get prompt config early to use for context building
        # We need to know the context config before building snapshots
        from app.models import PromptTemplate
        prompt_template = db.query(PromptTemplate).filter(
            PromptTemplate.mode == mode,
            PromptTemplate.has_pending == False,  # Use non-pending for initial config
            PromptTemplate.is_active == True
        ).order_by(PromptTemplate.version.desc()).first()
        
        initial_context_config = prompt_template.context_config if prompt_template and prompt_template.context_config else {}
        
        # Step 3: Build context using config
        user_snapshot = _get_user_snapshot(db, user_id, initial_context_config)
        task_snapshot = _get_task_snapshot(db, user_id, initial_context_config)
        
        # Step 4: Filter pending by mode
        pending_relevant = _filter_pending_by_mode(pending, mode, task_snapshot)
        has_relevant_pending = len(pending_relevant) > 0
        logger.info(f"Filtered to {len(pending_relevant)} relevant pending items")
        
        # Step 4.5: Get recent chat messages based on mode
        message_limit = initial_context_config.get('history_size', 3 if mode == "user_question" else 2)
        recent_messages = _get_recent_chat_messages(db, thread_id, message_limit)
        
        # Step 5: Build mode-specific context and prompt (get final config based on has_relevant_pending)
        system_prompt, context_config = _get_system_prompt(mode, has_relevant_pending, db)
        context_str = _build_context_string(mode, user_snapshot, task_snapshot, pending_relevant, db, thread_id, recent_messages, context_config)
        
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
                    # Helper to convert task name/ID to UUID
                    def get_task_uuid(task_ref: str) -> UUID | None:
                        if not task_ref or task_ref == "null":
                            return None
                        try:
                            # Try as UUID first
                            return UUID(task_ref)
                        except:
                            # Try as task name - search user's tasks and aligned users' tasks
                            # Get user's accessible tasks
                            my_tasks = db.query(Task).filter(
                                Task.owner_user_id == user_id,
                                Task.is_active == True
                            ).all()
                            
                            # Get aligned users' tasks
                            alignments = db.query(AlignmentEdge).filter(
                                AlignmentEdge.source_user_id == user_id
                            ).all()
                            aligned_user_ids = [a.target_user_id for a in alignments]
                            
                            aligned_tasks = db.query(Task).filter(
                                Task.owner_user_id.in_(aligned_user_ids),
                                Task.is_active == True
                            ).all() if aligned_user_ids else []
                            
                            all_accessible_tasks = list(my_tasks) + list(aligned_tasks)
                            
                            # Search by exact title match (case-insensitive)
                            for task in all_accessible_tasks:
                                if task.title.lower() == task_ref.lower():
                                    logger.info(f"Resolved task name '{task_ref}' to UUID {task.id}")
                                    return task.id
                            
                            logger.warning(f"Could not resolve task reference: {task_ref} (searched {len(all_accessible_tasks)} accessible tasks)")
                            return None
                    
                    # Helper to convert user name/ID to UUID
                    def get_user_uuid(user_ref: str) -> UUID | None:
                        if not user_ref or user_ref == "null":
                            return None
                        try:
                            # Try as UUID first
                            return UUID(user_ref)
                        except:
                            # Try as user name
                            user = db.query(User).filter(User.name == user_ref).first()
                            if user:
                                logger.info(f"Resolved user name '{user_ref}' to UUID {user.id}")
                                return user.id
                            logger.warning(f"Could not resolve user reference: {user_ref}")
                            return None
                    
                    task_id = get_task_uuid(upd.get("task_id"))
                    target_user_id = get_user_uuid(upd.get("target_user_id"))
                    
                    if target_user_id:  # target_user_id is required
                        updates.append(StructuredUpdate(
                            task_id=task_id,
                            target_user_id=target_user_id,
                            attribute_name=upd["attribute_name"],
                            value=upd["value"]
                        ))
                        logger.info(f"Parsed update: task={task_id}, user={target_user_id}, attr={upd['attribute_name']}, value={upd['value']}")
                    else:
                        logger.warning(f"Skipping update - could not resolve target_user_id: {upd}")
                        
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
