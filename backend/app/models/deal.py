from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Deal(Base):
    __tablename__ = "deals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    business_name = Column(String, nullable=False, index=True)
    address = Column(String, nullable=False)
    city = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True, index=True)
    zip = Column(String, nullable=True, index=True)
    county = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    category = Column(String, nullable=True)
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    places_id = Column(String, nullable=True)
    apollo_id = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False, index=True)
    has_property_verified = Column(Boolean, default=False, nullable=False, index=True)
    property_verification_method = Column(String, nullable=True)
    property_type = Column(String, default="parking_lot", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="deals")
    evaluation = relationship("Evaluation", back_populates="deal", uselist=False)

