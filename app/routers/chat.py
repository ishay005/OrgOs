"""
Chat API endpoints for Robin assistant
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.auth import get_current_user
from app.models import (
    User, ChatThread, ChatMessage, MessageSender,
    Task, AttributeDefinition, AttributeAnswer
)
from app.services.robin_orchestrator import generate_robin_reply, StructuredUpdate

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


# ============================================================================
# Helper Functions
# ============================================================================

def _ensure_thread_exists(db: Session, user_id: str) -> ChatThread:
    """Ensure a chat thread exists for the user, create if not"""
    thread = db.query(ChatThread).filter(ChatThread.user_id == user_id).first()
    
    if not thread:
        thread = ChatThread(user_id=user_id)
        db.add(thread)
        db.commit()
        db.refresh(thread)
        logger.info(f"Created new chat thread for user {user_id}")
    
    return thread


def _apply_structured_update(
    db: Session,
    current_user_id: str,
    update: StructuredUpdate
) -> bool:
    """
    Apply a structured update to the database.
    
    Returns True if successful, False otherwise.
    """
    try:
        # Find the attribute definition
        attr_def = db.query(AttributeDefinition).filter(
            AttributeDefinition.name == update.attribute_name
        ).first()
        
        if not attr_def:
            logger.warning(f"Attribute not found: {update.attribute_name}")
            return False
        
        # Check if task exists (if task_id is provided)
        if update.task_id:
            task = db.query(Task).filter(Task.id == update.task_id).first()
            if not task:
                logger.warning(f"Task not found: {update.task_id}")
                return False
        
        # Check if an answer already exists
        existing_answer = db.query(AttributeAnswer).filter(
            AttributeAnswer.answered_by_user_id == current_user_id,
            AttributeAnswer.target_user_id == update.target_user_id,
            AttributeAnswer.task_id == update.task_id,
            AttributeAnswer.attribute_id == attr_def.id
        ).first()
        
        if existing_answer:
            # Update existing answer
            existing_answer.value = update.value
            existing_answer.refused = False
            logger.info(
                f"Updated answer: user={current_user_id}, "
                f"task={update.task_id}, attr={update.attribute_name}, "
                f"value={update.value}"
            )
        else:
            # Create new answer
            new_answer = AttributeAnswer(
                answered_by_user_id=current_user_id,
                target_user_id=update.target_user_id,
                task_id=update.task_id,
                attribute_id=attr_def.id,
                value=update.value,
                refused=False
            )
            db.add(new_answer)
            logger.info(
                f"Created new answer: user={current_user_id}, "
                f"task={update.task_id}, attr={update.attribute_name}, "
                f"value={update.value}"
            )
        
        db.commit()
        return True
        
    except Exception as e:
        logger.error(f"Error applying structured update: {e}", exc_info=True)
        db.rollback()
        return False


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
    
    # Get messages
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread.id
    ).order_by(ChatMessage.created_at.asc()).limit(limit).all()
    
    return [
        ChatMessageResponse(
            id=str(msg.id),
            sender=msg.sender,  # Already a string, no .value needed
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
    Send a message to Robin and get a reply.
    
    This endpoint:
    1. Saves the user's message
    2. Calls Robin orchestrator to generate a reply
    3. Saves Robin's messages
    4. Applies any structured updates
    5. Returns all new messages (user + Robin)
    """
    logger.info(f"User {current_user.name} sent message: '{request.text[:50]}...'")
    
    # Ensure thread exists
    thread = _ensure_thread_exists(db, current_user.id)
    
    # Save user message
    user_message = ChatMessage(
        thread_id=thread.id,
        sender=MessageSender.USER.value,  # Use .value to get the string
        text=request.text
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    
    response_messages = [
        ChatMessageResponse(
            id=str(user_message.id),
            sender=user_message.sender,  # Already a string, no .value needed
            text=user_message.text,
            created_at=user_message.created_at,
            metadata=user_message.msg_metadata
        )
    ]
    
    try:
        logger.info(f"Generating Robin reply for user {current_user.id}")
        # Generate Robin's reply
        robin_reply = await generate_robin_reply(
            user_id=current_user.id,
            thread_id=thread.id,
            user_message=request.text,
            db=db
        )
        logger.info(f"Robin reply generated: {len(robin_reply.messages)} messages, {len(robin_reply.updates)} updates")
        
        # Apply structured updates
        updates_applied = 0
        for update in robin_reply.updates:
            if _apply_structured_update(db, current_user.id, update):
                updates_applied += 1
        
        logger.info(f"Applied {updates_applied}/{len(robin_reply.updates)} structured updates")
        
        # Save Robin's messages
        for robin_msg in robin_reply.messages:
            # Add metadata about applied updates if any
            metadata = robin_msg.metadata or {}
            if updates_applied > 0 and robin_msg == robin_reply.messages[-1]:
                # Add update info to the last message
                metadata["updates_applied"] = updates_applied
            
            chat_message = ChatMessage(
                thread_id=thread.id,
                sender=MessageSender.ROBIN.value,  # Use .value to get the string
                text=robin_msg.text,
                msg_metadata=metadata if metadata else None
            )
            db.add(chat_message)
            db.commit()
            db.refresh(chat_message)
            
            response_messages.append(
                ChatMessageResponse(
                    id=str(chat_message.id),
                    sender=chat_message.sender,  # Already a string, no .value needed
                    text=chat_message.text,
                    created_at=chat_message.created_at,
                    metadata=chat_message.msg_metadata
                )
            )
        
        return SendMessageResponse(messages=response_messages)
        
    except Exception as e:
        logger.error(f"Error generating Robin reply: {e}", exc_info=True)
        
        # Return error message
        error_message = ChatMessage(
            thread_id=thread.id,
            sender=MessageSender.ROBIN.value,  # Use .value to get the string
            text="Sorry, I encountered an error processing your message. Please try again.",
            msg_metadata={"error": str(e)}
        )
        db.add(error_message)
        db.commit()
        db.refresh(error_message)
        
        response_messages.append(
            ChatMessageResponse(
                id=str(error_message.id),
                sender=error_message.sender,  # Already a string, no .value needed
                text=error_message.text,
                created_at=error_message.created_at,
                metadata=error_message.msg_metadata
            )
        )
        
        return SendMessageResponse(messages=response_messages)


@router.post("/brief")
async def trigger_morning_brief(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger a morning brief from Robin.
    
    This is a convenience endpoint that sends "morning_brief" to Robin.
    """
    return await send_message(
        request=SendMessageRequest(text="morning_brief"),
        current_user=current_user,
        db=db
    )

