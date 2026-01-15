"""
PropertyBusiness - Association between Property and Business.
Replaces the old ParkingLotBusinessAssociation.
"""
from sqlalchemy import Column, String, Numeric, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class PropertyBusiness(Base):
    """Links properties to their tenant businesses."""
    __tablename__ = "property_businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey('properties.id', ondelete='CASCADE'), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False)
    
    # Relationship details
    is_primary = Column(Boolean, default=False)
    relationship_type = Column(String(50), default='tenant')  # tenant, owner, manager
    match_score = Column(Numeric(5, 2), nullable=True)
    distance_meters = Column(Numeric(10, 2), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    property = relationship("Property", back_populates="businesses")
    business = relationship("Business", back_populates="properties")

    __table_args__ = (
        UniqueConstraint('property_id', 'business_id', name='uq_property_business'),
    )

