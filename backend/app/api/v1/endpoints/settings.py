"""
User Settings API

Manage user preferences, API keys, and account settings.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from app.db.base import get_db
from app.models.user import User
from app.core.dependencies import get_current_user

router = APIRouter()


# ============ Schemas ============

class UserSettingsResponse(BaseModel):
    """User settings response."""
    email: str
    company_name: str
    phone: Optional[str]
    
    # API Keys (masked for security)
    has_openrouter_key: bool
    openrouter_key_preview: Optional[str]  # Shows "sk-or-...xxxx" format
    use_own_openrouter_key: bool
    
    # Preferences
    default_scoring_prompt: Optional[str]


class UpdateProfileRequest(BaseModel):
    """Update profile info."""
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)


class UpdateOpenRouterKeyRequest(BaseModel):
    """Update OpenRouter API key."""
    api_key: Optional[str] = Field(None, description="OpenRouter API key (set to null to remove)")
    enabled: bool = Field(..., description="Whether to use own key")


class UpdateScoringPromptRequest(BaseModel):
    """Update default scoring prompt."""
    scoring_prompt: Optional[str] = Field(None, description="Default scoring criteria")


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str
    new_password: str = Field(..., min_length=8)


# ============ Helper Functions ============

def mask_api_key(key: Optional[str]) -> Optional[str]:
    """Mask API key for display: sk-or-v1-abc...xyz"""
    if not key:
        return None
    if len(key) <= 12:
        return "***"
    return f"{key[:10]}...{key[-4:]}"


def settings_to_response(user: User) -> UserSettingsResponse:
    """Convert user to settings response."""
    return UserSettingsResponse(
        email=user.email,
        company_name=user.company_name,
        phone=user.phone,
        has_openrouter_key=bool(user.openrouter_api_key),
        openrouter_key_preview=mask_api_key(user.openrouter_api_key),
        use_own_openrouter_key=user.use_own_openrouter_key or False,
        default_scoring_prompt=user.default_scoring_prompt,
    )


# ============ Endpoints ============

@router.get("", response_model=UserSettingsResponse)
def get_settings(
    current_user: User = Depends(get_current_user),
):
    """Get current user's settings."""
    return settings_to_response(current_user)


@router.patch("/profile", response_model=UserSettingsResponse)
def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update profile information."""
    if request.company_name is not None:
        current_user.company_name = request.company_name
    if request.phone is not None:
        current_user.phone = request.phone
    
    db.commit()
    db.refresh(current_user)
    
    return settings_to_response(current_user)


@router.patch("/openrouter-key", response_model=UserSettingsResponse)
def update_openrouter_key(
    request: UpdateOpenRouterKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update OpenRouter API key settings.
    
    - Set api_key to save a new key
    - Set api_key to null/empty to remove key
    - Set enabled to toggle using own key vs system key
    """
    # Update key if provided
    if request.api_key is not None:
        if request.api_key == "" or request.api_key.lower() == "null":
            # Remove key
            current_user.openrouter_api_key = None
        else:
            # Validate key format (basic check)
            if not request.api_key.startswith("sk-"):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid API key format. OpenRouter keys start with 'sk-'"
                )
            current_user.openrouter_api_key = request.api_key
    
    # Update enabled toggle
    current_user.use_own_openrouter_key = request.enabled
    
    # If enabling but no key, disable
    if request.enabled and not current_user.openrouter_api_key:
        current_user.use_own_openrouter_key = False
    
    db.commit()
    db.refresh(current_user)
    
    return settings_to_response(current_user)


@router.patch("/scoring-prompt", response_model=UserSettingsResponse)
def update_scoring_prompt(
    request: UpdateScoringPromptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update default scoring prompt."""
    current_user.default_scoring_prompt = request.scoring_prompt
    
    db.commit()
    db.refresh(current_user)
    
    return settings_to_response(current_user)


@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user password."""
    from app.core.security import verify_password, get_password_hash
    
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    current_user.hashed_password = get_password_hash(request.new_password)
    
    db.commit()
    
    return {"message": "Password changed successfully"}


@router.delete("/openrouter-key", response_model=UserSettingsResponse)
def delete_openrouter_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove OpenRouter API key."""
    current_user.openrouter_api_key = None
    current_user.use_own_openrouter_key = False
    
    db.commit()
    db.refresh(current_user)
    
    return settings_to_response(current_user)

