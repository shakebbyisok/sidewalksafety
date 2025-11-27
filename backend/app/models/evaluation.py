from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False, unique=True)
    deal_score = Column(Numeric(5, 2), nullable=True)
    parking_lot_area_sqft = Column(Numeric(12, 2), nullable=True)
    crack_density_percent = Column(Numeric(5, 2), nullable=True)
    damage_severity = Column(String, nullable=True)
    estimated_repair_cost = Column(Numeric(12, 2), nullable=True)
    estimated_job_value = Column(Numeric(12, 2), nullable=True)
    satellite_image_url = Column(Text, nullable=True)
    parking_lot_mask = Column(JSON, nullable=True)
    crack_detections = Column(JSON, nullable=True)
    evaluation_metadata = Column(JSON, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

    deal = relationship("Deal", back_populates="evaluation")

