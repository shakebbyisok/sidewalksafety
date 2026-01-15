from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class User(Base):
    """Application user."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # User API Keys (Bring Your Own Key)
    openrouter_api_key = Column(Text, nullable=True)  # User's own OpenRouter key
    use_own_openrouter_key = Column(Boolean, default=False)  # Toggle to use own key
    
    # Default preferences
    default_scoring_prompt = Column(Text, nullable=True)  # Saved scoring criteria

    # Relationships
    deals = relationship("Deal", back_populates="user", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")
    scoring_prompts = relationship("ScoringPrompt", back_populates="user", cascade="all, delete-orphan")
