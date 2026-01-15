from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class AreaType(str, Enum):
    ZIP = "zip"
    COUNTY = "county"
    POLYGON = "polygon"


class DiscoveryMode(str, Enum):
    """Discovery pipeline mode."""
    BUSINESS_FIRST = "business_first"  # Find businesses via Google Places → analyze property with Regrid + VLM
    CONTACT_FIRST = "contact_first"  # Find contacts via Apollo → find their properties via Regrid → VLM scoring
    REGRID_FIRST = "regrid_first"  # Query Regrid directly by LBCS codes → VLM scoring → Enrichment


class PropertyCategoryEnum(str, Enum):
    """Property categories for Regrid-first discovery (maps to LBCS codes)."""
    MULTI_FAMILY = "multi_family"      # LBCS 1200-1299: Apartments, condos
    RETAIL = "retail"                   # LBCS 2200-2599: Shopping, stores
    OFFICE = "office"                   # LBCS 2100-2199: Office buildings
    INDUSTRIAL = "industrial"           # LBCS 2600-2799: Warehouses
    INSTITUTIONAL = "institutional"     # LBCS 3500, 4100-4299: Churches, schools, hospitals


# LBCS code ranges for each property category
# LBCS code ranges per category with the appropriate LBCS field
# - lbcs_structure: Physical structure type (best for multi-family)
# - lbcs_activity: What happens on property (best for commercial/retail)
PROPERTY_CATEGORY_LBCS_CONFIG = {
    PropertyCategoryEnum.MULTI_FAMILY: {
        "field": "lbcs_structure",  # Structure codes for multi-family buildings
        "ranges": [(1200, 1299)],
    },
    PropertyCategoryEnum.RETAIL: {
        "field": "lbcs_activity",  # Activity codes for shopping/retail
        "ranges": [(2200, 2299), (2500, 2599)],
    },
    PropertyCategoryEnum.OFFICE: {
        "field": "lbcs_activity",  # Activity codes for office use
        "ranges": [(2100, 2199)],
    },
    PropertyCategoryEnum.INDUSTRIAL: {
        "field": "lbcs_activity",  # Activity codes for industrial/manufacturing
        "ranges": [(2600, 2699), (2700, 2799)],
    },
    PropertyCategoryEnum.INSTITUTIONAL: {
        "field": "lbcs_activity",  # Activity codes for institutional uses
        "ranges": [(3500, 3599), (4100, 4199), (4200, 4299)],
    },
}

# Backwards compatibility - just the ranges
PROPERTY_CATEGORY_LBCS_RANGES = {
    cat: config["ranges"] 
    for cat, config in PROPERTY_CATEGORY_LBCS_CONFIG.items()
}


class BusinessTierEnum(str, Enum):
    """Business priority tiers."""
    PREMIUM = "premium"
    HIGH = "high"
    STANDARD = "standard"


# Available business types by tier (for frontend display)
# NOTE: We search for ACTUAL properties, not management companies
BUSINESS_TYPE_OPTIONS = {
    "premium": [
        {"id": "apartments", "label": "Apartment Complexes", "queries": ["apartment complex", "apartments for rent", "apartment building"]},
        {"id": "condos", "label": "Condo Buildings", "queries": ["condominium complex", "condo building"]},
        {"id": "townhomes", "label": "Townhome Communities", "queries": ["townhome community", "townhouse complex"]},
        {"id": "mobile_home", "label": "Mobile Home Parks", "queries": ["mobile home park", "trailer park", "manufactured home community"]},
    ],
    "high": [
        {"id": "shopping", "label": "Shopping Centers / Malls", "queries": ["shopping center", "shopping mall", "retail plaza", "strip mall"]},
        {"id": "hotels", "label": "Hotels / Motels", "queries": ["hotel", "motel", "extended stay"]},
        {"id": "offices", "label": "Office Parks / Complexes", "queries": ["office park", "office complex", "business park"]},
        {"id": "warehouses", "label": "Warehouses / Industrial", "queries": ["warehouse", "distribution center", "industrial park", "logistics center"]},
    ],
    "standard": [
        {"id": "churches", "label": "Churches", "queries": ["church", "religious center", "place of worship"]},
        {"id": "schools", "label": "Schools", "queries": ["school", "private school", "charter school"]},
        {"id": "hospitals", "label": "Hospitals / Medical", "queries": ["hospital", "medical center", "urgent care"]},
        {"id": "gyms", "label": "Gyms / Fitness", "queries": ["gym", "fitness center", "recreation center"]},
        {"id": "grocery", "label": "Grocery Stores", "queries": ["grocery store", "supermarket"]},
        {"id": "car_dealers", "label": "Car Dealerships", "queries": ["car dealership", "auto dealership"]},
    ],
}


class GeoJSONPolygon(BaseModel):
    type: str = "Polygon"
    coordinates: List[List[List[float]]]


class DiscoveryFilters(BaseModel):
    min_area_m2: float = Field(default=200.0, ge=0, description="Minimum lot area in square meters")
    max_condition_score: float = Field(default=70.0, ge=0, le=100, description="Maximum condition score (lower = worse = better lead)")
    min_match_score: float = Field(default=50.0, ge=0, le=100, description="Minimum business match confidence")
    max_lots: int = Field(default=10, ge=1, le=1000, description="Maximum parking lots to process (for testing, use low values)")
    max_businesses: int = Field(default=10, ge=1, le=500, description="Maximum businesses to load (for testing, use low values)")


# ============ Discovery Request ============

class DiscoveryRequest(BaseModel):
    area_type: AreaType
    value: str = Field(..., description="ZIP code or county name")
    state: Optional[str] = Field(None, description="Required if area_type is 'county'. Also used for contact_first mode.")
    polygon: Optional[GeoJSONPolygon] = Field(None, description="Required if area_type is 'polygon'")
    filters: Optional[DiscoveryFilters] = None
    mode: DiscoveryMode = Field(
        default=DiscoveryMode.BUSINESS_FIRST,
        description="Discovery mode: 'business_first' finds businesses via Google Places, 'contact_first' finds contacts via Apollo then their properties"
    )
    # Business type selection (for business_first mode)
    tiers: Optional[List[BusinessTierEnum]] = Field(
        default=None,
        description="Tiers to search: 'premium', 'high', 'standard'. If None, searches all tiers."
    )
    business_type_ids: Optional[List[str]] = Field(
        default=None,
        description="Specific business type IDs to search (e.g., 'hoa', 'apartments'). If None, searches all types in selected tiers."
    )
    max_results: Optional[int] = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to discover (1-50). Default is 10."
    )
    scoring_prompt: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Custom criteria for VLM lead scoring. If not provided, uses default pavement maintenance scoring."
    )
    
    # ============ Contact-First Mode Parameters ============
    city: Optional[str] = Field(
        default=None,
        description="City for contact search (contact_first mode). E.g., 'Dallas'"
    )
    job_titles: Optional[List[str]] = Field(
        default=None,
        description="Job titles to search in Apollo (contact_first mode). E.g., ['Owner', 'Principal', 'Asset Manager']. Defaults to property owner titles."
    )
    industries: Optional[List[str]] = Field(
        default=None,
        description="Industries to filter (contact_first mode). E.g., ['real estate', 'property management']. Defaults to real estate industries."
    )
    
    # ============ Regrid-First Mode Parameters ============
    property_categories: Optional[List[PropertyCategoryEnum]] = Field(
        default=None,
        description="Property categories to search in Regrid (regrid_first mode). E.g., ['multi_family', 'retail']. Maps to LBCS codes."
    )
    min_acres: Optional[float] = Field(
        default=None,
        ge=0,
        description="Minimum parcel size in acres (regrid_first mode). E.g., 0.5 for half-acre minimum."
    )
    max_acres: Optional[float] = Field(
        default=None,
        ge=0,
        description="Maximum parcel size in acres (regrid_first mode). E.g., 10 for ten-acre maximum."
    )


# ============ Discovery Job Status ============

class DiscoveryStep(str, Enum):
    QUEUED = "queued"
    CONVERTING_AREA = "converting_area"
    # Business-first mode steps
    COLLECTING_PARKING_LOTS = "collecting_parking_lots"
    NORMALIZING = "normalizing"
    FETCHING_IMAGERY = "fetching_imagery"
    EVALUATING_CONDITION = "evaluating_condition"
    LOADING_BUSINESSES = "loading_businesses"
    ASSOCIATING = "associating"
    # Contact-first mode steps
    SEARCHING_CONTACTS = "searching_contacts"
    SEARCHING_PROPERTIES = "searching_properties"
    ANALYZING_PROPERTIES = "analyzing_properties"
    # Regrid-first mode steps
    QUERYING_REGRID = "querying_regrid"
    PROCESSING_PARCELS = "processing_parcels"
    ENRICHING_LEADS = "enriching_leads"
    # Final steps
    FILTERING = "filtering"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoveryProgress(BaseModel):
    current_step: DiscoveryStep
    steps_completed: int
    total_steps: int = 9
    # Business-first mode metrics
    parking_lots_found: int = 0
    parking_lots_evaluated: int = 0
    businesses_loaded: int = 0
    businesses_skipped: int = 0  # Already-processed businesses that were skipped
    associations_made: int = 0
    # Contact-first mode metrics
    contacts_found: int = 0
    companies_searched: int = 0
    properties_found: int = 0
    properties_analyzed: int = 0
    # Common metrics
    high_value_leads: int = 0
    errors: List[str] = []


class DiscoveryJobResponse(BaseModel):
    job_id: UUID
    status: DiscoveryStep
    message: str
    estimated_completion: Optional[datetime] = None


class DiscoveryStatusResponse(BaseModel):
    job_id: UUID
    status: DiscoveryStep
    progress: DiscoveryProgress
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class DiscoveryResultsResponse(BaseModel):
    job_id: UUID
    status: DiscoveryStep
    results: Dict[str, int]
    message: str


# ============ Discovery Job (for DB storage) ============

class DiscoveryJobCreate(BaseModel):
    user_id: UUID
    area_type: AreaType
    area_value: str
    area_polygon: Optional[Dict[str, Any]] = None
    filters: DiscoveryFilters


class DiscoveryJobUpdate(BaseModel):
    status: Optional[DiscoveryStep] = None
    progress: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    completed_at: Optional[datetime] = None

