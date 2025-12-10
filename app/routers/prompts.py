"""
Prompt management endpoints for Robin
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import PromptTemplate
import logging

router = APIRouter(prefix="/prompts", tags=["prompts"])
logger = logging.getLogger(__name__)


class PromptTemplateResponse(BaseModel):
    id: str
    mode: str
    has_pending: bool
    prompt_text: str
    context_config: Dict[str, Any]
    version: int
    is_active: bool
    created_at: datetime
    created_by: Optional[str]
    notes: Optional[str]


class PromptTemplateCreate(BaseModel):
    mode: str
    has_pending: bool
    prompt_text: str
    context_config: Dict[str, Any]
    created_by: Optional[str] = None
    notes: Optional[str] = None


class PromptTemplateUpdate(BaseModel):
    prompt_text: Optional[str] = None
    context_config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


@router.get("/", response_model=list[PromptTemplateResponse])
async def get_all_prompts(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get all prompt templates"""
    query = db.query(PromptTemplate)
    
    if active_only:
        query = query.filter(PromptTemplate.is_active == True)
    
    prompts = query.order_by(
        PromptTemplate.mode,
        PromptTemplate.has_pending,
        PromptTemplate.version.desc()
    ).all()
    
    return [
        PromptTemplateResponse(
            id=str(p.id),
            mode=p.mode,
            has_pending=p.has_pending,
            prompt_text=p.prompt_text,
            context_config=p.context_config,
            version=p.version,
            is_active=p.is_active,
            created_at=p.created_at,
            created_by=p.created_by,
            notes=p.notes
        )
        for p in prompts
    ]


@router.get("/{mode}/{has_pending}", response_model=PromptTemplateResponse)
async def get_prompt_for_mode(
    mode: str,
    has_pending: bool,
    db: Session = Depends(get_db)
):
    """Get active prompt for specific mode and pending status"""
    prompt = db.query(PromptTemplate).filter(
        PromptTemplate.mode == mode,
        PromptTemplate.has_pending == has_pending,
        PromptTemplate.is_active == True
    ).order_by(PromptTemplate.version.desc()).first()
    
    if not prompt:
        raise HTTPException(
            status_code=404,
            detail=f"No active prompt found for mode={mode}, has_pending={has_pending}"
        )
    
    return PromptTemplateResponse(
        id=str(prompt.id),
        mode=prompt.mode,
        has_pending=prompt.has_pending,
        prompt_text=prompt.prompt_text,
        context_config=prompt.context_config,
        version=prompt.version,
        is_active=prompt.is_active,
        created_at=prompt.created_at,
        created_by=prompt.created_by,
        notes=prompt.notes
    )


@router.post("/", response_model=PromptTemplateResponse)
async def create_prompt(
    prompt_data: PromptTemplateCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new prompt version.
    Automatically deactivates previous versions for same mode/has_pending.
    """
    # Deactivate previous versions
    db.query(PromptTemplate).filter(
        PromptTemplate.mode == prompt_data.mode,
        PromptTemplate.has_pending == prompt_data.has_pending
    ).update({"is_active": False})
    
    # Get next version number
    max_version = db.query(PromptTemplate).filter(
        PromptTemplate.mode == prompt_data.mode,
        PromptTemplate.has_pending == prompt_data.has_pending
    ).count()
    
    # Create new prompt
    new_prompt = PromptTemplate(
        mode=prompt_data.mode,
        has_pending=prompt_data.has_pending,
        prompt_text=prompt_data.prompt_text,
        context_config=prompt_data.context_config,
        version=max_version + 1,
        is_active=True,
        created_by=prompt_data.created_by,
        notes=prompt_data.notes
    )
    
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)
    
    logger.info(f"Created new prompt: mode={new_prompt.mode}, has_pending={new_prompt.has_pending}, v{new_prompt.version}")
    
    return PromptTemplateResponse(
        id=str(new_prompt.id),
        mode=new_prompt.mode,
        has_pending=new_prompt.has_pending,
        prompt_text=new_prompt.prompt_text,
        context_config=new_prompt.context_config,
        version=new_prompt.version,
        is_active=new_prompt.is_active,
        created_at=new_prompt.created_at,
        created_by=new_prompt.created_by,
        notes=new_prompt.notes
    )


@router.put("/{prompt_id}", response_model=PromptTemplateResponse)
async def update_prompt(
    prompt_id: UUID,
    prompt_data: PromptTemplateUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing prompt.
    Creates a new version with the changes.
    """
    # Get existing prompt
    existing = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Deactivate all versions for this mode/has_pending
    db.query(PromptTemplate).filter(
        PromptTemplate.mode == existing.mode,
        PromptTemplate.has_pending == existing.has_pending
    ).update({"is_active": False})
    
    # Create new version
    new_version = PromptTemplate(
        mode=existing.mode,
        has_pending=existing.has_pending,
        prompt_text=prompt_data.prompt_text or existing.prompt_text,
        context_config=prompt_data.context_config or existing.context_config,
        version=existing.version + 1,
        is_active=True,
        created_by=prompt_data.notes or existing.created_by,
        notes=prompt_data.notes
    )
    
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    
    logger.info(f"Updated prompt: mode={new_version.mode}, has_pending={new_version.has_pending}, v{new_version.version}")
    
    return PromptTemplateResponse(
        id=str(new_version.id),
        mode=new_version.mode,
        has_pending=new_version.has_pending,
        prompt_text=new_version.prompt_text,
        context_config=new_version.context_config,
        version=new_version.version,
        is_active=new_version.is_active,
        created_at=new_version.created_at,
        created_by=new_version.created_by,
        notes=new_version.notes
    )


@router.get("/history/{mode}/{has_pending}", response_model=list[PromptTemplateResponse])
async def get_prompt_history(
    mode: str,
    has_pending: bool,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get version history for a specific mode (latest 10 versions)"""
    prompts = db.query(PromptTemplate).filter(
        PromptTemplate.mode == mode,
        PromptTemplate.has_pending == has_pending
    ).order_by(PromptTemplate.version.desc()).limit(limit).all()
    
    return [
        PromptTemplateResponse(
            id=str(p.id),
            mode=p.mode,
            has_pending=p.has_pending,
            prompt_text=p.prompt_text,
            context_config=p.context_config,
            version=p.version,
            is_active=p.is_active,
            created_at=p.created_at,
            created_by=p.created_by,
            notes=p.notes
        )
        for p in prompts
    ]


@router.post("/{prompt_id}/activate")
async def activate_prompt(
    prompt_id: UUID,
    db: Session = Depends(get_db)
):
    """Activate a specific prompt version"""
    prompt = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    # Deactivate all other versions
    db.query(PromptTemplate).filter(
        PromptTemplate.mode == prompt.mode,
        PromptTemplate.has_pending == prompt.has_pending
    ).update({"is_active": False})
    
    # Activate this one
    prompt.is_active = True
    db.commit()
    
    logger.info(f"Activated prompt: mode={prompt.mode}, has_pending={prompt.has_pending}, v{prompt.version}")
    
    return {"success": True, "message": f"Activated version {prompt.version}"}

