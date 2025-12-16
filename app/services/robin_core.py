"""
Robin Core - Central call_robin() function using OpenAI Responses API.

This is the single entry point for all Robin interactions.
Uses the Responses API with text.format for structured output and function calling for MCP tools.
"""
import json
import logging
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    User, Task, ChatThread, ChatMessage, DailySyncSession,
    AttributeDefinition, AttributeAnswer, EntityType, MessageDebugData,
    PromptTemplate
)
from app.services.robin_types import (
    RobinReply, StructuredUpdate, ControlSignals, LLMResponseSchema
)
from app.services.cortex_tools import CORTEX_TOOLS, execute_tool

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)

# Model to use - GPT-5 mini
MODEL = "gpt-5-mini"


# =============================================================================
# Response Schema for Structured Output (text.format)
# =============================================================================

# JSON Schema for structured responses via text.format
# Note: In strict mode, ALL properties must be in the required array
RESPONSE_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "robin_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "display_messages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Messages to show to the user"
            },
            "updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": ["string", "null"]},
                        "target_user_id": {"type": "string"},
                        "attribute_name": {"type": "string"},
                        "value": {"type": "string"}
                    },
                    "required": ["task_id", "target_user_id", "attribute_name", "value"],
                    "additionalProperties": False
                },
                "description": "Data updates to apply"
            },
            "control": {
                "type": "object",
                "properties": {
                    "conversation_done": {"type": "boolean"},
                    "next_phase": {"type": ["string", "null"]}
                },
                "required": ["conversation_done", "next_phase"],
                "additionalProperties": False
            }
        },
        "required": ["display_messages", "updates", "control"],
        "additionalProperties": False
    }
}


# Convert CORTEX_TOOLS to Responses API format
def get_responses_api_tools():
    """
    Convert CORTEX_TOOLS from Chat Completions format to Responses API format.
    
    Chat Completions format:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    
    Responses API format:
      {"type": "function", "name": ..., "description": ..., "parameters": ..., "strict": ...}
    """
    tools = []
    for tool in CORTEX_TOOLS:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            tools.append({
                "type": "function",
                "name": func.get("name"),
                "description": func.get("description"),
                "parameters": func.get("parameters"),
                "strict": False  # Allow flexible parameters
            })
    return tools


# =============================================================================
# Get Prompt from Database
# =============================================================================

def get_prompt_from_db(db: Session, mode: str, submode: Optional[str] = None) -> str:
    """
    Fetch the active prompt from the database for the given mode.
    
    Mode mapping:
    - "morning_brief" -> mode="morning_brief", has_pending=False
    - "daily" + "opening" -> mode="daily_opening", has_pending=False
    - "daily" + "questions" -> mode="daily_questions", has_pending=False
    - "daily" + "summary" -> mode="daily_summary", has_pending=False
    - "questions" -> mode="questions", has_pending=False
    """
    # Build the mode key
    if mode == "daily" and submode:
        db_mode = f"daily_{submode}"
    else:
        db_mode = mode
    
    # Get the active prompt for this mode
    prompt = db.query(PromptTemplate).filter(
        PromptTemplate.mode == db_mode,
        PromptTemplate.is_active == True
    ).order_by(PromptTemplate.version.desc()).first()
    
    if prompt:
        logger.info(f"📋 Using prompt from DB: mode={db_mode}, version={prompt.version}")
        return prompt.prompt_text
    
    # Fallback to hardcoded default if not in DB
    logger.warning(f"⚠️ No prompt found in DB for mode={db_mode}, using fallback")
    return _get_fallback_prompt(mode, submode)


def _get_fallback_prompt(mode: str, submode: Optional[str] = None) -> str:
    """Fallback prompts if DB is empty."""
    from app.services.robin_prompts import get_prompt
    return get_prompt(mode, submode)


# =============================================================================
# Main call_robin() Function - Using Responses API
# =============================================================================

async def call_robin(
    *,
    db: Session,
    user_id: UUID,
    mode: Literal["daily", "morning_brief", "questions"],
    submode: Optional[Literal["opening", "questions", "summary"]] = None,
    previous_response_id: Optional[str] = None,
    user_message: Optional[str] = None,
    thread_id: Optional[UUID] = None,
    daily_session: Optional[DailySyncSession] = None
) -> RobinReply:
    """
    Central function for all Robin interactions.
    
    Uses OpenAI Responses API with:
    - text.format for structured output (JSON schema enforcement)
    - Function calling for MCP tools
    - store=True + previous_response_id for conversation state
    
    Args:
        db: Database session
        user_id: Current user's UUID
        mode: "daily", "morning_brief", or "questions"
        submode: For daily mode: "opening", "questions", or "summary"
        previous_response_id: OpenAI response ID from previous call (for multi-turn)
        user_message: The user's message or trigger (e.g., "__start_daily__")
        thread_id: Chat thread ID for storing messages
        daily_session: Daily sync session if in daily mode
    
    Returns:
        RobinReply with display_messages, updates, control signals, and response_id
    """
    logger.info(f"🤖 call_robin: mode={mode}, submode={submode}, user_message={user_message[:50] if user_message else None}")
    
    # Get the appropriate system prompt from DB
    system_prompt = get_prompt_from_db(db, mode, submode)
    
    # Build input messages for the API call
    input_messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Note: When using previous_response_id, OpenAI maintains conversation history
    # We only need to add history manually if there's no previous_response_id (first message)
    if not previous_response_id and thread_id and mode in ["daily", "questions"]:
        # Fallback: load history from DB for first message in a session
        history = _get_conversation_history(db, thread_id, limit=5)
        input_messages.extend(history)
    
    # Add the user message
    if user_message:
        # Filter out synthetic triggers for display
        display_message = user_message
        if user_message.startswith("__"):
            display_message = ""  # Don't show synthetic triggers
        
        if display_message:
            input_messages.append({"role": "user", "content": display_message})
        else:
            # For synthetic triggers, add a placeholder
            input_messages.append({"role": "user", "content": "[Starting conversation]"})
    
    # Make the API call with tools using Responses API
    tool_calls_made = []
    max_tool_iterations = 5  # Prevent infinite loops
    
    for iteration in range(max_tool_iterations):
        logger.info(f"🔄 API call iteration {iteration + 1}")
        
        try:
            # Build API params
            api_params = {
                "model": MODEL,
                "input": input_messages,
                "text": {"format": RESPONSE_JSON_SCHEMA},
                "tools": get_responses_api_tools(),
                "tool_choice": "auto",
                "store": True  # Enable OpenAI to store response for conversation threading
            }
            
            # Add previous_response_id for multi-turn conversation state
            if previous_response_id:
                api_params["previous_response_id"] = previous_response_id
                logger.info(f"📎 Using previous_response_id: {previous_response_id[:20]}...")
            
            response = await client.responses.create(**api_params)
        except Exception as e:
            logger.error(f"❌ OpenAI API error: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return RobinReply(
                display_messages=["I'm sorry, I encountered an error. Please try again."],
                updates=[],
                control=ControlSignals(),
                mode=mode,
                submode=submode
            )
        
        # Process the response output
        output = response.output
        
        # Check if model wants to call tools (function_call type)
        tool_calls = [item for item in output if getattr(item, 'type', None) == "function_call"]
        
        if tool_calls:
            # Add assistant's tool calls to message history first
            for tool_call in tool_calls:
                input_messages.append({
                    "type": "function_call",
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments or "{}"
                })
            
            # Process each tool call and add outputs
            for tool_call in tool_calls:
                tool_name = tool_call.name
                try:
                    tool_args = json.loads(tool_call.arguments) if tool_call.arguments else {}
                except json.JSONDecodeError:
                    tool_args = {}
                
                logger.info(f"🔧 Tool call: {tool_name}({tool_args})")
                
                # Execute the tool
                result = execute_tool(
                    db=db,
                    user_id=user_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    daily_session=daily_session
                )
                
                # Store tool call with result for debug
                tool_calls_made.append({
                    "name": tool_name,
                    "args": tool_args,
                    "result": result
                })
                
                # Add tool output to messages
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(result)
                })
            
            # Continue loop to get final response after tool calls
            continue
        
        # No more tool calls - get the text output (message type)
        message_items = [item for item in output if getattr(item, 'type', None) == "message"]
        
        if not message_items:
            logger.warning("⚠️ No message output from model")
            return RobinReply(
                display_messages=["I couldn't generate a response. Please try again."],
                updates=[],
                control=ControlSignals(),
                mode=mode,
                submode=submode,
                tool_calls_made=tool_calls_made
            )
        
        # Get the structured text content from the message
        message_item = message_items[0]
        raw_content = ""
        if message_item.content:
            for content_part in message_item.content:
                if hasattr(content_part, 'text'):
                    raw_content = content_part.text
                    break
        logger.info(f"📝 Raw response: {raw_content[:200] if raw_content else 'None'}...")
        
        # Parse the JSON response (should be valid due to schema enforcement)
        try:
            parsed = json.loads(raw_content) if raw_content else {}
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            parsed = {
                "display_messages": [raw_content or "I encountered an error processing my response."],
                "updates": [],
                "control": {"conversation_done": False, "next_phase": None}
            }
        
        # Build the RobinReply
        raw_display_messages = parsed.get("display_messages", [])
        if raw_display_messages:
            combined_message = "\n\n".join([m for m in raw_display_messages if m])
            display_messages = [combined_message] if combined_message else []
        elif raw_content:
            display_messages = [raw_content]
        else:
            display_messages = []
        
        updates = []
        for u in parsed.get("updates", []):
            try:
                updates.append(StructuredUpdate(
                    task_id=u.get("task_id"),
                    target_user_id=u.get("target_user_id", ""),
                    attribute_name=u.get("attribute_name", ""),
                    value=u.get("value", "")
                ))
            except Exception as e:
                logger.warning(f"Could not parse update: {u}, error: {e}")
        
        control_data = parsed.get("control", {})
        control = ControlSignals(
            conversation_done=control_data.get("conversation_done", False),
            next_phase=control_data.get("next_phase")
        )
        
        # Get the response ID for conversation threading
        response_id = getattr(response, 'id', None)
        logger.info(f"📌 Response ID: {response_id[:20] if response_id else 'None'}...")
        
        # Build comprehensive debug data
        debug_info = {
            "mode": mode,
            "submode": submode,
            "tool_calls_made": tool_calls_made,
            "full_prompt": input_messages,
            "raw_response": parsed,
            "raw_content": raw_content,
            "response_id": response_id,
            "previous_response_id": previous_response_id
        }
        
        reply = RobinReply(
            display_messages=display_messages,
            updates=updates,
            control=control,
            mode=mode,
            submode=submode,
            response_id=response_id,  # OpenAI response ID for next call
            tool_calls_made=tool_calls_made,
            raw_response=debug_info
        )
        
        # Apply updates to database
        _apply_updates(db, user_id, updates)
        
        return reply
    
    # Max iterations reached
    logger.warning("⚠️ Max tool iterations reached")
    return RobinReply(
        display_messages=["I got a bit confused. Could you try rephrasing?"],
        updates=[],
        control=ControlSignals(),
        mode=mode,
        submode=submode,
        tool_calls_made=tool_calls_made
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _get_conversation_history(db: Session, thread_id: UUID, limit: int = 10) -> list[dict]:
    """
    Get recent conversation history for multi-turn modes.
    """
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    # Reverse to chronological order
    messages = list(reversed(messages))
    
    history = []
    for msg in messages:
        role = "assistant" if msg.sender == "robin" else "user"
        history.append({
            "role": role,
            "content": msg.text
        })
    
    return history


def _apply_updates(db: Session, user_id: UUID, updates: list[StructuredUpdate]):
    """
    Apply structured updates to the database.
    """
    from app.services.similarity_cache import calculate_and_store_scores_for_answer
    
    for update in updates:
        try:
            # Find task by ID or name
            task = None
            if update.task_id:
                task = db.query(Task).filter(Task.id == update.task_id).first()
            
            # Find target user by name
            target_user = db.query(User).filter(
                User.name.ilike(update.target_user_id)
            ).first()
            
            if not target_user:
                # Try as UUID
                try:
                    target_user = db.query(User).filter(
                        User.id == update.target_user_id
                    ).first()
                except:
                    pass
            
            if not target_user:
                logger.warning(f"Target user not found: {update.target_user_id}")
                continue
            
            # Find attribute
            attribute = db.query(AttributeDefinition).filter(
                AttributeDefinition.name == update.attribute_name,
                AttributeDefinition.entity_type == EntityType.TASK
            ).first()
            
            if not attribute:
                logger.warning(f"Attribute not found: {update.attribute_name}")
                continue
            
            # Create or update answer
            existing = db.query(AttributeAnswer).filter(
                AttributeAnswer.answered_by_user_id == user_id,
                AttributeAnswer.target_user_id == target_user.id,
                AttributeAnswer.task_id == (task.id if task else None),
                AttributeAnswer.attribute_id == attribute.id
            ).first()
            
            if existing:
                existing.value = update.value
                existing.refused = False
                db.commit()
                answer_id = existing.id
            else:
                new_answer = AttributeAnswer(
                    answered_by_user_id=user_id,
                    target_user_id=target_user.id,
                    task_id=task.id if task else None,
                    attribute_id=attribute.id,
                    value=update.value,
                    refused=False
                )
                db.add(new_answer)
                db.commit()
                db.refresh(new_answer)
                answer_id = new_answer.id
            
            logger.info(f"✅ Applied update: {update.attribute_name} = {update.value}")
            
            # Calculate similarity (async function, need to run in sync context)
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    calculate_and_store_scores_for_answer(answer_id, db)
                )
            except Exception as e:
                logger.warning(f"Could not calculate similarity: {e}")
                
        except Exception as e:
            logger.error(f"❌ Error applying update: {e}")


def _save_debug_data(db: Session, thread_id: UUID, messages: list, response: dict):
    """
    Save debug data for the last assistant message.
    """
    last_msg = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id,
        ChatMessage.sender == "robin"
    ).order_by(ChatMessage.created_at.desc()).first()
    
    if last_msg:
        existing = db.query(MessageDebugData).filter(
            MessageDebugData.message_id == last_msg.id
        ).first()
        
        if not existing:
            debug = MessageDebugData(
                message_id=last_msg.id,
                full_prompt=messages,
                full_response=response
            )
            db.add(debug)
            db.commit()


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_morning_brief(db: Session, user_id: UUID, thread_id: Optional[UUID] = None) -> RobinReply:
    """
    Get a morning brief (stateless, one-shot).
    """
    return await call_robin(
        db=db,
        user_id=user_id,
        mode="morning_brief",
        user_message="__morning_brief__",
        thread_id=thread_id
    )


async def start_daily_sync(
    db: Session, 
    user_id: UUID, 
    thread_id: UUID,
    daily_session: DailySyncSession
) -> RobinReply:
    """
    Start a daily sync session (opening phase).
    No previous_response_id since this is the first message.
    """
    return await call_robin(
        db=db,
        user_id=user_id,
        mode="daily",
        submode="opening",
        previous_response_id=None,  # First message - no previous response
        user_message="__start_daily__",
        thread_id=thread_id,
        daily_session=daily_session
    )


async def continue_daily_sync(
    db: Session,
    user_id: UUID,
    thread_id: UUID,
    daily_session: DailySyncSession,
    user_message: str
) -> RobinReply:
    """
    Continue a daily sync conversation.
    Uses the session's last_response_id for conversation threading.
    """
    phase = daily_session.phase
    if hasattr(phase, 'value'):
        phase = phase.value
    
    submode_map = {
        "opening_brief": "opening",
        "questions": "questions",
        "summary": "summary"
    }
    submode = submode_map.get(phase, "questions")
    
    return await call_robin(
        db=db,
        user_id=user_id,
        mode="daily",
        submode=submode,
        previous_response_id=daily_session.last_response_id,  # Chain to previous response
        user_message=user_message,
        thread_id=thread_id,
        daily_session=daily_session
    )


async def send_questions_message(
    db: Session,
    user_id: UUID,
    thread_id: UUID,
    user_message: str,
    previous_response_id: Optional[str] = None
) -> RobinReply:
    """
    Send a message in Questions mode.
    Uses previous_response_id for conversation threading.
    """
    return await call_robin(
        db=db,
        user_id=user_id,
        mode="questions",
        user_message=user_message,
        previous_response_id=previous_response_id,
        thread_id=thread_id
    )
