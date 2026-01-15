from sqlalchemy import Column, String, DateTime, Integer, Numeric, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geography
import uuid

from app.db.base import Base


class Business(Base):
    """Business/tenant at a property - from Google Places."""
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Google Places data
    places_id = Column(String(255), unique=True, nullable=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    location = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    
    # Contact info
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    
    # Business details
    category = Column(String(100), nullable=True)
    business_type = Column(String(100), nullable=True)
    rating = Column(Numeric(2, 1), nullable=True)
    review_count = Column(Integer, nullable=True)
    
    # Raw data
    raw_data = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    properties = relationship("PropertyBusiness", back_populates="business", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="business", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_businesses_location', location, postgresql_using='gist'),
    )

