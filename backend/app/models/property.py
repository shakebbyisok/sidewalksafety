"""
Property model - represents a commercial property (lead).
Replaces the old ParkingLot model with cleaner naming.
"""
from sqlalchemy import Column, String, Numeric, DateTime, Boolean, Text, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geography
import uuid

from app.db.base import Base


class Property(Base):
    """Commercial property - the main entity for lead generation."""
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Location
    centroid = Column(Geography(geometry_type='POINT', srid=4326), nullable=False)
    address = Column(String(500), nullable=True)
    
    # Regrid Property Data
    regrid_id = Column(String(100), nullable=True)
    regrid_apn = Column(String(100), nullable=True)
    regrid_owner = Column(String(255), nullable=True)
    regrid_owner2 = Column(String(255), nullable=True)  # Secondary owner (often mgmt company)
    regrid_owner_type = Column(String(50), nullable=True)
    regrid_owner_address = Column(Text, nullable=True)
    regrid_owner_city = Column(String(100), nullable=True)
    regrid_owner_state = Column(String(10), nullable=True)
    regrid_polygon = Column(Geography(geometry_type='POLYGON', srid=4326), nullable=True)
    regrid_land_use = Column(String(100), nullable=True)  # usedesc or usecode
    regrid_zoning = Column(String(50), nullable=True)
    regrid_zoning_desc = Column(String(255), nullable=True)
    regrid_year_built = Column(String(10), nullable=True)
    regrid_area_acres = Column(Numeric(10, 4), nullable=True)
    regrid_num_units = Column(Numeric(6, 0), nullable=True)  # Number of living units
    regrid_num_stories = Column(Numeric(4, 1), nullable=True)
    regrid_struct_style = Column(String(100), nullable=True)
    regrid_fetched_at = Column(DateTime(timezone=True), nullable=True)
    
    # LBCS Standardized Land Use Codes (Premium tier)
    # These provide reliable, standardized classification across all counties
    lbcs_activity = Column(Numeric(5, 0), nullable=True)  # 1000=residential, 2000=commercial
    lbcs_activity_desc = Column(String(255), nullable=True)
    lbcs_function = Column(Numeric(5, 0), nullable=True)  # Economic function
    lbcs_function_desc = Column(String(255), nullable=True)
    lbcs_structure = Column(Numeric(5, 0), nullable=True)  # 1200-1299=multifamily w/ unit count
    lbcs_structure_desc = Column(String(255), nullable=True)
    lbcs_site = Column(Numeric(5, 0), nullable=True)
    lbcs_site_desc = Column(String(255), nullable=True)
    lbcs_ownership = Column(Numeric(5, 0), nullable=True)  # 1000=private, 4000=public
    lbcs_ownership_desc = Column(String(255), nullable=True)
    
    # Property classification (derived from LBCS or text matching)
    property_category = Column(String(50), nullable=True)  # multi_family, retail, office, etc.
    
    # Area measurements
    area_sqft = Column(Numeric(12, 2), nullable=True)
    area_m2 = Column(Numeric(12, 2), nullable=True)
    
    # Satellite Imagery
    satellite_image_base64 = Column(Text, nullable=True)
    satellite_zoom_level = Column(String(10), nullable=True)
    satellite_fetched_at = Column(DateTime(timezone=True), nullable=True)
    
    # VLM Analysis Results
    paved_percentage = Column(Numeric(5, 2), nullable=True)
    building_percentage = Column(Numeric(5, 2), nullable=True)
    landscaping_percentage = Column(Numeric(5, 2), nullable=True)
    asphalt_condition_score = Column(Numeric(3, 1), nullable=True)  # 1-10 scale
    analysis_notes = Column(Text, nullable=True)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Lead Scoring
    lead_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    lead_quality = Column(String(20), nullable=True)  # premium, high, standard, low
    
    # Lead Enrichment - Decision Maker Contact
    contact_name = Column(String(255), nullable=True)
    contact_first_name = Column(String(100), nullable=True)
    contact_last_name = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_title = Column(String(255), nullable=True)
    contact_linkedin_url = Column(Text, nullable=True)
    contact_company = Column(String(255), nullable=True)  # Management company name
    contact_company_website = Column(Text, nullable=True)  # Management company website
    enriched_at = Column(DateTime(timezone=True), nullable=True)
    enrichment_source = Column(String(50), nullable=True)  # "apollo", "website_scrape", "google_places"
    enrichment_status = Column(String(20), nullable=True)  # "success", "not_found", "error"
    enrichment_steps = Column(JSONB, nullable=True)  # LLM enrichment process steps for UI visualization
    
    # Discovery metadata
    discovery_source = Column(String(50), nullable=True)  # business_first, regrid_first
    business_type_tier = Column(String(20), nullable=True)  # premium, high, standard
    
    # Status
    status = Column(String(50), default='discovered', nullable=True)
    status_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    businesses = relationship(
        "PropertyBusiness",
        back_populates="property",
        cascade="all, delete-orphan"
    )
    deals = relationship("Deal", back_populates="property", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_properties_centroid', centroid, postgresql_using='gist'),
        Index('idx_properties_regrid_polygon', regrid_polygon, postgresql_using='gist'),
        Index('idx_properties_status', status),
        Index('idx_properties_lead_score', lead_score),
    )

