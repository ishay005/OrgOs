"""
Daily Sync API endpoints

Updated for the new architecture with:
- call_robin() using function calling
- Model-driven phase transitions (questions -> summary)
- Simplified flow: opening -> questions -> summary -> done
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import ChatThread, ChatMessage, DailySyncSession, DailySyncPhase, MessageDebugData, User
from app.services.robin_core import start_daily_sync, continue_daily_sync, RobinReply
from app.services.cortex_tools import get_insight_questions_for_daily

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/daily", tags=["daily_sync"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DailySyncStartResponse(BaseModel):
    messages: list[dict]
    phase: str
    session_id: str


class DailySyncSendRequest(BaseModel):
    text: str


class DailySyncSendResponse(BaseModel):
    messages: list[dict]
    phase: str
    is_complete: bool


class DailySyncStatusResponse(BaseModel):
    has_active_session: bool
    session_id: Optional[str] = None
    phase: Optional[str] = None
    created_at: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def _get_active_session(db: Session, user_id: UUID) -> Optional[DailySyncSession]:
    """Get the active Daily Sync session for a user, if any"""
    return db.query(DailySyncSession).filter(
        DailySyncSession.user_id == user_id,
        DailySyncSession.is_active == True
    ).first()


def _ensure_thread_exists(db: Session, user_id: UUID) -> ChatThread:
    """Ensure a chat thread exists for the user"""
    thread = db.query(ChatThread).filter(ChatThread.user_id == user_id).first()
    if not thread:
        thread = ChatThread(user_id=user_id)
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread


def _create_daily_session(
    db: Session, 
    user_id: UUID, 
    thread_id: UUID
) -> DailySyncSession:
    """Create a new Daily Sync session"""
    # Get insight questions to cache in session
    insight_questions = get_insight_questions_for_daily(db, user_id, None)
    insight_questions_json = [q.model_dump() for q in insight_questions]
    
    session = DailySyncSession(
        user_id=user_id,
        thread_id=thread_id,
        phase=DailySyncPhase.OPENING_BRIEF,
        is_active=True,
        insight_questions=insight_questions_json,
        asked_question_ids=[],
        answered_question_ids=[]
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    logger.info(f"Created Daily Sync session {session.id} with {len(insight_questions_json)} insight questions")
    return session


def _save_robin_messages(
    db: Session, 
    thread_id: UUID, 
    reply: RobinReply
) -> list[dict]:
    """Save Robin's messages and return response dicts"""
    messages = []
    
    for msg_text in reply.display_messages:
        if not msg_text:
            continue
        
        # Build metadata including segments for rich rendering
        msg_metadata = {
            "mode": reply.mode,
            "submode": reply.submode,
            "tool_calls": reply.tool_calls_made,
            "has_debug": True
        }
        # Include segments for clickable task references (if provided)
        if reply.segments:
            msg_metadata["segments"] = reply.segments
            
        chat_msg = ChatMessage(
            thread_id=thread_id,
            sender="robin",
            text=msg_text,
            msg_metadata=msg_metadata
        )
        db.add(chat_msg)
        db.commit()
        db.refresh(chat_msg)
        
        # Save comprehensive debug data
        if reply.raw_response:
            debug = MessageDebugData(
                message_id=chat_msg.id,
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
        
        # Build response dict including metadata with segments
        response_dict = {
            "id": str(chat_msg.id),
            "text": chat_msg.text,
            "sender": "robin",
            "created_at": chat_msg.created_at.isoformat(),
            "metadata": msg_metadata  # Include metadata for frontend rendering
        }
        messages.append(response_dict)
    
    return messages


def _update_session_phase(
    db: Session, 
    session: DailySyncSession, 
    reply: RobinReply
):
    """Update session phase based on Robin's control signals"""
    current_phase = session.phase
    if hasattr(current_phase, 'value'):
        current_phase = current_phase.value
    
    # Check for phase transition
    if reply.control.next_phase == "summary":
        session.phase = DailySyncPhase.SUMMARY
        logger.info(f"Phase transition: {current_phase} -> summary")
    
    # Check for completion
    if reply.control.conversation_done:
        session.phase = DailySyncPhase.DONE
        session.is_active = False
        logger.info(f"Daily Sync complete, session {session.id} marked inactive")
    
    session.updated_at = datetime.utcnow()
    db.commit()


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/start", response_model=DailySyncStartResponse)
async def start_daily(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Start a new Daily Sync session.
    
    Creates a session and generates the opening message.
    """
    try:
        user_id = UUID(x_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {x_user_id}")
    
    logger.info(f"🚀 /daily/start called for user {user_id}")
    
    # Check for existing session
    existing = _get_active_session(db, user_id)
    if existing:
        phase = existing.phase.value if hasattr(existing.phase, 'value') else existing.phase
        raise HTTPException(
            status_code=400,
            detail=f"Daily Sync already in progress (phase: {phase}). End it first."
        )
    
    # Ensure thread exists
    thread = _ensure_thread_exists(db, user_id)
    
    # Create session
    session = _create_daily_session(db, user_id, thread.id)
    
    # Add system message
    system_msg = ChatMessage(
        thread_id=thread.id,
        sender="system",
        text="🌅 Daily Sync started"
    )
    db.add(system_msg)
    db.commit()
    
    try:
        # Generate opening message
        reply = await start_daily_sync(
            db=db,
            user_id=user_id,
            thread_id=thread.id,
            daily_session=session
        )
        
        # Save messages
        messages = _save_robin_messages(db, thread.id, reply)
        
        # Store the response ID for conversation threading
        if reply.response_id:
            session.last_response_id = reply.response_id
        
        # Move to questions phase after opening
        session.phase = DailySyncPhase.QUESTIONS
        db.commit()
        
        return DailySyncStartResponse(
            messages=messages,
            phase="questions",  # Always move to questions after opening
            session_id=str(session.id)
        )
        
    except Exception as e:
        logger.error(f"Error starting Daily Sync: {e}", exc_info=True)
        # Clean up session
        session.is_active = False
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send", response_model=DailySyncSendResponse)
async def send_daily_message(
    request: DailySyncSendRequest,
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Send a message during Daily Sync.
    
    Handles the conversation and phase transitions.
    """
    try:
        user_id = UUID(x_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {x_user_id}")
    
    logger.info(f"📨 /daily/send: '{request.text[:50]}...'")
    
    # Get active session
    session = _get_active_session(db, user_id)
    if not session:
        raise HTTPException(status_code=400, detail="No active Daily Sync session")
    
    # Get thread
    thread = db.query(ChatThread).filter(ChatThread.id == session.thread_id).first()
    if not thread:
        raise HTTPException(status_code=500, detail="Thread not found")
    
    # Save user message
    user_msg = ChatMessage(
        thread_id=thread.id,
        sender="user",
        text=request.text
    )
    db.add(user_msg)
    db.commit()
    
    try:
        # Generate reply
        reply = await continue_daily_sync(
            db=db,
            user_id=user_id,
            thread_id=thread.id,
            daily_session=session,
            user_message=request.text
        )
        
        # Store the response ID for conversation threading
        if reply.response_id:
            session.last_response_id = reply.response_id
            db.commit()
        
        # Update phase based on control signals
        _update_session_phase(db, session, reply)
        
        # Save messages
        messages = _save_robin_messages(db, thread.id, reply)
        
        # Get current phase
        phase = session.phase
        if hasattr(phase, 'value'):
            phase = phase.value
        
        return DailySyncSendResponse(
            messages=messages,
            phase=phase,
            is_complete=(phase == "done" or not session.is_active)
        )
        
    except Exception as e:
        logger.error(f"Error in Daily Sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/end")
async def end_daily_sync(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Manually end the current Daily Sync session.
    """
    try:
        user_id = UUID(x_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {x_user_id}")
    
    session = _get_active_session(db, user_id)
    if not session:
        return {"ended": False, "message": "No active session"}
    
    session.is_active = False
    session.phase = DailySyncPhase.DONE
    db.commit()
    
    logger.info(f"Manually ended Daily Sync session {session.id}")
    return {"ended": True, "session_id": str(session.id)}


@router.get("/status", response_model=DailySyncStatusResponse)
async def get_daily_status(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Get the current Daily Sync session status.
    """
    try:
        user_id = UUID(x_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {x_user_id}")
    
    session = _get_active_session(db, user_id)
    
    if not session:
        return DailySyncStatusResponse(has_active_session=False)
    
    phase = session.phase
    if hasattr(phase, 'value'):
        phase = phase.value
    
    return DailySyncStatusResponse(
        has_active_session=True,
        session_id=str(session.id),
        phase=phase,
        created_at=session.created_at.isoformat()
    )
