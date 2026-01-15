from sqlalchemy import Column, String, Integer, BigInteger, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.db.base import Base


class UsageLog(Base):
    """Track API and compute usage per user."""
    
    __tablename__ = "usage_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # What was used
    service = Column(String(50), nullable=False, index=True)  # 'google_places', 'regrid', 'satellite', 'vlm'
    operation = Column(String(100), nullable=True)
    
    # Metrics
    api_calls = Column(Integer, default=1)
    tokens_used = Column(Integer, nullable=True)
    cost_estimate = Column(Numeric(10, 6), nullable=True)
    
    # Context
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    extra_data = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    user = relationship("User", back_populates="usage_logs")
    
    def __repr__(self):
        return f"<UsageLog {self.service}:{self.operation} user={self.user_id}>"

