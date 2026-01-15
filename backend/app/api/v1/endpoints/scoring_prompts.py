"""
Scoring Prompts API

Manage user's saved lead scoring prompts.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

from app.db.base import get_db
from app.models.scoring_prompt import ScoringPrompt
from app.models.user import User
from app.core.dependencies import get_current_user

router = APIRouter()


# ============ Schemas ============

class ScoringPromptResponse(BaseModel):
    """Scoring prompt response."""
    id: str
    title: str
    prompt: str
    is_default: bool
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class CreateScoringPromptRequest(BaseModel):
    """Create a new scoring prompt."""
    title: str = Field(..., min_length=1, max_length=255)
    prompt: str = Field(..., min_length=10)
    is_default: bool = Field(default=False)


class UpdateScoringPromptRequest(BaseModel):
    """Update a scoring prompt."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    prompt: Optional[str] = Field(None, min_length=10)
    is_default: Optional[bool] = None


# ============ Endpoints ============

@router.get("", response_model=List[ScoringPromptResponse])
def list_scoring_prompts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all scoring prompts for the current user."""
    prompts = db.query(ScoringPrompt).filter(
        ScoringPrompt.user_id == current_user.id
    ).order_by(
        ScoringPrompt.is_default.desc(),  # Default first
        ScoringPrompt.created_at.desc()
    ).all()
    
    return [
        ScoringPromptResponse(
            id=str(p.id),
            title=p.title,
            prompt=p.prompt,
            is_default=p.is_default,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat() if p.updated_at else None,
        )
        for p in prompts
    ]


@router.post("", response_model=ScoringPromptResponse)
def create_scoring_prompt(
    request: CreateScoringPromptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new scoring prompt."""
    # If setting as default, unset other defaults
    if request.is_default:
        db.query(ScoringPrompt).filter(
            and_(
                ScoringPrompt.user_id == current_user.id,
                ScoringPrompt.is_default == True
            )
        ).update({"is_default": False})
    
    prompt = ScoringPrompt(
        user_id=current_user.id,
        title=request.title,
        prompt=request.prompt,
        is_default=request.is_default,
    )
    
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    
    return ScoringPromptResponse(
        id=str(prompt.id),
        title=prompt.title,
        prompt=prompt.prompt,
        is_default=prompt.is_default,
        created_at=prompt.created_at.isoformat(),
        updated_at=prompt.updated_at.isoformat() if prompt.updated_at else None,
    )


@router.get("/{prompt_id}", response_model=ScoringPromptResponse)
def get_scoring_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific scoring prompt."""
    prompt = db.query(ScoringPrompt).filter(
        and_(
            ScoringPrompt.id == prompt_id,
            ScoringPrompt.user_id == current_user.id
        )
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Scoring prompt not found")
    
    return ScoringPromptResponse(
        id=str(prompt.id),
        title=prompt.title,
        prompt=prompt.prompt,
        is_default=prompt.is_default,
        created_at=prompt.created_at.isoformat(),
        updated_at=prompt.updated_at.isoformat() if prompt.updated_at else None,
    )


@router.patch("/{prompt_id}", response_model=ScoringPromptResponse)
def update_scoring_prompt(
    prompt_id: UUID,
    request: UpdateScoringPromptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a scoring prompt."""
    prompt = db.query(ScoringPrompt).filter(
        and_(
            ScoringPrompt.id == prompt_id,
            ScoringPrompt.user_id == current_user.id
        )
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Scoring prompt not found")
    
    # If setting as default, unset other defaults
    if request.is_default is True:
        db.query(ScoringPrompt).filter(
            and_(
                ScoringPrompt.user_id == current_user.id,
                ScoringPrompt.id != prompt_id,
                ScoringPrompt.is_default == True
            )
        ).update({"is_default": False})
    
    # Update fields
    if request.title is not None:
        prompt.title = request.title
    if request.prompt is not None:
        prompt.prompt = request.prompt
    if request.is_default is not None:
        prompt.is_default = request.is_default
    
    db.commit()
    db.refresh(prompt)
    
    return ScoringPromptResponse(
        id=str(prompt.id),
        title=prompt.title,
        prompt=prompt.prompt,
        is_default=prompt.is_default,
        created_at=prompt.created_at.isoformat(),
        updated_at=prompt.updated_at.isoformat() if prompt.updated_at else None,
    )


@router.delete("/{prompt_id}")
def delete_scoring_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a scoring prompt."""
    prompt = db.query(ScoringPrompt).filter(
        and_(
            ScoringPrompt.id == prompt_id,
            ScoringPrompt.user_id == current_user.id
        )
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Scoring prompt not found")
    
    db.delete(prompt)
    db.commit()
    
    return {"message": "Scoring prompt deleted successfully"}

