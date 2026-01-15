import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import UUID
from enum import Enum
from sqlalchemy.orm import Session
from shapely.geometry import shape
from geoalchemy2.shape import to_shape, from_shape

from app.models.property import Property
from app.models.business import Business
from app.models.property_business import PropertyBusiness
from app.schemas.discovery import DiscoveryStep, DiscoveryProgress, DiscoveryFilters
from app.core.business_data_service import business_data_service
from app.core.usage_tracking_service import usage_tracking_service
from app.core.business_first_discovery_service import (
    business_first_discovery_service,
    BusinessTier,
    DiscoveredBusiness,
)
from app.core.apollo_enrichment_service import apollo_enrichment_service, ContactSearchResult
from app.core.lead_enrichment_service import lead_enrichment_service
from app.core.llm_enrichment_service import llm_enrichment_service
from app.core.config import settings

# Clean property imagery pipeline
from app.core.property_imagery_pipeline import property_imagery_pipeline
from app.core.regrid_service import regrid_service
from app.core.vlm_analysis_service import vlm_analysis_service
import os
import math


class DiscoveryMode(str, Enum):
    """Discovery pipeline mode."""
    BUSINESS_FIRST = "business_first"  # Find businesses via Google Places → analyze property with Regrid + VLM
    CONTACT_FIRST = "contact_first"  # Find contacts via Apollo → find their properties via Regrid → VLM
    REGRID_FIRST = "regrid_first"  # Query Regrid directly by LBCS codes → VLM scoring → Enrichment

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class DiscoveryOrchestrator:
    """Orchestrates the complete parking lot discovery pipeline."""
    
    # In-memory job storage (use Redis in production)
    _jobs: Dict[str, Dict[str, Any]] = {}
    
    def initialize_job(self, job_id: UUID, user_id: UUID) -> None:
        """Initialize job status before starting background task."""
        job_key = str(job_id)
        self._jobs[job_key] = {
            "status": DiscoveryStep.QUEUED,
            "progress": DiscoveryProgress(
                current_step=DiscoveryStep.QUEUED,
                steps_completed=0,
            ),
            "started_at": datetime.utcnow(),
            "user_id": str(user_id),
        }
    
    async def start_discovery(
        self,
        job_id: UUID,
        user_id: UUID,
        area_polygon: Dict[str, Any],
        filters: DiscoveryFilters,
        db: Session,
        mode: DiscoveryMode = DiscoveryMode.BUSINESS_FIRST,
        tiers: Optional[List[str]] = None,
        business_type_ids: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
        # Contact-first mode parameters
        city: Optional[str] = None,
        state: Optional[str] = None,
        job_titles: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        # Regrid-first mode parameters
        property_categories: Optional[List[str]] = None,
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
    ) -> None:
        """
        Start the discovery pipeline.
        This runs as a background task.
        
        Args:
            job_id: Unique job identifier
            user_id: User running the job
            area_polygon: GeoJSON polygon defining search area
            filters: Discovery filters (max_lots, etc.)
            db: Database session
            mode: Discovery mode (business_first, contact_first, or regrid_first)
            tiers: List of tiers to search ("premium", "high", "standard")
            business_type_ids: Specific business type IDs to search
            scoring_prompt: User's criteria for VLM lead scoring
            city: City for contact search (contact_first mode)
            state: State code for contact search (contact_first mode)
            job_titles: Job titles to search in Apollo (contact_first mode)
            industries: Industries to filter (contact_first mode)
            property_categories: Property categories for Regrid query (regrid_first mode)
            min_acres: Minimum parcel size in acres (regrid_first mode)
            max_acres: Maximum parcel size in acres (regrid_first mode)
        """
        job_key = str(job_id)
        
        # Ensure job is initialized (might already be done by initialize_job)
        if job_key not in self._jobs:
            self.initialize_job(job_id, user_id)
        
        self._jobs[job_key]["mode"] = mode.value
        self._jobs[job_key]["tiers"] = tiers
        self._jobs[job_key]["business_type_ids"] = business_type_ids
        self._jobs[job_key]["scoring_prompt"] = scoring_prompt
        
        try:
            if mode == DiscoveryMode.CONTACT_FIRST:
                await self._run_contact_first_pipeline(
                    job_id, user_id, filters, db,
                    city=city,
                    state=state,
                    job_titles=job_titles,
                    industries=industries,
                    scoring_prompt=scoring_prompt,
                )
            elif mode == DiscoveryMode.REGRID_FIRST:
                await self._run_regrid_first_pipeline(
                    job_id, user_id, area_polygon, filters, db,
                    property_categories=property_categories,
                    scoring_prompt=scoring_prompt,
                    min_acres=min_acres,
                    max_acres=max_acres,
                )
            else:
                await self._run_business_first_pipeline(
                    job_id, user_id, area_polygon, filters, db,
                    tiers=tiers,
                    business_type_ids=business_type_ids,
                    scoring_prompt=scoring_prompt,
                )
        except Exception as e:
            logger.error(f"❌ Discovery pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            self._update_job(job_key, DiscoveryStep.FAILED, error=str(e))
    
    async def stream_discovery(
        self,
        job_id: UUID,
        user_id: UUID,
        area_polygon: Dict[str, Any],
        filters: DiscoveryFilters,
        db: Session,
        mode: DiscoveryMode = DiscoveryMode.BUSINESS_FIRST,
        tiers: Optional[List[str]] = None,
        business_type_ids: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        job_titles: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        property_categories: Optional[List[str]] = None,
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
    ):
        """
        Stream discovery progress via async generator.
        Yields user-friendly progress messages as the discovery runs.
        """
        job_key = str(job_id)
        self.initialize_job(job_id, user_id)
        
        try:
            if mode == DiscoveryMode.REGRID_FIRST:
                async for progress in self._stream_regrid_first_pipeline(
                    job_id, user_id, area_polygon, filters, db,
                    property_categories=property_categories,
                    scoring_prompt=scoring_prompt,
                    min_acres=min_acres,
                    max_acres=max_acres,
                ):
                    yield progress
            elif mode == DiscoveryMode.CONTACT_FIRST:
                # Fallback to non-streaming for now
                yield {"type": "started", "message": "Starting contact-first discovery..."}
                await self._run_contact_first_pipeline(
                    job_id, user_id, filters, db,
                    city=city, state=state, job_titles=job_titles, industries=industries,
                    scoring_prompt=scoring_prompt,
                )
                yield {"type": "complete", "message": "Discovery complete!"}
            else:
                # Fallback to non-streaming for business-first
                yield {"type": "started", "message": "Starting business-first discovery..."}
                await self._run_business_first_pipeline(
                    job_id, user_id, area_polygon, filters, db,
                    tiers=tiers, business_type_ids=business_type_ids, scoring_prompt=scoring_prompt,
                )
                yield {"type": "complete", "message": "Discovery complete!"}
        except Exception as e:
            logger.error(f"Discovery pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            self._update_job(job_key, DiscoveryStep.FAILED, error=str(e))
            yield {"type": "error", "message": f"Discovery failed: {str(e)}"}
    
    async def _stream_regrid_first_pipeline(
        self,
        job_id: UUID,
        user_id: UUID,
        area_polygon: Dict[str, Any],
        filters: DiscoveryFilters,
        db: Session,
        property_categories: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
    ):
        """
        Streaming version of Regrid-First Discovery Pipeline.
        Yields progress messages for real-time UI updates.
        """
        from app.schemas.discovery import PROPERTY_CATEGORY_LBCS_RANGES, PropertyCategoryEnum, PROPERTY_CATEGORY_LBCS_CONFIG
        from app.core.property_classifier import classify_property, PropertyCategory
        
        job_key = str(job_id)
        start_time = datetime.utcnow()
        
        # Format category names for display
        category_display = ", ".join([c.replace("_", " ").title() for c in (property_categories or ["multi_family"])])
        
        msg = {
            "type": "started",
            "message": f"Starting property discovery...",
            "details": f"Searching for {category_display} properties"
        }
        logger.info(f"[Stream] Sending: {msg['type']} - {msg['message']}")
        yield msg
        await asyncio.sleep(0.1)  # Allow event to be sent
        
        # ============ Step 1: Build LBCS queries ============
        yield {
            "type": "searching",
            "message": f"Analyzing {category_display} classification codes..."
        }
        await asyncio.sleep(0.1)
        
        if not property_categories:
            property_categories = [PropertyCategoryEnum.MULTI_FAMILY.value]
        
        lbcs_queries = {}
        for cat_str in property_categories:
            try:
                cat = PropertyCategoryEnum(cat_str)
                config = PROPERTY_CATEGORY_LBCS_CONFIG.get(cat, {})
                field = config.get("field", "lbcs_structure")
                ranges = config.get("ranges", [])
                if field not in lbcs_queries:
                    lbcs_queries[field] = []
                lbcs_queries[field].extend(ranges)
            except ValueError:
                pass
        
        lbcs_ranges = []
        for ranges in lbcs_queries.values():
            lbcs_ranges.extend(ranges)
        
        if not lbcs_ranges:
            yield {"type": "error", "message": "No valid property categories"}
            self._update_job(job_key, DiscoveryStep.FAILED, error="No valid property categories")
            return
        
        # Extract geographic filters
        zip_code = None
        state_code = None
        county_fips = None
        location_desc = "selected area"
        
        if area_polygon and area_polygon.get("properties"):
            props = area_polygon["properties"]
            zip_code = props.get("zip_code")
            state_code = props.get("state")
            county_fips = props.get("county_fips")
            if zip_code:
                location_desc = f"ZIP {zip_code}"
            elif state_code:
                location_desc = state_code
        
        # ============ Step 2: Query Regrid with Pagination ============
        msg = {
            "type": "searching",
            "message": f"Searching property records in {location_desc}...",
            "details": "Querying Regrid database"
        }
        logger.info(f"[Stream] Sending: {msg['type']} - {msg['message']}")
        yield msg
        await asyncio.sleep(0.1)
        
        self._update_job(job_key, DiscoveryStep.QUERYING_REGRID)
        
        # Get existing parcel IDs to filter out
        existing_regrid_ids = set(
            row[0] for row in db.query(Property.regrid_id).filter(
                Property.user_id == user_id,
                Property.regrid_id.isnot(None)
            ).all()
        )
        
        # Pagination loop - keep fetching until we have enough NEW parcels
        batch_size = max(filters.max_lots * 2, 20)  # Fetch more per batch
        max_pages = 10  # Safety limit to prevent infinite loops
        current_offset = 0
        new_parcels = []
        seen_parcel_ids = set()
        total_fetched = 0
        total_skipped = 0
        exhausted_regrid = False
        
        for page in range(max_pages):
            if len(new_parcels) >= filters.max_lots:
                break
            
            # Fetch next batch from each LBCS field
            batch_parcels = []
            for lbcs_field, ranges in lbcs_queries.items():
                if len(batch_parcels) >= batch_size:
                    break
                
                field_parcels = await regrid_service.search_parcels_by_lbcs(
                    lbcs_ranges=ranges,
                    county_fips=county_fips,
                    state_code=state_code,
                    zip_code=zip_code,
                    max_results=batch_size,
                    lbcs_field=lbcs_field,
                    min_acres=min_acres,
                    max_acres=max_acres,
                    offset=current_offset,
                )
                
                for parcel in field_parcels:
                    if parcel.parcel_id not in seen_parcel_ids:
                        seen_parcel_ids.add(parcel.parcel_id)
                        batch_parcels.append(parcel)
            
            if not batch_parcels:
                # No more results from Regrid
                exhausted_regrid = True
                logger.info(f"[Stream] Regrid exhausted after {total_fetched} parcels")
                break
            
            total_fetched += len(batch_parcels)
            
            # Filter out existing parcels
            for parcel in batch_parcels:
                if parcel.parcel_id not in existing_regrid_ids:
                    new_parcels.append(parcel)
                    if len(new_parcels) >= filters.max_lots:
                        break
                else:
                    total_skipped += 1
            
            # Update progress
            if total_skipped > 0 and page > 0:
                yield {
                    "type": "searching",
                    "message": f"Fetching more records... ({total_skipped} already processed)",
                    "details": f"Found {len(new_parcels)} new so far"
                }
                await asyncio.sleep(0.1)
            
            # Move to next page
            current_offset += batch_size
            
            logger.info(f"[Stream] Page {page+1}: fetched {len(batch_parcels)}, new={len(new_parcels)}, skipped={total_skipped}")
        
        # Fallback to usedesc search if no LBCS results
        if not new_parcels and total_fetched == 0:
            yield {
                "type": "searching",
                "message": "No LBCS matches, trying alternative search..."
            }
            await asyncio.sleep(0.1)
            
            usedesc_patterns = []
            for cat_str in property_categories:
                if cat_str == "multi_family":
                    usedesc_patterns.extend(["apartment", "multi-family", "condo"])
                elif cat_str == "retail":
                    usedesc_patterns.extend(["retail", "shopping"])
                elif cat_str == "office":
                    usedesc_patterns.extend(["office"])
                elif cat_str == "industrial":
                    usedesc_patterns.extend(["warehouse", "industrial"])
            
            if usedesc_patterns:
                fallback_parcels = await regrid_service.search_parcels_by_usedesc(
                    patterns=usedesc_patterns,
                    county_fips=county_fips,
                    state_code=state_code,
                    zip_code=zip_code,
                    max_results=filters.max_lots * 2,
                )
                # Filter fallback results too
                for parcel in fallback_parcels:
                    if parcel.parcel_id not in existing_regrid_ids:
                        new_parcels.append(parcel)
                        if len(new_parcels) >= filters.max_lots:
                            break
        
        # Check final results
        if not new_parcels:
            if total_fetched > 0:
                # We found parcels but all were already processed
                msg = {
                    "type": "complete",
                    "message": f"All {total_fetched} matching properties already processed",
                    "stats": {"found": total_fetched, "new": 0, "skipped": total_skipped}
                }
            else:
                msg = {
                    "type": "complete",
                    "message": "No properties found matching criteria",
                    "stats": {"found": 0, "processed": 0, "enriched": 0}
                }
            logger.info(f"[Stream] Sending: {msg['type']} - {msg['message']}")
            yield msg
            self._update_job(job_key, DiscoveryStep.COMPLETED)
            return
        
        # Trim to max_lots if we got more
        if len(new_parcels) > filters.max_lots:
            new_parcels = new_parcels[:filters.max_lots]
        
        msg = {
            "type": "found",
            "message": f"Found {len(new_parcels)} new properties",
            "details": f"{total_skipped} already in database" if total_skipped > 0 else None,
            "total": len(new_parcels)
        }
        logger.info(f"[Stream] Sending: {msg['type']} - {msg['message']}")
        yield msg
        await asyncio.sleep(0.1)
        
        self._jobs[job_key]["progress"].properties_found = len(new_parcels)
        
        # ============ Step 3: Process each parcel ============
        self._update_job(job_key, DiscoveryStep.PROCESSING_PARCELS)
        
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        user_api_key = None
        if user and user.use_own_openrouter_key and user.openrouter_api_key:
            user_api_key = user.openrouter_api_key
        
        property_ids = []
        processed_count = 0
        analyzed_count = 0
        enriched_count = 0
        vlm_total_cost = 0.0
        
        for idx, parcel in enumerate(new_parcels):
            try:
                processed_count += 1
                short_address = (parcel.address or "Unknown")[:35]
                
                yield {
                    "type": "processing",
                    "message": f"Processing: {short_address}",
                    "current": idx + 1,
                    "total": len(new_parcels),
                    "address": parcel.address,
                    "owner": parcel.owner
                }
                await asyncio.sleep(0.05)
                
                centroid = parcel.centroid
                
                # Create property record
                db_property = Property(
                    user_id=user_id,
                    centroid=from_shape(centroid, srid=4326),
                    address=parcel.address,
                    discovery_source="regrid_first",
                    status="discovered",
                )
                db.add(db_property)
                db.flush()
                property_ids.append(db_property.id)
                
                # Store Regrid data
                db_property.regrid_id = parcel.parcel_id
                db_property.regrid_apn = parcel.apn
                db_property.regrid_owner = parcel.owner
                db_property.regrid_owner2 = parcel.owner2
                db_property.regrid_owner_type = parcel.owner_type
                db_property.regrid_owner_address = parcel.mail_address
                db_property.regrid_owner_city = parcel.mail_city
                db_property.regrid_owner_state = parcel.mail_state
                db_property.regrid_land_use = parcel.land_use
                db_property.regrid_zoning = parcel.zoning
                db_property.regrid_zoning_desc = parcel.zoning_description
                db_property.regrid_year_built = str(parcel.year_built) if parcel.year_built else None
                db_property.regrid_area_acres = parcel.area_acres
                db_property.regrid_num_units = parcel.num_units
                db_property.regrid_num_stories = parcel.num_stories
                db_property.regrid_struct_style = parcel.struct_style
                db_property.lbcs_structure = parcel.lbcs_structure
                db_property.lbcs_structure_desc = parcel.lbcs_structure_desc
                db_property.lbcs_activity = parcel.lbcs_activity
                db_property.lbcs_function = parcel.lbcs_function
                db_property.lbcs_ownership = parcel.lbcs_ownership
                db_property.lbcs_site = parcel.lbcs_site
                
                # Classify property
                classification = classify_property(
                    usecode=parcel.land_use or "",
                    usedesc=parcel.land_use or "",  # land_use contains usedesc
                    zoning=parcel.zoning or "",
                    lbcs_structure=parcel.lbcs_structure,
                    lbcs_activity=parcel.lbcs_activity,
                )
                db_property.property_category = classification.value
                
                # Store polygon if available
                if parcel.polygon:
                    try:
                        db_property.regrid_polygon = from_shape(parcel.polygon, srid=4326)
                    except Exception:
                        pass
                
                # Fetch satellite imagery
                yield {
                    "type": "imagery",
                    "message": "Capturing satellite view...",
                    "current": idx + 1,
                    "total": len(new_parcels)
                }
                await asyncio.sleep(0.05)
                
                try:
                    imagery_result = await property_imagery_pipeline.get_property_image(
                        lat=centroid.y,
                        lng=centroid.x,
                        address=parcel.address,
                    )
                    
                    if imagery_result and imagery_result.success:
                        # Access metadata dict for zoom and area
                        metadata = imagery_result.metadata or {}
                        db_property.satellite_zoom_level = metadata.get("zoom_level", 20)
                        db_property.satellite_area_m2 = metadata.get("area_m2")
                        
                        # Run VLM analysis
                        yield {
                            "type": "analyzing",
                            "message": "AI analyzing property...",
                            "current": idx + 1,
                            "total": len(new_parcels)
                        }
                        await asyncio.sleep(0.05)
                        
                        image_base64 = imagery_result.image_base64
                        if image_base64:
                            property_context = {
                                "address": parcel.address,
                                "area_sqft": (parcel.area_acres or 0) * 43560,
                                "property_type": classification.value,
                                "owner": parcel.owner,
                            }
                            
                            vlm_result = await vlm_analysis_service.analyze_property(
                                image_base64=image_base64,
                                property_context=property_context,
                                scoring_prompt=scoring_prompt,
                                user_api_key=user_api_key,
                            )
                            
                            if vlm_result and vlm_result.success:
                                db_property.lead_score = vlm_result.lead_score
                                db_property.lead_confidence = vlm_result.confidence
                                db_property.analysis_notes = vlm_result.reasoning
                                db_property.lead_quality = (
                                    'high' if vlm_result.lead_score >= 70
                                    else 'medium' if vlm_result.lead_score >= 40
                                    else 'low'
                                )
                                db_property.analyzed_at = datetime.utcnow()
                                db_property.status = "analyzed"
                                if vlm_result.usage:
                                    vlm_total_cost += vlm_result.usage.cost
                                analyzed_count += 1
                                
                                score = vlm_result.lead_score or 0
                                score_label = "High" if score >= 70 else "Medium" if score >= 40 else "Low"
                                
                                yield {
                                    "type": "scoring",
                                    "message": f"Lead score: {score}/100 ({score_label})",
                                    "score": score,
                                    "current": idx + 1,
                                    "total": len(new_parcels)
                                }
                                await asyncio.sleep(0.05)
                                
                                # Enrichment
                                yield {
                                    "type": "enriching",
                                    "message": "Finding property manager...",
                                    "current": idx + 1,
                                    "total": len(new_parcels)
                                }
                                await asyncio.sleep(0.05)
                                
                                try:
                                    enrichment_result = await llm_enrichment_service.enrich(
                                        address=parcel.address or "",
                                        property_type=classification.value,
                                        owner_name=parcel.owner,
                                        lbcs_code=int(parcel.lbcs_structure) if parcel.lbcs_structure else None,
                                    )
                                    
                                    # Store enrichment steps
                                    import json
                                    if enrichment_result.detailed_steps:
                                        db_property.enrichment_steps = json.dumps([
                                            step.to_dict() for step in enrichment_result.detailed_steps
                                        ])
                                    
                                    if enrichment_result.success and enrichment_result.contact:
                                        contact = enrichment_result.contact
                                        db_property.contact_name = contact.name
                                        db_property.contact_first_name = contact.first_name
                                        db_property.contact_last_name = contact.last_name
                                        db_property.contact_email = contact.email
                                        db_property.contact_phone = contact.phone
                                        db_property.contact_title = contact.title
                                        db_property.contact_company = enrichment_result.management_company
                                        db_property.contact_company_website = enrichment_result.management_website
                                        db_property.enrichment_source = "llm_enrichment"
                                        db_property.enrichment_status = "success"
                                        db_property.enriched_at = datetime.utcnow()
                                        enriched_count += 1
                                        
                                        phone_display = contact.phone[:15] + "..." if contact.phone and len(contact.phone) > 15 else contact.phone
                                        contact_msg = f"Contact found: {phone_display or contact.email or enrichment_result.management_company}"
                                        logger.info(f"[Stream] Sending: contact_found - {contact_msg}")
                                        yield {
                                            "type": "contact_found",
                                            "message": contact_msg,
                                            "phone": contact.phone,
                                            "email": contact.email,
                                            "company": enrichment_result.management_company,
                                            "current": idx + 1,
                                            "total": len(new_parcels)
                                        }
                                        await asyncio.sleep(0.05)
                                    else:
                                        db_property.enrichment_status = "not_found"
                                        logger.info(f"[Stream] Sending: progress - No contact info found for {parcel.address}")
                                        yield {
                                            "type": "progress",
                                            "message": "No contact info found",
                                            "current": idx + 1,
                                            "total": len(new_parcels)
                                        }
                                        await asyncio.sleep(0.05)
                                        
                                except Exception as enrich_err:
                                    logger.warning(f"Enrichment error: {enrich_err}")
                                    db_property.enrichment_status = "error"
                                
                except Exception as img_err:
                    logger.warning(f"Imagery/VLM error: {img_err}")
                    db_property.status = "imagery_failed"
                
                db.commit()
                
            except Exception as e:
                logger.error(f"Error processing parcel: {e}")
                db.rollback()
                continue
        
        # ============ Complete ============
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        self._update_job(job_key, DiscoveryStep.COMPLETED)
        self._jobs[job_key]["progress"].parking_lots_found = processed_count
        self._jobs[job_key]["progress"].parking_lots_evaluated = analyzed_count
        self._jobs[job_key]["completed_at"] = datetime.utcnow()
        
        # Log usage
        usage_tracking_service.log_discovery_job(
            db=db,
            user_id=user_id,
            job_id=job_id,
            properties_found=processed_count,
            properties_with_imagery=analyzed_count,
            properties_analyzed=analyzed_count,
            businesses_loaded=0,
            vlm_total_cost=vlm_total_cost,
        )
        
        complete_msg = {
            "type": "complete",
            "message": "Discovery complete!",
            "stats": {
                "found": processed_count,
                "analyzed": analyzed_count,
                "enriched": enriched_count,
                "duration": f"{duration:.1f}s",
                "cost": f"${vlm_total_cost:.4f}"
            }
        }
        logger.info(f"[Stream] Sending: complete - {processed_count} found, {analyzed_count} analyzed, {enriched_count} enriched")
        yield complete_msg
    
    async def _run_business_first_pipeline(
        self,
        job_id: UUID,
        user_id: UUID,
        area_polygon: Dict[str, Any],
        filters: DiscoveryFilters,
        db: Session,
        tiers: Optional[List[str]] = None,
        business_type_ids: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
    ) -> None:
        """
        Run the business-first discovery pipeline.
        
        1. Find businesses by type (HOA, apartments, etc.)
        2. Find parking lots near each business
        3. Fetch imagery and evaluate condition
        4. Run VLM analysis to score leads
        5. Create leads with business + parking lot + score
        
        Args:
            tiers: List of tier strings to search ("premium", "high", "standard")
            business_type_ids: Specific business type IDs to search
            scoring_prompt: User's criteria for VLM lead scoring
        """
        job_key = str(job_id)
        start_time = datetime.utcnow()
        
        # Get user to check for their own API key
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        user_openrouter_key = None
        if user and user.use_own_openrouter_key and user.openrouter_api_key:
            user_openrouter_key = user.openrouter_api_key
            logger.info("   Using user's own OpenRouter API key")
        
        # Convert tier strings to BusinessTier enums
        tier_enums = None
        if tiers:
            tier_enums = []
            for t in tiers:
                if t == "premium":
                    tier_enums.append(BusinessTier.PREMIUM)
                elif t == "high":
                    tier_enums.append(BusinessTier.HIGH)
                elif t == "standard":
                    tier_enums.append(BusinessTier.STANDARD)
        
        tier_desc = ", ".join(tiers) if tiers else "all"
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"🚀 BUSINESS-FIRST DISCOVERY PIPELINE STARTED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Max results: {filters.max_lots}")
        logger.info(f"   Tiers: {tier_desc}")
        if business_type_ids:
            logger.info(f"   Business types: {', '.join(business_type_ids)}")
        logger.info("=" * 60)
        
        # Get polygon centroid and bounds
        poly = shape(area_polygon)
        centroid = poly.centroid
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        
        # Calculate search radius from bounds
        lat_range = bounds[3] - bounds[1]
        lng_range = bounds[2] - bounds[0]
        radius_meters = int(max(lat_range, lng_range) * 111000 / 2 * 1.2)
        radius_meters = min(radius_meters, 50000)  # Cap at 50km
        
        # ============ Step 1: Discover businesses by type ============
        logger.info("")
        logger.info("🏢 STEP 1: Discovering businesses by type...")
        self._update_job(job_key, DiscoveryStep.LOADING_BUSINESSES)
        
        # SMART FETCHING: Keep fetching until we have enough NEW businesses
        # Google Places allows up to 60 results per query (3 pages x 20 each)
        # If no new businesses found, expand the search radius
        max_fetch_attempts = 3
        max_radius_expansions = 3  # How many times to expand radius
        fetch_batch_size = max(30, filters.max_lots * 3)  # Fetch 3x what we need per batch
        
        discovered_businesses = []
        total_skipped = 0
        all_seen_place_ids = set()
        current_radius = radius_meters
        
        for radius_expansion in range(max_radius_expansions + 1):
            if len(discovered_businesses) >= filters.max_lots:
                break
            
            if radius_expansion > 0:
                # Expand radius by 50% each time
                current_radius = int(current_radius * 1.5)
                current_radius = min(current_radius, 50000)  # Cap at 50km
                logger.info(f"   🔄 Expanding search radius to {current_radius/1000:.1f}km")
            
            found_new_in_radius = False
            
            for attempt in range(max_fetch_attempts):
                if len(discovered_businesses) >= filters.max_lots:
                    break
                
                # Fetch a batch of businesses
                batch = await business_first_discovery_service.discover_businesses(
            center_lat=centroid.y,
            center_lng=centroid.x,
                    radius_meters=current_radius,
            tiers=tier_enums,
            business_type_ids=business_type_ids,
                    max_per_tier=max(20, fetch_batch_size // 2),  # More per tier for pagination
                    max_total=fetch_batch_size,
                )
                
                # Check for new businesses we haven't seen in this session
                new_in_batch = [b for b in batch if b.places_id not in all_seen_place_ids]
                for b in new_in_batch:
                    all_seen_place_ids.add(b.places_id)
                
                if not new_in_batch:
                    logger.info(f"   📭 No more businesses in area (radius: {current_radius/1000:.1f}km)")
                    break
                
                # Check which ones are already processed in DB
                already_processed = self._get_already_processed_places_ids(
                    places_ids=[b.places_id for b in new_in_batch],
                    db=db,
                )
                
                # Separate new vs already processed
                new_businesses = [b for b in new_in_batch if b.places_id not in already_processed]
                batch_skipped = len(new_in_batch) - len(new_businesses)
                total_skipped += batch_skipped
                
                # Add new businesses to our result list
                for business in new_businesses:
                    if len(discovered_businesses) >= filters.max_lots:
                        break
                    discovered_businesses.append(business)
                    found_new_in_radius = True
                
                logger.info(f"   📥 Batch {attempt + 1}: {len(new_in_batch)} found, {len(new_businesses)} new, {batch_skipped} skipped")
                
                # If we got less than expected, we've likely exhausted results at this radius
                if len(new_in_batch) < fetch_batch_size // 2:
                    break
            
            # If we found new businesses at this radius, don't expand further unless needed
            if found_new_in_radius and len(discovered_businesses) >= filters.max_lots:
                break
            
            # If no new businesses found at current radius, try expanding
            if not found_new_in_radius and radius_expansion < max_radius_expansions:
                continue
            elif not found_new_in_radius:
                logger.info(f"   ⚠️ No new businesses found even after expanding radius to {current_radius/1000:.1f}km")
        
        skipped_count = total_skipped
        
        if skipped_count > 0:
            logger.info(f"   ♻️  Total skipped (already processed): {skipped_count}")
        
        # Count by tier
        premium_count = len([b for b in discovered_businesses if b.tier == BusinessTier.PREMIUM])
        high_count = len([b for b in discovered_businesses if b.tier == BusinessTier.HIGH])
        standard_count = len([b for b in discovered_businesses if b.tier == BusinessTier.STANDARD])
        
        logger.info(f"   ✅ Found {len(discovered_businesses)} NEW businesses to process:")
        logger.info(f"      🏆 Premium (Apartments/Condos): {premium_count}")
        logger.info(f"      ⭐ High (Shopping/Hotels): {high_count}")
        logger.info(f"      📍 Standard (Other): {standard_count}")
        if skipped_count > 0:
            logger.info(f"      ♻️  Already processed (skipped): {skipped_count}")
        
        self._jobs[job_key]["progress"].businesses_loaded = len(discovered_businesses)
        self._jobs[job_key]["progress"].businesses_skipped = skipped_count
        
        if not discovered_businesses:
            if skipped_count > 0:
                logger.warning(f"   ⚠️  All {skipped_count} businesses in this area already processed")
                logger.info(f"   💡 Tip: Try a different area or expand the search radius")
            else:
                logger.warning("   ⚠️  No businesses found in area")
            self._update_job(job_key, DiscoveryStep.COMPLETED)
            return
        
        # ============ Step 2: Find parking lots for each business ============
        logger.info("")
        logger.info("🅿️  STEP 2: Finding parking lots for each business...")
        self._update_job(job_key, DiscoveryStep.COLLECTING_PARKING_LOTS)
        
        processed_count = 0
        evaluated_count = 0
        vlm_analyzed_count = 0
        vlm_total_cost = 0.0  # Actual cost from OpenRouter
        parking_lot_ids: List[UUID] = []
        
        for idx, business in enumerate(discovered_businesses):
            try:
                logger.info(f"   [{idx+1}/{len(discovered_businesses)}] {business.name} ({business.tier.value})")
                
                # Save business to database
                existing_business = db.query(Business).filter(
                    Business.places_id == business.places_id
                ).first()
                
                if existing_business:
                    db_business = existing_business
                    # Update contact info if we have new data
                    if business.phone and not existing_business.phone:
                        existing_business.phone = business.phone
                    if business.website and not existing_business.website:
                        existing_business.website = business.website
                else:
                    db_business = Business(
                        user_id=user_id,
                        places_id=business.places_id,
                        name=business.name,
                        address=business.address,
                        phone=business.phone,
                        website=business.website,
                        category=business.business_type,
                        business_type=business.tier.value,
                        location=from_shape(business.location, srid=4326),
                        raw_data=business.raw_data,
                    )
                    db.add(db_business)
                    db.flush()
                
                # Check if parking lot already exists for this business
                existing_lot = None
                if existing_business:
                    # Check for existing parking lot via association
                    existing_assoc = db.query(PropertyBusiness).filter(
                        PropertyBusiness.business_id == db_business.id,
                        PropertyBusiness.is_primary == True
                    ).first()
                    if existing_assoc:
                        existing_lot = db.query(Property).filter(
                            Property.id == existing_assoc.parking_lot_id
                        ).first()
                
                if existing_lot:
                    # Use existing parking lot, skip re-analysis
                    db_property = existing_lot
                    logger.info(f"      ♻️  Using existing parking lot (already analyzed)")
                    parking_lot_ids.append(db_property.id)
                    
                    # Skip to next business if already evaluated
                    if db_property.status == "analyzed":
                        logger.info(f"      ✅ Already evaluated, skipping")
                        continue
                else:
                    # Create placeholder parking lot (actual area will come from SAM analysis)
                    from shapely.geometry import Point
                    business_point = Point(business.longitude, business.latitude)
                    
                    db_property = Property(
                        user_id=user_id,
                        centroid=from_shape(business_point, srid=4326),
                        address=business.address,
                        business_type_tier=business.tier.value,
                        discovery_source="business_first",
                        status="discovered",
                    )
                    db.add(db_property)
                    db.flush()
                    
                    parking_lot_ids.append(db_property.id)
                    
                    # Create association
                    association = PropertyBusiness(
                        property_id=db_property.id,
                        business_id=db_business.id,
                        match_score=95.0,  # High score since we found business first
                        distance_meters=0,  # Property is for this business
                        is_primary=True,
                        relationship_type="tenant",
                    )
                    db.add(association)
                    db.flush()
                
                processed_count += 1
                
                # ============ Step 1: Get Property Boundary from Regrid ============
                # Use ADDRESS-based lookup (more accurate than point lookup)
                logger.info(f"      🗺️  Fetching property boundary from Regrid by ADDRESS...")
                
                property_boundary = None
                regrid_parcel = None
                
                try:
                    # Use validated parcel lookup (point-in-polygon validation)
                    regrid_parcel = await regrid_service.get_validated_parcel(
                        lat=business.latitude,
                        lng=business.longitude,
                        address=business.address
                    )
                    
                    if regrid_parcel and regrid_parcel.has_valid_geometry:
                        property_boundary = regrid_parcel.polygon
                        logger.info(f"      ✅ Got Regrid boundary: {regrid_parcel.area_m2:,.0f} m²")
                        logger.info(f"         Owner: {regrid_parcel.owner}")
                        logger.info(f"         Regrid Address: {regrid_parcel.address}")
                        logger.info(f"         Business Address: {business.address[:50]}...")
                    else:
                        logger.warning(f"      ❌ No Regrid parcel found - SKIPPING (need exact boundary)")
                except Exception as e:
                    logger.warning(f"      ❌ Regrid lookup failed: {e} - SKIPPING")
                
                # ============ Step 2: REQUIRE Regrid Boundary ============
                # Without exact property boundary, we can't accurately detect private asphalt
                if not property_boundary:
                    logger.warning(f"      ⏭️  Skipping {business.name} - no Regrid coverage in this area")
                    # Mark as skipped but keep in DB for potential future analysis
                    db_property.status = "skipped_no_boundary"
                    db_property.status_error = "Regrid has no parcel data for this location"
                    db.commit()
                    continue
                
                # ============ Step 3: Get Property Satellite Image ============
                logger.info(f"      🎯 Fetching property satellite imagery...")
                
                imagery_result = await property_imagery_pipeline.get_property_image(
                    lat=business.latitude,
                    lng=business.longitude,
                    address=business.address,
                    zoom=20,
                    draw_boundary=True,
                    save_debug=True,
                )
                
                if imagery_result.success:
                    # Store Regrid data directly on parking lot
                    if regrid_parcel:
                        db_property.regrid_id = regrid_parcel.parcel_id
                        db_property.regrid_apn = regrid_parcel.apn
                        db_property.regrid_owner = regrid_parcel.owner
                        db_property.regrid_owner2 = regrid_parcel.owner2
                        db_property.regrid_owner_type = regrid_parcel.owner_type
                        db_property.regrid_owner_address = regrid_parcel.mail_address
                        db_property.regrid_owner_city = regrid_parcel.mail_city
                        db_property.regrid_owner_state = regrid_parcel.mail_state
                        db_property.regrid_land_use = regrid_parcel.land_use
                        db_property.regrid_zoning = regrid_parcel.zoning
                        db_property.regrid_zoning_desc = regrid_parcel.zoning_description
                        db_property.regrid_year_built = str(regrid_parcel.year_built) if regrid_parcel.year_built else None
                        db_property.regrid_area_acres = regrid_parcel.area_acres
                        db_property.regrid_num_units = regrid_parcel.num_units
                        db_property.regrid_num_stories = regrid_parcel.num_stories
                        db_property.regrid_struct_style = regrid_parcel.struct_style
                        db_property.regrid_fetched_at = datetime.utcnow()
                        
                        # Store LBCS codes (Premium tier - standardized classification)
                        db_property.lbcs_activity = regrid_parcel.lbcs_activity
                        db_property.lbcs_activity_desc = regrid_parcel.lbcs_activity_desc
                        db_property.lbcs_function = regrid_parcel.lbcs_function
                        db_property.lbcs_function_desc = regrid_parcel.lbcs_function_desc
                        db_property.lbcs_structure = regrid_parcel.lbcs_structure
                        db_property.lbcs_structure_desc = regrid_parcel.lbcs_structure_desc
                        db_property.lbcs_site = regrid_parcel.lbcs_site
                        db_property.lbcs_site_desc = regrid_parcel.lbcs_site_desc
                        db_property.lbcs_ownership = regrid_parcel.lbcs_ownership
                        db_property.lbcs_ownership_desc = regrid_parcel.lbcs_ownership_desc
                        
                        # Log LBCS codes for debugging
                        if regrid_parcel.lbcs_structure:
                            logger.info(f"      🏷️  LBCS Structure: {regrid_parcel.lbcs_structure} ({regrid_parcel.lbcs_structure_desc or 'N/A'})")
                        if regrid_parcel.num_units:
                            logger.info(f"      🏢 Units: {regrid_parcel.num_units}")
                        
                        # Store polygon as Geography
                        if regrid_parcel.polygon:
                            db_property.regrid_polygon = from_shape(regrid_parcel.polygon, srid=4326)
                    
                    # Store satellite image (base64 for quick display)
                    db_property.satellite_image_base64 = imagery_result.image_base64
                    db_property.satellite_zoom_level = str(imagery_result.metadata.get('zoom', 20))
                    
                    # Update parking lot with property area
                    db_property.area_m2 = imagery_result.area_sqm
                    db_property.area_sqft = imagery_result.area_sqft
                    db_property.status = "imagery_captured"
                    db_property.satellite_fetched_at = datetime.utcnow()
                    
                    evaluated_count += 1
                    
                    logger.info(f"      ✅ Imagery captured: {imagery_result.image_size[0]}x{imagery_result.image_size[1]} px")
                    logger.info(f"         Property area: {imagery_result.area_sqft:,.0f} sqft")
                    logger.info(f"         Regrid owner: {regrid_parcel.owner if regrid_parcel else 'N/A'}")
                    logger.info(f"         Land use: {regrid_parcel.land_use if regrid_parcel else 'N/A'}")
                    
                    # ============ Step 4: VLM Analysis for Lead Scoring ============
                    logger.info(f"      🤖 Running VLM analysis for lead scoring...")
                    
                    vlm_result = await vlm_analysis_service.analyze_property(
                        image_base64=imagery_result.image_base64,
                        scoring_prompt=scoring_prompt,
                        property_context={
                            "address": business.address,
                            "owner": regrid_parcel.owner if regrid_parcel else None,
                            "land_use": regrid_parcel.land_use if regrid_parcel else None,
                            "area_acres": regrid_parcel.area_acres if regrid_parcel else None,
                            "business_name": business.name,
                            "business_type": business.tier.value,
                        },
                        user_api_key=user_openrouter_key,  # Use user's key if enabled
                    )
                    
                    if vlm_result.success:
                        # Store VLM results
                        db_property.lead_score = vlm_result.lead_score
                        db_property.lead_quality = (
                            'high' if vlm_result.lead_score >= 70 
                            else 'medium' if vlm_result.lead_score >= 40 
                            else 'low'
                        )
                        db_property.analysis_notes = vlm_result.reasoning
                        db_property.analyzed_at = datetime.utcnow()
                        db_property.status = "analyzed"
                        
                        # Store surface breakdown if available
                        if vlm_result.observations:
                            db_property.paved_percentage = vlm_result.observations.paved_area_pct
                            db_property.building_percentage = vlm_result.observations.building_pct
                            db_property.landscaping_percentage = vlm_result.observations.landscaping_pct
                            db_property.asphalt_condition_score = (
                                90 if vlm_result.observations.condition == 'critical' else
                                70 if vlm_result.observations.condition == 'poor' else
                                50 if vlm_result.observations.condition == 'fair' else
                                30 if vlm_result.observations.condition == 'good' else
                                10  # excellent
                            )
                        
                        vlm_analyzed_count += 1
                        if vlm_result.usage:
                            vlm_total_cost += vlm_result.usage.cost
                        logger.info(f"      🎯 VLM Score: {vlm_result.lead_score}/100 ({db_property.lead_quality})")
                        logger.info(f"         Confidence: {vlm_result.confidence}%")
                        logger.info(f"         Reasoning: {vlm_result.reasoning[:100]}...")
                        if vlm_result.observations:
                            logger.info(f"         Paved: {vlm_result.observations.paved_area_pct}% | Buildings: {vlm_result.observations.building_pct}%")
                            if vlm_result.observations.visible_issues:
                                logger.info(f"         Issues: {', '.join(vlm_result.observations.visible_issues[:3])}")
                        
                        # ============ Step 5: LLM-Powered Lead Enrichment ============
                        # Use LLM to intelligently find Property Manager contact data
                        logger.info(f"      📇 LLM-powered enrichment to find Property Manager...")
                        
                        # Determine property type from LBCS or business type
                        prop_type = business.tier.value
                        if regrid_parcel and regrid_parcel.lbcs_structure:
                            if 1200 <= regrid_parcel.lbcs_structure < 1300:
                                prop_type = "multi_family"
                            elif 2100 <= regrid_parcel.lbcs_structure < 2200:
                                prop_type = "office"
                            elif 2200 <= regrid_parcel.lbcs_structure < 2300:
                                prop_type = "retail"
                        
                        enrichment_result = await llm_enrichment_service.enrich(
                            address=business.address,
                            property_type=prop_type,
                            owner_name=regrid_parcel.owner if regrid_parcel else None,
                            lbcs_code=regrid_parcel.lbcs_structure if regrid_parcel else None,
                        )
                        
                        # Store enrichment steps for UI (always save detailed steps with URLs)
                        import json
                        if enrichment_result.detailed_steps:
                            # Store detailed steps as JSON (includes URL, source, confidence)
                            db_property.enrichment_steps = json.dumps([
                                step.to_dict() for step in enrichment_result.detailed_steps
                            ])
                            # Log simple flow for console
                            flow_parts = [step.to_simple_string() for step in enrichment_result.detailed_steps]
                            logger.info(f"         Flow: {' → '.join(flow_parts)}")
                        elif enrichment_result.steps:
                            # Fallback to simple steps if no detailed steps
                            db_property.enrichment_steps = json.dumps(enrichment_result.steps)
                            logger.info(f"         Flow: {' → '.join(enrichment_result.steps)}")
                        
                        if enrichment_result.success and enrichment_result.contact:
                            contact = enrichment_result.contact
                            db_property.contact_name = contact.name
                            db_property.contact_first_name = contact.first_name
                            db_property.contact_last_name = contact.last_name
                            db_property.contact_email = contact.email
                            db_property.contact_phone = contact.phone
                            db_property.contact_title = contact.title
                            db_property.contact_company = enrichment_result.management_company
                            db_property.contact_company_website = enrichment_result.management_website
                            db_property.enriched_at = datetime.utcnow()
                            db_property.enrichment_source = "llm_enrichment"
                            db_property.enrichment_status = "success"
                            
                            logger.info(f"      ✅ Contact found: {contact.name or contact.phone or contact.email}")
                            logger.info(f"         Confidence: {enrichment_result.confidence:.0%}")
                            if enrichment_result.management_company:
                                logger.info(f"         Company: {enrichment_result.management_company}")
                        else:
                            db_property.enrichment_status = "not_found"
                            if enrichment_result.error_message:
                                logger.info(f"      ⚠️ Enrichment: {enrichment_result.error_message}")
                    else:
                        logger.warning(f"      ⚠️ VLM analysis failed: {vlm_result.error_message}")
                else:
                    logger.warning(f"      ❌ Imagery failed: {imagery_result.error_message}")
                    db_property.status_error = imagery_result.error_message
                    db_property.status = "failed"
                
                db.commit()
                self._jobs[job_key]["progress"].parking_lots_evaluated = evaluated_count
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"      ❌ Error processing business: {e}")
                import traceback
                traceback.print_exc()
                db.rollback()
        
        self._jobs[job_key]["progress"].parking_lots_found = processed_count
        self._jobs[job_key]["progress"].associations_made = processed_count
        
        # ============ Step 4: Count high-value leads ============
        logger.info("")
        logger.info("🎯 STEP 4: Counting high-value leads...")
        self._update_job(job_key, DiscoveryStep.FILTERING)
        
        high_value_count = self._count_high_value_leads(parking_lot_ids, filters, db)
        self._jobs[job_key]["progress"].high_value_leads = high_value_count
        
        logger.info(f"   ✅ Found {high_value_count} high-value leads")
        
        # ============ Complete ============
        self._update_job(job_key, DiscoveryStep.COMPLETED)
        self._jobs[job_key]["completed_at"] = datetime.utcnow()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ BUSINESS-FIRST DISCOVERY COMPLETED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   Duration: {elapsed:.1f} seconds")
        logger.info(f"   Businesses processed: {len(discovered_businesses)} new")
        if skipped_count > 0:
            logger.info(f"   Businesses skipped: {skipped_count} (already processed)")
        logger.info(f"   Properties processed: {processed_count}")
        logger.info(f"   Properties with imagery: {evaluated_count}")
        logger.info(f"   Properties analyzed (VLM): {vlm_analyzed_count}")
        logger.info(f"   VLM total cost: ${vlm_total_cost:.4f}")
        logger.info(f"   High-value leads: {high_value_count}")
        
        # Count enriched leads
        enriched_count = db.query(Property).filter(
            Property.id.in_(parking_lot_ids),
            Property.enrichment_status == "success"
        ).count()
        logger.info(f"   Leads with contact data: {enriched_count}/{vlm_analyzed_count}")
        
        logger.info(f"   By tier:")
        logger.info(f"      🏆 Premium: {premium_count}")
        logger.info(f"      ⭐ High: {high_count}")
        logger.info(f"      📍 Standard: {standard_count}")
        logger.info("=" * 60)
        logger.info("")
        
        # Log usage with actual VLM cost
        usage_tracking_service.log_discovery_job(
            db=db,
            user_id=user_id,
            job_id=job_id,
            properties_found=processed_count,
            properties_with_imagery=evaluated_count,
            properties_analyzed=vlm_analyzed_count,
            businesses_loaded=len(discovered_businesses),
            vlm_total_cost=vlm_total_cost,  # Actual cost from OpenRouter
            metadata={
                "high_value_leads": high_value_count,
                "associations_made": processed_count,
                "businesses_skipped": skipped_count,
                "duration_seconds": elapsed,
                "mode": "business_first",
                "tiers": {
                    "premium": premium_count,
                    "high": high_count,
                    "standard": standard_count,
                },
            }
        )
    
    async def _run_contact_first_pipeline(
        self,
        job_id: UUID,
        user_id: UUID,
        filters: DiscoveryFilters,
        db: Session,
        city: Optional[str] = None,
        state: Optional[str] = None,
        job_titles: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
    ) -> None:
        """
        Run the contact-first discovery pipeline.
        
        This is the Apollo-first flow:
        1. Search Apollo for contacts by job title + location
        2. For each contact's company, search Regrid for properties they own
        3. Get satellite imagery for each property
        4. Run VLM analysis to score leads
        5. Create leads with GUARANTEED contact data
        
        Args:
            city: City for contact search (e.g., "Dallas")
            state: State code (e.g., "TX")
            job_titles: Job titles to search (defaults to property owner titles)
            industries: Industries to filter (defaults to real estate)
            scoring_prompt: User's criteria for VLM lead scoring
        """
        job_key = str(job_id)
        start_time = datetime.utcnow()
        
        # Get user to check for their own API key
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        user_openrouter_key = None
        if user and user.use_own_openrouter_key and user.openrouter_api_key:
            user_openrouter_key = user.openrouter_api_key
            logger.info("   Using user's own OpenRouter API key")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"🚀 CONTACT-FIRST DISCOVERY PIPELINE STARTED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Location: {city or 'Any'}, {state or 'Any'}")
        logger.info(f"   Max results: {filters.max_lots}")
        logger.info("=" * 60)
        
        # Check if Apollo is configured
        if not apollo_enrichment_service.is_configured:
            logger.error("   ❌ Apollo API key not configured")
            self._update_job(job_key, DiscoveryStep.FAILED, error="Apollo API key not configured")
            return
        
        # ============ Step 1: Search for contacts via Apollo ============
        logger.info("")
        logger.info("👥 STEP 1: Searching for contacts via Apollo...")
        self._update_job(job_key, DiscoveryStep.SEARCHING_CONTACTS)
        
        # Search for more contacts than we need (we'll filter by matched properties)
        max_contacts = min(filters.max_lots * 3, 50)  # Get 3x what we need, max 50 (free tier limit)
        
        contacts = await apollo_enrichment_service.search_contacts_by_location(
            city=city,
            state=state,
            job_titles=job_titles,
            industries=industries,
            max_results=max_contacts,
        )
        
        if not contacts:
            logger.warning("   ⚠️ No contacts found in Apollo")
            self._update_job(job_key, DiscoveryStep.COMPLETED)
            return
        
        logger.info(f"   ✅ Found {len(contacts)} contacts from Apollo")
        self._jobs[job_key]["progress"].contacts_found = len(contacts)
        
        # Group contacts by company (we'll search Regrid once per company)
        companies = {}
        for contact in contacts:
            company_name = contact.company_name
            if company_name not in companies:
                companies[company_name] = []
            companies[company_name].append(contact)
        
        logger.info(f"   📊 Contacts grouped into {len(companies)} unique companies")
        
        # ============ Step 2: Search Regrid for properties owned by each company ============
        logger.info("")
        logger.info("🗺️  STEP 2: Searching Regrid for properties by owner...")
        self._update_job(job_key, DiscoveryStep.SEARCHING_PROPERTIES)
        
        # Get county FIPS for more targeted search
        county_fips = None
        if city and state:
            # Try to get county FIPS (for better performance)
            county_fips = await regrid_service.get_county_fips(city=city, state=state)
        
        all_leads = []  # List of (contact, parcel) tuples
        companies_searched = 0
        
        for company_name, company_contacts in companies.items():
            if len(all_leads) >= filters.max_lots:
                break
            
            logger.info(f"   [{companies_searched + 1}/{len(companies)}] Searching: {company_name}")
            
            # Search Regrid for properties owned by this company
            parcels = await regrid_service.search_parcels_by_owner(
                owner_name=company_name,
                county_fips=county_fips,
                state_code=state,
                max_results=10,  # Limit per company
            )
            
            companies_searched += 1
            
            if not parcels:
                logger.info(f"      ❌ No properties found")
                continue
            
            logger.info(f"      ✅ Found {len(parcels)} properties")
            
            # Get the best contact for this company (first one, usually has highest rank)
            primary_contact = company_contacts[0]
            
            # Create leads (contact + parcel pairs)
            for parcel in parcels:
                if len(all_leads) >= filters.max_lots:
                    break
                all_leads.append((primary_contact, parcel))
        
        self._jobs[job_key]["progress"].companies_searched = companies_searched
        self._jobs[job_key]["progress"].properties_found = len(all_leads)
        
        if not all_leads:
            logger.warning("   ⚠️ No properties found for any contacts")
            self._update_job(job_key, DiscoveryStep.COMPLETED)
            return
        
        logger.info(f"   ✅ Total: {len(all_leads)} property-contact matches")
        
        # ============ Step 3: Get imagery and VLM score for each property ============
        logger.info("")
        logger.info("🎯 STEP 3: Analyzing properties...")
        self._update_job(job_key, DiscoveryStep.ANALYZING_PROPERTIES)
        
        analyzed_count = 0
        vlm_total_cost = 0.0
        property_ids = []
        
        for idx, (contact, parcel) in enumerate(all_leads):
            try:
                logger.info(f"   [{idx+1}/{len(all_leads)}] {parcel.address or parcel.parcel_id}")
                logger.info(f"      Contact: {contact.name} ({contact.email})")
                logger.info(f"      Company: {contact.company_name}")
                
                # Check if property already exists
                existing_property = db.query(Property).filter(
                    Property.regrid_id == parcel.parcel_id,
                    Property.user_id == user_id,
                ).first()
                
                if existing_property:
                    logger.info(f"      ♻️ Property already exists, updating contact info")
                    db_property = existing_property
                else:
                    # Create new property
                    from shapely.geometry import Point
                    centroid = parcel.centroid if parcel.centroid else Point(0, 0)
                    
                    db_property = Property(
                        user_id=user_id,
                        centroid=from_shape(centroid, srid=4326),
                        address=parcel.address,
                        discovery_source="contact_first",
                        status="discovered",
                    )
                    db.add(db_property)
                    db.flush()
                
                property_ids.append(db_property.id)
                
                # Store contact info (GUARANTEED from Apollo)
                db_property.contact_name = contact.name
                db_property.contact_first_name = contact.first_name
                db_property.contact_last_name = contact.last_name
                db_property.contact_email = contact.email
                db_property.contact_phone = contact.phone
                db_property.contact_title = contact.title
                db_property.contact_linkedin_url = contact.linkedin_url
                db_property.enriched_at = datetime.utcnow()
                db_property.enrichment_source = "apollo"
                db_property.enrichment_status = "success"
                
                # Store Regrid parcel data
                db_property.regrid_id = parcel.parcel_id
                db_property.regrid_apn = parcel.apn
                db_property.regrid_owner = parcel.owner
                db_property.regrid_owner2 = parcel.owner2
                db_property.regrid_owner_type = parcel.owner_type
                db_property.regrid_owner_address = parcel.mail_address
                db_property.regrid_owner_city = parcel.mail_city
                db_property.regrid_owner_state = parcel.mail_state
                db_property.regrid_land_use = parcel.land_use
                db_property.regrid_zoning = parcel.zoning
                db_property.regrid_zoning_desc = parcel.zoning_description
                db_property.regrid_year_built = str(parcel.year_built) if parcel.year_built else None
                db_property.regrid_area_acres = parcel.area_acres
                db_property.regrid_num_units = parcel.num_units
                db_property.regrid_num_stories = parcel.num_stories
                db_property.regrid_struct_style = parcel.struct_style
                db_property.regrid_fetched_at = datetime.utcnow()
                
                # Store LBCS codes (Premium tier - standardized classification)
                db_property.lbcs_activity = parcel.lbcs_activity
                db_property.lbcs_activity_desc = parcel.lbcs_activity_desc
                db_property.lbcs_function = parcel.lbcs_function
                db_property.lbcs_function_desc = parcel.lbcs_function_desc
                db_property.lbcs_structure = parcel.lbcs_structure
                db_property.lbcs_structure_desc = parcel.lbcs_structure_desc
                db_property.lbcs_site = parcel.lbcs_site
                db_property.lbcs_site_desc = parcel.lbcs_site_desc
                db_property.lbcs_ownership = parcel.lbcs_ownership
                db_property.lbcs_ownership_desc = parcel.lbcs_ownership_desc
                
                if parcel.polygon:
                    db_property.regrid_polygon = from_shape(parcel.polygon, srid=4326)
                
                # Get satellite imagery
                logger.info(f"      📷 Fetching satellite imagery...")
                
                imagery_result = await property_imagery_pipeline.get_property_image(
                    lat=parcel.centroid.y if parcel.centroid else 0,
                    lng=parcel.centroid.x if parcel.centroid else 0,
                    address=parcel.address,
                    zoom=20,
                    draw_boundary=True,
                    save_debug=True,
                )
                
                if imagery_result.success:
                    db_property.satellite_image_base64 = imagery_result.image_base64
                    db_property.satellite_zoom_level = str(imagery_result.metadata.get('zoom', 20))
                    db_property.area_m2 = imagery_result.area_sqm
                    db_property.area_sqft = imagery_result.area_sqft
                    db_property.satellite_fetched_at = datetime.utcnow()
                    db_property.status = "imagery_captured"
                    
                    logger.info(f"      ✅ Imagery captured: {imagery_result.image_size[0]}x{imagery_result.image_size[1]} px")
                    
                    # Run VLM analysis
                    logger.info(f"      🤖 Running VLM analysis...")
                    
                    vlm_result = await vlm_analysis_service.analyze_property(
                        image_base64=imagery_result.image_base64,
                        scoring_prompt=scoring_prompt,
                        property_context={
                            "address": parcel.address,
                            "owner": parcel.owner,
                            "land_use": parcel.land_use,
                            "area_acres": parcel.area_acres,
                            "contact_name": contact.name,
                            "contact_company": contact.company_name,
                        },
                        user_api_key=user_openrouter_key,
                    )
                    
                    if vlm_result.success:
                        db_property.lead_score = vlm_result.lead_score
                        db_property.lead_quality = (
                            'high' if vlm_result.lead_score >= 70 
                            else 'medium' if vlm_result.lead_score >= 40 
                            else 'low'
                        )
                        db_property.analysis_notes = vlm_result.reasoning
                        db_property.analyzed_at = datetime.utcnow()
                        db_property.status = "analyzed"
                        
                        if vlm_result.observations:
                            db_property.paved_percentage = vlm_result.observations.paved_area_pct
                            db_property.building_percentage = vlm_result.observations.building_pct
                            db_property.landscaping_percentage = vlm_result.observations.landscaping_pct
                        
                        analyzed_count += 1
                        if vlm_result.usage:
                            vlm_total_cost += vlm_result.usage.cost
                        
                        logger.info(f"      🎯 VLM Score: {vlm_result.lead_score}/100 ({db_property.lead_quality})")
                    else:
                        logger.warning(f"      ⚠️ VLM analysis failed: {vlm_result.error_message}")
                else:
                    logger.warning(f"      ⚠️ Imagery failed: {imagery_result.error_message}")
                    db_property.status = "failed"
                    db_property.status_error = imagery_result.error_message
                
                db.commit()
                self._jobs[job_key]["progress"].properties_analyzed = analyzed_count
                
                # Rate limiting
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"      ❌ Error processing property: {e}")
                import traceback
                traceback.print_exc()
                db.rollback()
        
        # ============ Step 4: Count high-value leads ============
        logger.info("")
        logger.info("🎯 STEP 4: Counting high-value leads...")
        self._update_job(job_key, DiscoveryStep.FILTERING)
        
        high_value_count = self._count_high_value_leads(property_ids, filters, db)
        self._jobs[job_key]["progress"].high_value_leads = high_value_count
        
        logger.info(f"   ✅ Found {high_value_count} high-value leads")
        
        # ============ Complete ============
        self._update_job(job_key, DiscoveryStep.COMPLETED)
        self._jobs[job_key]["completed_at"] = datetime.utcnow()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ CONTACT-FIRST DISCOVERY COMPLETED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   Duration: {elapsed:.1f} seconds")
        logger.info(f"   Contacts found: {len(contacts)}")
        logger.info(f"   Companies searched: {companies_searched}")
        logger.info(f"   Properties found: {len(all_leads)}")
        logger.info(f"   Properties analyzed: {analyzed_count}")
        logger.info(f"   VLM total cost: ${vlm_total_cost:.4f}")
        logger.info(f"   High-value leads: {high_value_count}")
        logger.info("=" * 60)
        logger.info("")
        
        # Log usage
        usage_tracking_service.log_discovery_job(
            db=db,
            user_id=user_id,
            job_id=job_id,
            properties_found=len(all_leads),
            properties_with_imagery=analyzed_count,
            properties_analyzed=analyzed_count,
            businesses_loaded=0,
            vlm_total_cost=vlm_total_cost,
            metadata={
                "mode": "contact_first",
                "contacts_found": len(contacts),
                "companies_searched": companies_searched,
                "high_value_leads": high_value_count,
                "duration_seconds": elapsed,
                "city": city,
                "state": state,
            }
        )
    
    async def _run_regrid_first_pipeline(
        self,
        job_id: UUID,
        user_id: UUID,
        area_polygon: Dict[str, Any],
        filters: DiscoveryFilters,
        db: Session,
        property_categories: Optional[List[str]] = None,
        scoring_prompt: Optional[str] = None,
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
    ) -> None:
        """
        Regrid-First Discovery Pipeline.
        
        Flow:
        1. Query Regrid directly by LBCS codes (skip Google Places)
        2. For each parcel: fetch satellite imagery
        3. VLM analysis for lead scoring
        4. Enrichment to find Property Manager contacts
        
        This is ideal when you want to find ALL properties of a certain type
        in an area, not just ones with Google Places listings.
        """
        from app.schemas.discovery import PROPERTY_CATEGORY_LBCS_RANGES, PropertyCategoryEnum
        from app.core.property_classifier import classify_property, PropertyCategory
        
        job_key = str(job_id)
        start_time = datetime.utcnow()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("🏢 REGRID-FIRST DISCOVERY PIPELINE STARTED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Max results: {filters.max_lots}")
        logger.info(f"   Categories: {property_categories}")
        if min_acres or max_acres:
            logger.info(f"   Size filter: {min_acres or 0} - {max_acres or '∞'} acres")
        logger.info("=" * 60)
        
        # ============ Step 1: Build LBCS queries from categories ============
        logger.info("")
        logger.info("🔍 STEP 1: Building LBCS query from property categories...")
        self._update_job(job_key, DiscoveryStep.QUERYING_REGRID)
        
        # Default to multi-family if no categories specified
        if not property_categories:
            property_categories = [PropertyCategoryEnum.MULTI_FAMILY.value]
        
        # Build LBCS queries grouped by field type (structure vs activity)
        # Import config that specifies which LBCS field to use for each category
        from app.schemas.discovery import PROPERTY_CATEGORY_LBCS_CONFIG
        
        lbcs_queries = {}  # field -> [(min, max), ...]
        for cat_str in property_categories:
            try:
                cat = PropertyCategoryEnum(cat_str)
                config = PROPERTY_CATEGORY_LBCS_CONFIG.get(cat, {})
                field = config.get("field", "lbcs_structure")
                ranges = config.get("ranges", [])
                
                if field not in lbcs_queries:
                    lbcs_queries[field] = []
                lbcs_queries[field].extend(ranges)
                
                logger.info(f"   📋 {cat.value}: LBCS {field} ranges {ranges}")
            except ValueError:
                logger.warning(f"   ⚠️ Unknown category: {cat_str}")
        
        # Backwards compatibility - flat list of ranges
        lbcs_ranges = []
        for ranges in lbcs_queries.values():
            lbcs_ranges.extend(ranges)
        
        if not lbcs_ranges:
            logger.error("   ❌ No valid LBCS ranges to search")
            self._update_job(job_key, DiscoveryStep.FAILED, error="No valid property categories")
            return
        
        # Extract ZIP code from area_polygon if available
        zip_code = None
        state_code = None
        county_fips = None
        
        # Try to get geographic filter from polygon properties
        if area_polygon and area_polygon.get("properties"):
            props = area_polygon["properties"]
            zip_code = props.get("zip_code")
            state_code = props.get("state")
            county_fips = props.get("county_fips")
        
        logger.info(f"   📍 Geographic filter: ZIP={zip_code}, State={state_code}, FIPS={county_fips}")
        
        # ============ Step 2: Query Regrid with Pagination ============
        logger.info("")
        logger.info("🗺️ STEP 2: Querying Regrid for parcels (with pagination)...")
        
        # Get existing parcel IDs to filter out
        existing_regrid_ids = set(
            row[0] for row in db.query(Property.regrid_id).filter(
                Property.user_id == user_id,
                Property.regrid_id.isnot(None)
            ).all()
        )
        
        # Pagination loop - keep fetching until we have enough NEW parcels
        batch_size = max(filters.max_lots * 2, 20)  # Fetch more per batch
        max_pages = 10  # Safety limit
        current_offset = 0
        new_parcels = []
        seen_parcel_ids = set()
        total_fetched = 0
        total_skipped = 0
        
        for page in range(max_pages):
            if len(new_parcels) >= filters.max_lots:
                break
            
            # Fetch next batch from each LBCS field
            batch_parcels = []
            for lbcs_field, ranges in lbcs_queries.items():
                if len(batch_parcels) >= batch_size:
                    break
                
                logger.info(f"   Querying {lbcs_field} with ranges: {ranges} (offset: {current_offset})")
                
                field_parcels = await regrid_service.search_parcels_by_lbcs(
                    lbcs_ranges=ranges,
                    county_fips=county_fips,
                    state_code=state_code,
                    zip_code=zip_code,
                    max_results=batch_size,
                    lbcs_field=lbcs_field,
                    min_acres=min_acres,
                    max_acres=max_acres,
                    offset=current_offset,
                )
                
                for parcel in field_parcels:
                    if parcel.parcel_id not in seen_parcel_ids:
                        seen_parcel_ids.add(parcel.parcel_id)
                        batch_parcels.append(parcel)
            
            if not batch_parcels:
                logger.info(f"   Regrid exhausted after {total_fetched} parcels")
                break
            
            total_fetched += len(batch_parcels)
            
            # Filter out existing parcels
            batch_new = 0
            for parcel in batch_parcels:
                if parcel.parcel_id not in existing_regrid_ids:
                    new_parcels.append(parcel)
                    batch_new += 1
                    if len(new_parcels) >= filters.max_lots:
                        break
                else:
                    total_skipped += 1
            
            logger.info(f"   Page {page+1}: fetched {len(batch_parcels)}, new={batch_new}, total_new={len(new_parcels)}, skipped={total_skipped}")
            current_offset += batch_size
        
        # Fallback to usedesc search if no LBCS results
        if not new_parcels and total_fetched == 0:
            logger.info("   ⚠️ No LBCS results, trying usedesc text search...")
            
            usedesc_patterns = []
            for cat_str in property_categories:
                if cat_str == "multi_family":
                    usedesc_patterns.extend(["apartment", "multi-family", "condo", "townhome"])
                elif cat_str == "retail":
                    usedesc_patterns.extend(["retail", "shopping", "store"])
                elif cat_str == "office":
                    usedesc_patterns.extend(["office"])
                elif cat_str == "industrial":
                    usedesc_patterns.extend(["warehouse", "industrial"])
                elif cat_str == "institutional":
                    usedesc_patterns.extend(["church", "school", "hospital"])
            
            if usedesc_patterns:
                fallback_parcels = await regrid_service.search_parcels_by_usedesc(
                    patterns=usedesc_patterns,
                    county_fips=county_fips,
                    state_code=state_code,
                    zip_code=zip_code,
                    max_results=filters.max_lots * 2,
                )
                for parcel in fallback_parcels:
                    if parcel.parcel_id not in existing_regrid_ids:
                        new_parcels.append(parcel)
                        if len(new_parcels) >= filters.max_lots:
                            break
        
        if not new_parcels:
            if total_fetched > 0:
                logger.warning(f"   ⚠️ All {total_fetched} parcels already processed. Try a different area.")
            else:
                logger.warning("   ⚠️ No parcels found matching criteria")
            self._update_job(job_key, DiscoveryStep.COMPLETED)
            return
        
        # Limit to max_lots NEW parcels
        if len(new_parcels) > filters.max_lots:
            new_parcels = new_parcels[:filters.max_lots]
        
        logger.info(f"   ✅ Found {len(new_parcels)} NEW parcels to process (fetched {total_fetched}, skipped {total_skipped})")
        self._jobs[job_key]["progress"].properties_found = len(new_parcels)
        
        # ============ Step 3: Process each parcel ============
        logger.info("")
        logger.info(f"📷 STEP 3: Processing {len(new_parcels)} parcels...")
        self._update_job(job_key, DiscoveryStep.PROCESSING_PARCELS)
        
        property_ids = []
        processed_count = 0
        analyzed_count = 0
        enriched_count = 0
        vlm_total_cost = 0.0
        
        # Get user's OpenRouter API key if available
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        user_api_key = None
        if user and user.use_own_openrouter_key and user.openrouter_api_key:
            user_api_key = user.openrouter_api_key
            logger.info("   🔑 Using user's OpenRouter API key")
        
        for idx, parcel in enumerate(new_parcels):
            try:
                processed_count += 1
                logger.info(f"")
                logger.info(f"   [{idx + 1}/{len(new_parcels)}] {parcel.address or parcel.parcel_id}")
                logger.info(f"      Owner: {parcel.owner or 'Unknown'}")
                logger.info(f"      LBCS Structure: {parcel.lbcs_structure} ({parcel.lbcs_structure_desc or 'N/A'})")
                
                centroid = parcel.centroid
                
                # Create property record
                db_property = Property(
                    user_id=user_id,
                    centroid=from_shape(centroid, srid=4326),
                    address=parcel.address,
                    discovery_source="regrid_first",
                    status="discovered",
                )
                db.add(db_property)
                db.flush()
                property_ids.append(db_property.id)
                
                # Store all Regrid data
                db_property.regrid_id = parcel.parcel_id
                db_property.regrid_apn = parcel.apn
                db_property.regrid_owner = parcel.owner
                db_property.regrid_owner2 = parcel.owner2
                db_property.regrid_owner_type = parcel.owner_type
                db_property.regrid_owner_address = parcel.mail_address
                db_property.regrid_owner_city = parcel.mail_city
                db_property.regrid_owner_state = parcel.mail_state
                db_property.regrid_land_use = parcel.land_use
                db_property.regrid_zoning = parcel.zoning
                db_property.regrid_zoning_desc = parcel.zoning_description
                db_property.regrid_year_built = str(parcel.year_built) if parcel.year_built else None
                db_property.regrid_area_acres = parcel.area_acres
                db_property.regrid_num_units = parcel.num_units
                db_property.regrid_num_stories = parcel.num_stories
                db_property.regrid_struct_style = parcel.struct_style
                db_property.regrid_fetched_at = datetime.utcnow()
                
                # Store LBCS codes
                db_property.lbcs_activity = parcel.lbcs_activity
                db_property.lbcs_activity_desc = parcel.lbcs_activity_desc
                db_property.lbcs_function = parcel.lbcs_function
                db_property.lbcs_function_desc = parcel.lbcs_function_desc
                db_property.lbcs_structure = parcel.lbcs_structure
                db_property.lbcs_structure_desc = parcel.lbcs_structure_desc
                db_property.lbcs_site = parcel.lbcs_site
                db_property.lbcs_site_desc = parcel.lbcs_site_desc
                db_property.lbcs_ownership = parcel.lbcs_ownership
                db_property.lbcs_ownership_desc = parcel.lbcs_ownership_desc
                
                # Store polygon
                if parcel.polygon:
                    db_property.regrid_polygon = from_shape(parcel.polygon, srid=4326)
                
                # Classify property
                category = classify_property(
                    lbcs_structure=parcel.lbcs_structure,
                    lbcs_activity=parcel.lbcs_activity,
                    lbcs_function=parcel.lbcs_function,
                    usecode=parcel.land_use,
                    usedesc=parcel.land_use,
                    zoning=parcel.zoning,
                    zoning_description=parcel.zoning_description,
                    struct_style=parcel.struct_style,
                )
                db_property.property_category = category.value
                
                # ============ Fetch Satellite Imagery ============
                logger.info(f"      📷 Fetching satellite imagery...")
                
                imagery_result = await property_imagery_pipeline.get_property_image(
                    lat=centroid.y,
                    lng=centroid.x,
                    address=parcel.address,
                )
                
                if imagery_result.success:
                    db_property.satellite_image_base64 = imagery_result.image_base64
                    db_property.satellite_zoom_level = str(imagery_result.metadata.get('zoom', 20))
                    db_property.satellite_fetched_at = datetime.utcnow()
                    db_property.area_m2 = imagery_result.area_sqm
                    db_property.area_sqft = imagery_result.area_sqft
                    db_property.status = "imagery_captured"
                    
                    self._jobs[job_key]["progress"].properties_found = processed_count
                    
                    logger.info(f"      ✅ Imagery captured: {imagery_result.image_size[0]}x{imagery_result.image_size[1]} px")
                    logger.info(f"         Property area: {imagery_result.area_sqft:,.0f} sqft")
                    
                    # ============ VLM Analysis ============
                    logger.info(f"      🤖 Running VLM analysis...")
                    
                    vlm_result = await vlm_analysis_service.analyze_property(
                        image_base64=imagery_result.image_base64,
                        scoring_prompt=scoring_prompt,
                        property_context={
                            "address": parcel.address,
                            "area_sqft": imagery_result.area_sqft,
                            "owner": parcel.owner,
                            "land_use": parcel.land_use,
                        },
                        user_api_key=user_api_key,
                    )
                    
                    if vlm_result.success:
                        db_property.lead_score = vlm_result.lead_score
                        db_property.lead_quality = (
                            'high' if vlm_result.lead_score >= 70 
                            else 'medium' if vlm_result.lead_score >= 40 
                            else 'low'
                        )
                        db_property.analysis_notes = vlm_result.reasoning
                        db_property.analyzed_at = datetime.utcnow()
                        db_property.status = "analyzed"
                        
                        if vlm_result.observations:
                            db_property.paved_percentage = vlm_result.observations.paved_area_pct
                            db_property.building_percentage = vlm_result.observations.building_pct
                            db_property.landscaping_percentage = vlm_result.observations.landscaping_pct
                        
                        analyzed_count += 1
                        if vlm_result.usage:
                            vlm_total_cost += vlm_result.usage.cost
                        
                        logger.info(f"      🎯 VLM Score: {vlm_result.lead_score}/100 ({db_property.lead_quality})")
                        
                        # ============ LLM-Powered Enrichment ============
                        # Use LLM to intelligently find Property Manager contact data
                        logger.info(f"      📇 LLM-powered enrichment to find Property Manager...")
                        self._update_job(job_key, DiscoveryStep.ENRICHING_LEADS)
                        
                        enrichment_result = await llm_enrichment_service.enrich(
                            address=parcel.address or "",
                            property_type=category.value,
                            owner_name=parcel.owner,
                            lbcs_code=parcel.lbcs_structure,
                        )
                        
                        # Store enrichment steps for UI (detailed steps with URLs)
                        import json
                        if enrichment_result.detailed_steps:
                            # Store detailed steps as JSON (includes URL, source, confidence)
                            db_property.enrichment_steps = json.dumps([
                                step.to_dict() for step in enrichment_result.detailed_steps
                            ])
                            flow_parts = [step.to_simple_string() for step in enrichment_result.detailed_steps]
                            logger.info(f"         Flow: {' → '.join(flow_parts)}")
                        elif enrichment_result.steps:
                            # Fallback to simple steps if no detailed steps
                            db_property.enrichment_steps = json.dumps(enrichment_result.steps)
                            logger.info(f"         Flow: {' → '.join(enrichment_result.steps)}")
                        
                        if enrichment_result.success and enrichment_result.contact:
                            contact = enrichment_result.contact
                            db_property.contact_name = contact.name
                            db_property.contact_first_name = contact.first_name
                            db_property.contact_last_name = contact.last_name
                            db_property.contact_email = contact.email
                            db_property.contact_phone = contact.phone
                            db_property.contact_title = contact.title
                            db_property.contact_company = enrichment_result.management_company
                            db_property.contact_company_website = enrichment_result.management_website
                            db_property.enriched_at = datetime.utcnow()
                            db_property.enrichment_source = "llm_enrichment"
                            db_property.enrichment_status = "success"
                            enriched_count += 1
                            logger.info(f"      ✅ Found contact: {contact.name or contact.phone or contact.email}")
                            logger.info(f"         Confidence: {enrichment_result.confidence:.0%}")
                            if enrichment_result.management_company:
                                logger.info(f"         Company: {enrichment_result.management_company}")
                        else:
                            db_property.enrichment_status = "not_found"
                            if enrichment_result.error_message:
                                logger.info(f"      ⚠️ Enrichment: {enrichment_result.error_message}")
                    else:
                        logger.warning(f"      ⚠️ VLM analysis failed: {vlm_result.error_message}")
                else:
                    logger.warning(f"      ⚠️ Imagery failed: {imagery_result.error_message}")
                    db_property.status = "failed"
                    db_property.status_error = imagery_result.error_message
                
                db.commit()
                self._jobs[job_key]["progress"].properties_analyzed = analyzed_count
                
                # Rate limiting
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"      ❌ Error processing parcel: {e}")
                import traceback
                traceback.print_exc()
                db.rollback()
        
        # ============ Complete ============
        self._update_job(job_key, DiscoveryStep.COMPLETED)
        self._jobs[job_key]["completed_at"] = datetime.utcnow()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ REGRID-FIRST DISCOVERY COMPLETED")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   Duration: {elapsed:.1f} seconds")
        logger.info(f"   Categories: {property_categories}")
        logger.info(f"   Parcels fetched: {total_fetched} (skipped {total_skipped})")
        logger.info(f"   Parcels processed: {processed_count}")
        logger.info(f"   Parcels analyzed: {analyzed_count}")
        logger.info(f"   Leads enriched: {enriched_count}")
        logger.info(f"   VLM total cost: ${vlm_total_cost:.4f}")
        logger.info("=" * 60)
        logger.info("")
        
        # Log usage
        usage_tracking_service.log_discovery_job(
            db=db,
            user_id=user_id,
            job_id=job_id,
            properties_found=len(new_parcels),
            properties_with_imagery=analyzed_count,
            properties_analyzed=analyzed_count,
            businesses_loaded=0,
            vlm_total_cost=vlm_total_cost,
            metadata={
                "mode": "regrid_first",
                "property_categories": property_categories,
                "parcels_processed": processed_count,
                "leads_enriched": enriched_count,
                "duration_seconds": elapsed,
            }
        )
    
    def _get_already_processed_places_ids(
        self,
        places_ids: List[str],
        db: Session,
    ) -> set:
        """
        Get set of places_ids that already have processed parking lots.
        
        A business is considered "already processed" if it:
        1. Exists in the Business table AND
        2. Has an associated Property (via PropertyBusiness)
        
        This allows re-discovering businesses that failed or were skipped.
        """
        if not places_ids:
            return set()
        
        # Query businesses that have associated parking lots
        processed = db.query(Business.places_id).join(
            PropertyBusiness,
            Business.id == PropertyBusiness.business_id
        ).filter(
            Business.places_id.in_(places_ids)
        ).all()
        
        return {row[0] for row in processed}
    
    def _count_high_value_leads(
        self,
        parking_lot_ids: List[UUID],
        filters: DiscoveryFilters,
        db: Session
    ) -> int:
        """Count parking lots that meet high-value lead criteria."""
        query = db.query(Property).filter(
            Property.id.in_(parking_lot_ids),
            Property.status.in_(["imagery_captured", "analyzed"]),
        )
        
        if filters.min_area_m2:
            query = query.filter(Property.area_m2 >= filters.min_area_m2)
        
        # Note: condition_score filter removed - use lead_score instead
        
        return query.count()
    
    def _update_job(
        self,
        job_key: str,
        step: DiscoveryStep,
        error: Optional[str] = None
    ) -> None:
        """Update job status."""
        if job_key not in self._jobs:
            return
        
        self._jobs[job_key]["status"] = step
        self._jobs[job_key]["progress"].current_step = step
        
        step_order = [
            DiscoveryStep.QUEUED,
            DiscoveryStep.CONVERTING_AREA,
            DiscoveryStep.COLLECTING_PARKING_LOTS,
            DiscoveryStep.NORMALIZING,
            DiscoveryStep.FETCHING_IMAGERY,
            DiscoveryStep.EVALUATING_CONDITION,
            DiscoveryStep.LOADING_BUSINESSES,
            DiscoveryStep.ASSOCIATING,
            DiscoveryStep.FILTERING,
            DiscoveryStep.COMPLETED,
        ]
        
        if step in step_order:
            self._jobs[job_key]["progress"].steps_completed = step_order.index(step)
        
        if error:
            self._jobs[job_key]["error"] = error
            self._jobs[job_key]["progress"].errors.append(error)
    
    def get_job_status(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get current job status."""
        job_key = str(job_id)
        return self._jobs.get(job_key)
    
    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Remove old completed jobs from memory."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        removed = 0
        
        for job_key in list(self._jobs.keys()):
            job = self._jobs[job_key]
            if job.get("completed_at") and job["completed_at"] < cutoff:
                del self._jobs[job_key]
                removed += 1
        
        return removed


# Singleton instance
discovery_orchestrator = DiscoveryOrchestrator()
