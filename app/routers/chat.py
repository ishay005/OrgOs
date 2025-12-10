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
    User, ChatThread, ChatMessage, MessageSender, MessageDebugData,
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
    
    Supports:
    - Creating new tasks (attribute_name="create_task", value=task_title)
    - Updating attributes on existing tasks
    
    Returns True if successful, False otherwise.
    """
    try:
        # Special case: Task creation
        if update.attribute_name == "create_task":
            task_title = update.value
            task_description = None
            
            # Check if task already exists with this title for this user
            existing_task = db.query(Task).filter(
                Task.title == task_title,
                Task.owner_user_id == current_user_id,
                Task.is_active == True
            ).first()
            
            if existing_task:
                logger.info(f"Task already exists: {task_title}")
                return True  # Not an error, task exists
            
            # Create new task
            new_task = Task(
                title=task_title,
                description=task_description,
                owner_user_id=current_user_id,
                is_active=True
            )
            db.add(new_task)
            db.commit()
            logger.info(f"Created new task: {task_title} for user {current_user_id}")
            return True
        
        # Normal attribute update flow
        # Find the attribute definition (case-insensitive)
        attr_def = db.query(AttributeDefinition).filter(
            AttributeDefinition.name.ilike(update.attribute_name)
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
    
    # Get messages - get the LATEST N messages, then reverse to chronological order
    messages = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread.id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    
    # Reverse to get chronological order (oldest to newest)
    messages = list(reversed(messages))
    
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
            
            # Save debug data if available
            if robin_msg.metadata and ('debug_prompt' in robin_msg.metadata or 'full_response' in robin_msg.metadata):
                debug_data = MessageDebugData(
                    message_id=chat_message.id,
                    full_prompt=robin_msg.metadata.get('debug_prompt', {}),
                    full_response=robin_msg.metadata.get('full_response', {})
                )
                db.add(debug_data)
                db.commit()
            
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



@router.get("/message/{message_id}/debug")
async def get_message_debug_data(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get debug data (prompt + response) for a specific message.
    """
    from uuid import UUID
    
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
