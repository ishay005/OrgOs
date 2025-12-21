"""
Chat API endpoints for Robin assistant

Updated for the new architecture with:
- call_robin() using function calling
- Questions mode with model-driven termination
- Morning Brief as one-shot stateless call
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.database import get_db
from app.auth import get_current_user
from app.models import (
    User, ChatThread, ChatMessage, MessageSender, MessageDebugData,
    Task, AttributeDefinition, AttributeAnswer, QuestionsSession
)
from app.services.robin_core import (
    get_morning_brief, send_questions_message, RobinReply
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SendMessageRequest(BaseModel):
    """Request body for sending a message to Robin"""
    text: str


class ChatMessageResponse(BaseModel):
    """Response model for a single chat message"""
    id: str
    sender: str  # "user", "robin", or "system"
    text: str
    created_at: datetime
    metadata: Optional[dict] = None
    
    class Config:
        from_attributes = True


class SendMessageResponse(BaseModel):
    """Response model for sending a message"""
    messages: list[ChatMessageResponse]
    session_ended: bool = False  # True if Questions mode session was terminated


# ============================================================================
# Helper Functions
# ============================================================================

def _ensure_thread_exists(db: Session, user_id: UUID) -> ChatThread:
    """Ensure a chat thread exists for the user, create if not"""
    thread = db.query(ChatThread).filter(ChatThread.user_id == user_id).first()
    
    if not thread:
        thread = ChatThread(user_id=user_id)
        db.add(thread)
        db.commit()
        db.refresh(thread)
        logger.info(f"Created new chat thread for user {user_id}")
    
    return thread


def _get_or_create_questions_session(db: Session, user_id: UUID, thread_id: UUID) -> QuestionsSession:
    """Get active questions session or create a new one"""
    session = db.query(QuestionsSession).filter(
        QuestionsSession.user_id == user_id,
        QuestionsSession.is_active == True
    ).first()
    
    if not session:
        session = QuestionsSession(
            user_id=user_id,
            thread_id=thread_id,
            is_active=True
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"Created new questions session for user {user_id}")
    
    return session


def _save_robin_messages(
    db: Session, 
    thread_id: UUID, 
    reply: RobinReply
) -> list[ChatMessageResponse]:
    """Save Robin's display messages to the database"""
    messages = []
    
    for msg_text in reply.display_messages:
        if not msg_text:
            continue
            
        # Build metadata including segments for rich rendering
        metadata = {
            "mode": reply.mode,
            "submode": reply.submode,
            "tool_calls": reply.tool_calls_made,
            "has_debug": True  # Flag to show debug button
        }
        # Include segments for clickable task references (if provided)
        if reply.segments:
            metadata["segments"] = reply.segments
        
        chat_message = ChatMessage(
            thread_id=thread_id,
            sender=MessageSender.ROBIN.value,
            text=msg_text,
            msg_metadata=metadata
        )
        db.add(chat_message)
        db.commit()
        db.refresh(chat_message)
        
        # Save comprehensive debug data for each message
        if reply.raw_response:
            debug = MessageDebugData(
                message_id=chat_message.id,
                full_prompt=reply.raw_response.get("full_prompt", []),
                full_response={
                    "mode": reply.mode,
                    "submode": reply.submode,
                    "tool_calls_made": reply.tool_calls_made,
                    "parsed_response": reply.raw_response.get("raw_response", {}),
                    "raw_content": reply.raw_response.get("raw_content", ""),
                    "updates": [u.model_dump() for u in reply.updates],
                    "control": reply.control.model_dump()
                }
            )
            db.add(debug)
            db.commit()
        
        messages.append(ChatMessageResponse(
            id=str(chat_message.id),
            sender=chat_message.sender,
            text=chat_message.text,
            created_at=chat_message.created_at,
            metadata=chat_message.msg_metadata
        ))
    
    return messages


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
):
    """
    Get chat history between current user and Robin.
    
    Returns messages ordered by created_at ascending (chronological order).
    Creates a thread if one doesn't exist yet.
    """
    # Ensure thread exists
    thread = _ensure_thread_exists(db, current_user.id)
    
    # Get messages - get the LATEST N messages, then reverse to chronological order
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread.id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    # Reverse to get chronological order (oldest to newest)
    messages = list(reversed(messages))
    
    return [
        ChatMessageResponse(
            id=str(msg.id),
            sender=msg.sender,
            text=msg.text,
            created_at=msg.created_at,
            metadata=msg.msg_metadata
        )
        for msg in messages
    ]


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message to Robin in Questions mode.
    
    This endpoint:
    1. Saves the user's message
    2. Calls Robin (Questions mode) to generate a reply
    3. Saves Robin's messages
    4. Returns all new messages
    5. Ends session if model signals conversation_done
    """
    logger.info(f"User {current_user.name} sent message: '{request.text[:50]}...'")
    
    # Ensure thread exists
    thread = _ensure_thread_exists(db, current_user.id)
    
    # Get or create questions session
    session = _get_or_create_questions_session(db, current_user.id, thread.id)
    
    # Save user message
    user_message = ChatMessage(
        thread_id=thread.id,
        sender=MessageSender.USER.value,
        text=request.text
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    response_messages = [
        ChatMessageResponse(
            id=str(user_message.id),
            sender=user_message.sender,
            text=user_message.text,
            created_at=user_message.created_at,
            metadata=user_message.msg_metadata
        )
    ]
    
    try:
        logger.info(f"Generating Robin reply (Questions mode) for user {current_user.id}")
        
        # Generate Robin's reply using Questions mode
        robin_reply = await send_questions_message(
            db=db,
            user_id=current_user.id,
            thread_id=thread.id,
            user_message=request.text,
            previous_response_id=session.last_response_id  # Use OpenAI conversation threading
        )
        
        logger.info(f"Robin reply: {len(robin_reply.display_messages)} messages, "
                   f"conversation_done={robin_reply.control.conversation_done}")
        
        # Save Robin's messages
        robin_messages = _save_robin_messages(db, thread.id, robin_reply)
        response_messages.extend(robin_messages)
        
        # Store the response ID for next call (conversation threading)
        if robin_reply.response_id:
            session.last_response_id = robin_reply.response_id
            db.commit()
        
        # Check if session should end
        session_ended = robin_reply.control.conversation_done
        if session_ended:
            session.is_active = False
            db.commit()
            logger.info(f"Questions session ended for user {current_user.id}")
        
        return SendMessageResponse(
            messages=response_messages,
            session_ended=session_ended
        )
        
    except Exception as e:
        logger.error(f"Error generating Robin reply: {e}", exc_info=True)
        
        # Return error message
        error_message = ChatMessage(
            thread_id=thread.id,
            sender=MessageSender.ROBIN.value,
            text="Sorry, I encountered an error processing your message. Please try again.",
            msg_metadata={"error": str(e)}
        )
        db.add(error_message)
        db.commit()
        db.refresh(error_message)
        
        response_messages.append(
            ChatMessageResponse(
                id=str(error_message.id),
                sender=error_message.sender,
                text=error_message.text,
                created_at=error_message.created_at,
                metadata=error_message.msg_metadata
            )
        )
        
        return SendMessageResponse(messages=response_messages)


@router.post("/brief", response_model=SendMessageResponse)
async def trigger_morning_brief(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger a morning brief from Robin.
    
    This is a stateless one-shot call - no conversation history is used.
    Robin uses MCP tools to fetch context and builds a brief.
    """
    logger.info(f"User {current_user.name} requested morning brief")
    
    # Ensure thread exists
    thread = _ensure_thread_exists(db, current_user.id)
    
    # Add a system message indicating brief was requested
    trigger_message = ChatMessage(
        thread_id=thread.id,
        sender=MessageSender.SYSTEM.value,
        text="☀️ Morning Brief requested"
    )
    db.add(trigger_message)
    db.commit()
    db.refresh(trigger_message)
    
    response_messages = [
        ChatMessageResponse(
            id=str(trigger_message.id),
            sender=trigger_message.sender,
            text=trigger_message.text,
            created_at=trigger_message.created_at,
            metadata=trigger_message.msg_metadata
        )
    ]
    
    try:
        # Get morning brief (stateless)
        robin_reply = await get_morning_brief(
            db=db,
            user_id=current_user.id,
            thread_id=thread.id
        )
        
        logger.info(f"Morning brief generated: {len(robin_reply.display_messages)} messages")
        
        # Save Robin's messages
        robin_messages = _save_robin_messages(db, thread.id, robin_reply)
        response_messages.extend(robin_messages)
        
        return SendMessageResponse(messages=response_messages)
        
    except Exception as e:
        logger.error(f"Error generating morning brief: {e}", exc_info=True)
        
        error_message = ChatMessage(
            thread_id=thread.id,
            sender=MessageSender.ROBIN.value,
            text="Sorry, I couldn't generate your morning brief. Please try again.",
            msg_metadata={"error": str(e)}
        )
        db.add(error_message)
        db.commit()
        db.refresh(error_message)
        
        response_messages.append(
            ChatMessageResponse(
                id=str(error_message.id),
                sender=error_message.sender,
                text=error_message.text,
                created_at=error_message.created_at,
                metadata=error_message.msg_metadata
            )
        )
        
        return SendMessageResponse(messages=response_messages)


@router.get("/message/{message_id}/debug")
async def get_message_debug_data(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get debug data (prompt + response) for a specific message.
    """
    try:
        msg_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID")
    
    # Get the message to verify it belongs to the user's thread
    message = db.query(ChatMessage).filter(ChatMessage.id == msg_uuid).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify the message belongs to user's thread
    thread = db.query(ChatThread).filter(
        ChatThread.id == message.thread_id,
        ChatThread.user_id == current_user.id
    ).first()
    if not thread:
        raise HTTPException(status_code=403, detail="Not authorized to view this message")
    
    # Get debug data
    debug_data = db.query(MessageDebugData).filter(
        MessageDebugData.message_id == msg_uuid
    ).first()
    
    if not debug_data:
        raise HTTPException(status_code=404, detail="No debug data available for this message")
    
    return {
        "message_id": str(message.id),
        "full_prompt": debug_data.full_prompt,
        "full_response": debug_data.full_response,
        "created_at": debug_data.created_at.isoformat()
    }


@router.get("/session/status")
async def get_session_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current Questions session status.
    """
    session = db.query(QuestionsSession).filter(
        QuestionsSession.user_id == current_user.id,
        QuestionsSession.is_active == True
    ).first()
    
    return {
        "has_active_session": session is not None,
        "session_id": str(session.id) if session else None,
        "created_at": session.created_at.isoformat() if session else None
    }


@router.post("/session/end")
async def end_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually end the current Questions session.
    """
    session = db.query(QuestionsSession).filter(
        QuestionsSession.user_id == current_user.id,
        QuestionsSession.is_active == True
    ).first()
    
    if session:
        session.is_active = False
        db.commit()
        logger.info(f"Manually ended questions session for user {current_user.id}")
        return {"ended": True, "session_id": str(session.id)}
    
    return {"ended": False, "message": "No active session"}
