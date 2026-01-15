from sqlalchemy import Column, String, Numeric, DateTime, Date, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Deal(Base):
    """Sales pipeline deal for a property."""
    __tablename__ = "deals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Deal info
    title = Column(String(255), nullable=False)
    stage = Column(String(50), default="lead", nullable=False)  # lead, contacted, proposal, negotiation, won, lost
    value = Column(Numeric(12, 2), nullable=True)
    probability = Column(Numeric(5, 2), nullable=True)
    
    # Contact info (can override business contact)
    contact_name = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(255), nullable=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    next_action = Column(Text, nullable=True)
    next_action_date = Column(Date, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="deals")
    property = relationship("Property", back_populates="deals")
    business = relationship("Business", back_populates="deals")

    # Indexes
    __table_args__ = (
        Index('idx_deals_stage', stage),
    )
