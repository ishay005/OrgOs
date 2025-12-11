"""
Daily Sync API endpoints
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from pydantic import BaseModel

from app.database import get_db
from app.models import ChatThread, ChatMessage, DailySyncSession, DailySyncPhase, MessageDebugData
from app.services import daily_sync_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/daily", tags=["daily_sync"])


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


@router.post("/start", response_model=DailySyncStartResponse)
async def start_daily_sync(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Start a new Daily Sync session.
    
    Creates a session, generates greeting + morning brief,
    and returns initial messages.
    """
    try:
        user_id = UUID(x_user_id)
    except Exception as e:
        logger.error(f"❌ Invalid user ID: {x_user_id}")
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {x_user_id}")
    
    logger.info(f"🚀 /daily/start called for user {user_id}")
    
    try:
        # Check if there's already an active session
        existing_session = daily_sync_orchestrator.get_active_daily_session(db, user_id)
        if existing_session:
            logger.warning(f"⚠️  User {user_id} already has active Daily Sync session in phase {existing_session.phase}")
            raise HTTPException(
                status_code=400,
                detail=f"Daily Sync already in progress (phase: {existing_session.phase}). Complete or cancel it first."
            )
        
        # Get or create chat thread
        thread = db.query(ChatThread).filter(ChatThread.user_id == user_id).first()
        if not thread:
            thread = ChatThread(user_id=user_id)
            db.add(thread)
            db.commit()
            db.refresh(thread)
        
        # Get insight questions
        insight_questions = daily_sync_orchestrator.get_insight_questions_for_daily_sync(db, user_id)
        
        # Create session
        session = daily_sync_orchestrator.create_daily_session(
            db, user_id, thread.id, insight_questions
        )
        
        # Get contexts
        user_ctx = daily_sync_orchestrator.get_daily_user_context(db, user_id)
        situation_ctx = daily_sync_orchestrator.get_daily_situation_context(db, user_id)
        
        # Generate greeting (no user message yet)
        result = await daily_sync_orchestrator.handle_daily_sync_turn(
            db, session, user_ctx, situation_ctx, None
        )
        
        # Store Robin's messages and collect response data
        response_messages = []
        logger.info(f"📝 Daily START - Storing {len(result.messages)} messages")
        for i, msg in enumerate(result.messages):
            logger.info(f"  Msg {i}: len={len(msg.text)}, preview: '{msg.text[:100]}'")
            chat_msg = ChatMessage(
                thread_id=thread.id,
                sender="robin",
                text=msg.text,
                msg_metadata=msg.metadata or {}
            )
            db.add(chat_msg)
            db.commit()
            db.refresh(chat_msg)
            
            # Save debug data if available
            if msg.metadata and ('debug_prompt' in msg.metadata or 'full_response' in msg.metadata):
                debug_data = MessageDebugData(
                    message_id=chat_msg.id,
                    full_prompt=msg.metadata.get('debug_prompt', {}),
                    full_response=msg.metadata.get('full_response', {})
                )
                db.add(debug_data)
                db.commit()
            
            # Add to response with message ID
            response_messages.append({
                "id": str(chat_msg.id),
                "sender": "robin",
                "text": msg.text,
                "metadata": msg.metadata,
                "created_at": chat_msg.created_at.isoformat()
            })
        
        # Update session phase
        session.phase = result.new_phase
        daily_sync_orchestrator.update_daily_session(db, session)
        
        db.commit()
        
        return DailySyncStartResponse(
            messages=response_messages,
            phase=result.new_phase.value,
            session_id=str(session.id)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Daily Sync start error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Daily Sync start failed: {str(e)}")


@router.post("/send", response_model=DailySyncSendResponse)
async def send_daily_sync_message(
    request: DailySyncSendRequest,
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Send a message during an active Daily Sync session.
    """
    user_id = UUID(x_user_id)
    logger.info(f"📨 /daily/send called for user {user_id}, message: '{request.text[:50]}'")
    
    # Get active session
    session = daily_sync_orchestrator.get_active_daily_session(db, user_id)
    if not session:
        logger.error(f"❌ No active Daily Sync session for user {user_id}")
        raise HTTPException(
            status_code=404,
            detail="No active Daily Sync session. Start one with POST /daily/start"
        )
    
    logger.info(f"📊 Current session phase: {session.phase}")
    
    # Store user message
    user_msg = ChatMessage(
        thread_id=session.thread_id,
        sender="user",
        text=request.text,
        msg_metadata={}
    )
    db.add(user_msg)
    db.commit()
    
    # Get contexts
    user_ctx = daily_sync_orchestrator.get_daily_user_context(db, user_id)
    situation_ctx = daily_sync_orchestrator.get_daily_situation_context(db, user_id)
    
    # Process turn
    result = await daily_sync_orchestrator.handle_daily_sync_turn(
        db, session, user_ctx, situation_ctx, request.text
    )
    
    # Store Robin's messages and collect response data
    response_messages = []
    for msg in result.messages:
        chat_msg = ChatMessage(
            thread_id=session.thread_id,
            sender="robin",
            text=msg.text,
            msg_metadata=msg.metadata or {}
        )
        db.add(chat_msg)
        db.commit()
        db.refresh(chat_msg)
        
        # Save debug data if available
        if msg.metadata and ('debug_prompt' in msg.metadata or 'full_response' in msg.metadata):
            debug_data = MessageDebugData(
                message_id=chat_msg.id,
                full_prompt=msg.metadata.get('debug_prompt', {}),
                full_response=msg.metadata.get('full_response', {})
            )
            db.add(debug_data)
            db.commit()
        
        # Add to response with message ID
        response_messages.append({
            "id": str(chat_msg.id),
            "sender": "robin",
            "text": msg.text,
            "metadata": msg.metadata,
            "created_at": chat_msg.created_at.isoformat()
        })
    
    # Apply updates
    for update in result.updates:
        # TODO: Apply structured updates to AttributeAnswer
        logger.info(f"Update: {update}")
    
    # Update session phase
    session.phase = result.new_phase
    
    # If done, deactivate session
    if result.new_phase == DailySyncPhase.DONE:
        daily_sync_orchestrator.end_daily_session(db, session)
    else:
        daily_sync_orchestrator.update_daily_session(db, session)
    
    db.commit()
    
    return DailySyncSendResponse(
        messages=response_messages,
        phase=result.new_phase.value,
        is_complete=(result.new_phase == DailySyncPhase.DONE)
    )


@router.get("/status")
async def get_daily_sync_status(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """Check if user has an active Daily Sync session"""
    user_id = UUID(x_user_id)
    session = daily_sync_orchestrator.get_active_daily_session(db, user_id)
    
    if session:
        return {
            "has_active_session": True,
            "session_id": str(session.id),
            "phase": session.phase.value,
            "created_at": session.created_at.isoformat()
        }
    else:
        return {
            "has_active_session": False
        }


@router.post("/end")
async def end_daily_sync(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """Manually end the active Daily Sync session"""
    user_id = UUID(x_user_id)
    
    # Get active session
    session = daily_sync_orchestrator.get_active_daily_session(db, user_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="No active Daily Sync session"
        )
    
    # End the session
    daily_sync_orchestrator.end_daily_session(db, session)
    
    return {
        "message": "Daily Sync session ended",
        "session_id": str(session.id)
    }


@router.get("/cancel-all")
async def cancel_all_daily_sync_sessions(
    db: Session = Depends(get_db),
    x_user_id: str = Header(...)
):
    """
    Force cancel ALL active Daily Sync sessions for the user.
    Use this to clear stuck sessions.
    """
    user_id = UUID(x_user_id)
    
    # Find all active sessions for this user
    from app.models import DailySyncSession
    active_sessions = db.query(DailySyncSession).filter(
        DailySyncSession.user_id == user_id,
        DailySyncSession.is_active == True
    ).all()
    
    count = len(active_sessions)
    for session in active_sessions:
        session.is_active = False
    
    db.commit()
    
    return {
        "message": f"Cancelled {count} active Daily Sync session(s)",
        "cancelled_count": count
    }

