"""
Property Type Classifier

Classifies properties using Regrid's LBCS (Land Based Classification Standards) codes.
LBCS codes are standardized across all US counties, making them highly reliable.

Classification priority:
1. LBCS Structure code (most reliable - from county assessor data)
2. LBCS Activity/Function codes (backup standardized codes)
3. Text matching on usedesc/usecode (fallback for non-premium data)
4. Business name hints (last resort)
"""

from enum import Enum
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)


class PropertyCategory(str, Enum):
    """Property categories for enrichment flow routing."""
    MULTI_FAMILY = "multi_family"      # Apartments, condos, townhomes
    RETAIL = "retail"                   # Shopping centers, stores
    OFFICE = "office"                   # Office buildings
    INDUSTRIAL = "industrial"           # Warehouses, distribution
    INSTITUTIONAL = "institutional"     # Churches, schools, hospitals
    HOA = "hoa"                         # HOA-managed communities
    SINGLE_FAMILY = "single_family"     # Single-family homes (usually skip)
    UNKNOWN = "unknown"                 # Could not classify


# =============================================================================
# LBCS CODE RANGES
# =============================================================================

# LBCS Structure codes - Building types
LBCS_STRUCTURE_RANGES = {
    # Residential
    PropertyCategory.SINGLE_FAMILY: [(1100, 1199)],  # Single-family buildings
    PropertyCategory.MULTI_FAMILY: [
        (1200, 1299),  # Multifamily structures (1202=2 units, 1250=50 units, etc.)
        (1320, 1320),  # Dormitories
    ],
    # Commercial
    PropertyCategory.OFFICE: [(2100, 2199)],  # Office or bank building
    PropertyCategory.RETAIL: [
        (2200, 2299),  # Store or shop building
        (2500, 2599),  # Malls, shopping centers
    ],
    PropertyCategory.INDUSTRIAL: [
        (2600, 2699),  # Industrial buildings
        (2700, 2799),  # Warehouse or storage
    ],
    # Institutional
    PropertyCategory.INSTITUTIONAL: [
        (3500, 3599),  # Churches, synagogues, temples, mosques
        (4100, 4199),  # Medical facility
        (4200, 4299),  # School or university buildings
        (4300, 4399),  # Library building
    ],
}

# LBCS Activity codes - What people are doing
LBCS_ACTIVITY_RANGES = {
    PropertyCategory.MULTI_FAMILY: [(1100, 1399)],  # Household/transient/institutional living
    PropertyCategory.RETAIL: [(2000, 2299)],  # Shopping, business, trade
    PropertyCategory.OFFICE: [(2300, 2399)],  # Office activities
    PropertyCategory.INDUSTRIAL: [(3000, 3999)],  # Industrial, manufacturing, waste
    PropertyCategory.INSTITUTIONAL: [(4000, 4999)],  # Social, institutional, infrastructure
}

# LBCS Function codes - Economic function
LBCS_FUNCTION_RANGES = {
    PropertyCategory.MULTI_FAMILY: [
        (1000, 1299),  # Residence or accommodation
        (2320, 2329),  # Property management services (2322 = rental housing)
    ],
    PropertyCategory.RETAIL: [(2100, 2199), (2500, 2599)],  # Retail, food services
    PropertyCategory.OFFICE: [(2200, 2499)],  # Finance, real estate, professional services
    PropertyCategory.INDUSTRIAL: [(3000, 3699)],  # Manufacturing, wholesale, warehouse
    PropertyCategory.INSTITUTIONAL: [(6000, 6899)],  # Education, public admin, health care
}


# =============================================================================
# TEXT MATCHING PATTERNS (Fallback)
# =============================================================================

TEXT_CLASSIFICATION_RULES = {
    PropertyCategory.MULTI_FAMILY: [
        r"apartment",
        r"^mfr\b",           # MFR - APARTMENTS
        r"multi.?family",
        r"multi.?unit",
        r"multi.?res",
        r"residential.?multi",
        r"condo",
        r"condominium", 
        r"townho",
        r"mobile.?home",
        r"manufactured",
        r"student.?housing",
        r"senior.?living",
        r"assisted.?living",
        r"duplex",
        r"triplex",
        r"fourplex",
        r"quadplex",
        r"garden.?apt",
        r"high.?rise.?res",
    ],
    PropertyCategory.RETAIL: [
        r"retail",
        r"shopping",
        r"mall",
        r"strip.?cent",
        r"store",
        r"restaurant",
        r"fast.?food",
        r"gas.?station",
        r"convenience",
        r"grocery",
        r"supermarket",
        r"commercial.?retail",
        r"^cr\b",
        r"neighborhood.?center",
    ],
    PropertyCategory.OFFICE: [
        r"office",
        r"professional",
        r"medical.?office",
        r"business.?park",
        r"corporate",
        r"^co\b",
    ],
    PropertyCategory.INDUSTRIAL: [
        r"industrial",
        r"warehouse",
        r"distribution",
        r"manufacturing",
        r"logistics",
        r"storage",
        r"flex.?space",
        r"light.?industrial",
        r"^ci\b",
    ],
    PropertyCategory.INSTITUTIONAL: [
        r"church",
        r"religious",
        r"worship",
        r"school",
        r"education",
        r"hospital",
        r"medical.?center",
        r"clinic",
        r"government",
        r"municipal",
        r"library",
        r"museum",
        r"nonprofit",
        r"community.?center",
        r"exempt",
    ],
    PropertyCategory.HOA: [
        r"hoa",
        r"homeowner",
        r"association",
        r"common.?area",
        r"planned.?unit",
        r"pud",
    ],
}

# Commercial catch-all patterns
COMMERCIAL_CATCHALL_PATTERNS = [
    r"commercial\s+bpp",
    r"commercial\s+gen",
    r"^commercial$",
    r"commercial",
]


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_by_lbcs_structure(lbcs_structure: Optional[int]) -> Optional[PropertyCategory]:
    """
    Classify property by LBCS Structure code.
    This is the most reliable classification method.
    """
    if lbcs_structure is None:
        return None
    
    for category, ranges in LBCS_STRUCTURE_RANGES.items():
        for low, high in ranges:
            if low <= lbcs_structure <= high:
                logger.debug(f"LBCS Structure {lbcs_structure} -> {category.value}")
                return category
    
    return None


def classify_by_lbcs_activity(lbcs_activity: Optional[int]) -> Optional[PropertyCategory]:
    """Classify property by LBCS Activity code."""
    if lbcs_activity is None:
        return None
    
    for category, ranges in LBCS_ACTIVITY_RANGES.items():
        for low, high in ranges:
            if low <= lbcs_activity <= high:
                logger.debug(f"LBCS Activity {lbcs_activity} -> {category.value}")
                return category
    
    return None


def classify_by_lbcs_function(lbcs_function: Optional[int]) -> Optional[PropertyCategory]:
    """Classify property by LBCS Function code."""
    if lbcs_function is None:
        return None
    
    for category, ranges in LBCS_FUNCTION_RANGES.items():
        for low, high in ranges:
            if low <= lbcs_function <= high:
                logger.debug(f"LBCS Function {lbcs_function} -> {category.value}")
                return category
    
    return None


def classify_by_text(
    usecode: Optional[str] = None,
    usedesc: Optional[str] = None,
    zoning: Optional[str] = None,
    zoning_description: Optional[str] = None,
    struct_style: Optional[str] = None,
) -> Optional[PropertyCategory]:
    """
    Classify property by text matching on land use fields.
    Fallback method when LBCS codes are not available.
    """
    # Combine all text fields
    text_fields = [
        usecode or "",
        usedesc or "",
        zoning_description or "",
        struct_style or "",
    ]
    combined_text = " ".join(text_fields).upper()
    
    if not combined_text.strip():
        return None
    
    # Check each category's rules
    for category, patterns in TEXT_CLASSIFICATION_RULES.items():
        for pattern in patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                logger.debug(f"Text match '{pattern}' -> {category.value}")
                return category
    
    # Check zoning codes
    if zoning:
        zoning_upper = zoning.upper()
        
        # Multi-family zoning codes
        if any(z in zoning_upper for z in ["MF", "R-3", "R-4", "R-5", "RM", "RMF"]):
            return PropertyCategory.MULTI_FAMILY
        
        # Commercial zoning
        if any(z in zoning_upper for z in ["C-", "CR", "CC", "CG", "CN"]):
            return PropertyCategory.RETAIL
        
        # Office zoning
        if any(z in zoning_upper for z in ["O-", "PO", "BP"]):
            return PropertyCategory.OFFICE
        
        # Industrial zoning
        if any(z in zoning_upper for z in ["I-", "M-", "LI", "HI", "IR"]):
            return PropertyCategory.INDUSTRIAL
    
    # Commercial catch-all
    for pattern in COMMERCIAL_CATCHALL_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            logger.debug(f"Commercial catch-all '{pattern}' -> RETAIL")
            return PropertyCategory.RETAIL
    
    return None


def classify_by_business_name(business_name: Optional[str]) -> Optional[PropertyCategory]:
    """Classify property based on business name hints."""
    if not business_name:
        return None
    
    business_upper = business_name.upper()
    
    business_hints = {
        PropertyCategory.MULTI_FAMILY: [r"apartment", r"apt", r"residence", r"living", r"lofts", r"flats"],
        PropertyCategory.RETAIL: [r"shopping", r"center", r"plaza", r"mall", r"market"],
        PropertyCategory.OFFICE: [r"office", r"tower", r"building", r"corporate"],
        PropertyCategory.INSTITUTIONAL: [r"church", r"school", r"hospital", r"clinic", r"temple", r"mosque"],
    }
    
    for category, patterns in business_hints.items():
        for pattern in patterns:
            if re.search(pattern, business_upper, re.IGNORECASE):
                logger.debug(f"Business name match '{pattern}' -> {category.value}")
                return category
    
    return None


def classify_property(
    # LBCS codes (most reliable)
    lbcs_structure: Optional[int] = None,
    lbcs_activity: Optional[int] = None,
    lbcs_function: Optional[int] = None,
    # Text fields (fallback)
    usecode: Optional[str] = None,
    usedesc: Optional[str] = None,
    zoning: Optional[str] = None,
    zoning_description: Optional[str] = None,
    struct_style: Optional[str] = None,
    # Business name (last resort)
    business_name: Optional[str] = None,
) -> PropertyCategory:
    """
    Classify a property using the best available data.
    
    Classification priority:
    1. LBCS Structure code (most reliable)
    2. LBCS Activity code
    3. LBCS Function code
    4. Text matching on usedesc/usecode
    5. Business name hints
    
    Returns:
        PropertyCategory indicating the type of property
    """
    # Priority 1: LBCS Structure (most reliable)
    result = classify_by_lbcs_structure(lbcs_structure)
    if result:
        logger.info(f"   🏷️  Classified by LBCS Structure ({lbcs_structure}): {result.value}")
        return result
    
    # Priority 2: LBCS Activity
    result = classify_by_lbcs_activity(lbcs_activity)
    if result:
        logger.info(f"   🏷️  Classified by LBCS Activity ({lbcs_activity}): {result.value}")
        return result
    
    # Priority 3: LBCS Function
    result = classify_by_lbcs_function(lbcs_function)
    if result:
        logger.info(f"   🏷️  Classified by LBCS Function ({lbcs_function}): {result.value}")
        return result
    
    # Priority 4: Text matching
    result = classify_by_text(usecode, usedesc, zoning, zoning_description, struct_style)
    if result:
        logger.info(f"   🏷️  Classified by text ({usedesc or usecode}): {result.value}")
        return result
    
    # Priority 5: Business name hints
    result = classify_by_business_name(business_name)
    if result:
        logger.info(f"   🏷️  Classified by business name ({business_name}): {result.value}")
        return result
    
    logger.info(f"   🏷️  Could not classify property")
    return PropertyCategory.UNKNOWN


# =============================================================================
# ENRICHMENT STRATEGY
# =============================================================================

def get_enrichment_strategy(category: PropertyCategory) -> dict:
    """
    Get the enrichment strategy for a property category.
    
    Returns dict with:
        - primary_source: Best source for finding management company
        - search_queries: Google search queries to try
        - apollo_titles: Job titles to search in Apollo
        - fallback_sources: Backup sources to try
    """
    strategies = {
        PropertyCategory.MULTI_FAMILY: {
            "primary_source": "google_places",
            "search_queries": [
                "{property_name} leasing office",
                "{address} apartment management",
                "{property_name} property management",
            ],
            "apollo_titles": [
                "Property Manager",
                "Community Manager", 
                "Leasing Manager",
                "Regional Property Manager",
                "Maintenance Director",
                "Assistant Property Manager",
            ],
            "fallback_sources": ["website_scrape", "apollo"],
        },
        PropertyCategory.RETAIL: {
            "primary_source": "google_search",
            "search_queries": [
                "{address} property management",
                "{property_name} management company",
                "{address} shopping center management",
            ],
            "apollo_titles": [
                "Facilities Manager",
                "Property Manager",
                "General Manager",
                "Operations Manager",
                "Center Manager",
            ],
            "fallback_sources": ["google_places", "website_scrape", "apollo"],
        },
        PropertyCategory.OFFICE: {
            "primary_source": "google_search",
            "search_queries": [
                "{address} building management",
                "{property_name} property management",
                "{address} office building manager",
            ],
            "apollo_titles": [
                "Building Manager",
                "Facilities Manager",
                "Property Manager",
                "Facilities Director",
                "Operations Manager",
            ],
            "fallback_sources": ["google_places", "website_scrape", "apollo"],
        },
        PropertyCategory.INDUSTRIAL: {
            "primary_source": "google_search",
            "search_queries": [
                "{address} property management",
                "{property_name} facilities",
            ],
            "apollo_titles": [
                "Facilities Manager",
                "Operations Manager",
                "Plant Manager",
                "Site Manager",
            ],
            "fallback_sources": ["google_places", "website_scrape", "apollo"],
        },
        PropertyCategory.INSTITUTIONAL: {
            "primary_source": "google_places",
            "search_queries": [
                "{property_name}",
                "{property_name} {city}",
            ],
            "apollo_titles": [
                "Facilities Director",
                "Operations Director",
                "Facilities Manager",
                "Business Administrator",
            ],
            "fallback_sources": ["website_scrape", "apollo"],
        },
        PropertyCategory.HOA: {
            "primary_source": "google_search",
            "search_queries": [
                "{property_name} HOA management",
                "{property_name} community association",
                "{address} HOA",
            ],
            "apollo_titles": [
                "Community Manager",
                "HOA Manager",
                "Association Manager",
                "Property Manager",
            ],
            "fallback_sources": ["website_scrape", "apollo"],
        },
        PropertyCategory.UNKNOWN: {
            "primary_source": "google_places",
            "search_queries": [
                "{address}",
                "{property_name}",
            ],
            "apollo_titles": [
                "Property Manager",
                "Facilities Manager",
                "Operations Manager",
                "General Manager",
            ],
            "fallback_sources": ["website_scrape", "apollo"],
        },
        PropertyCategory.SINGLE_FAMILY: {
            # Usually skip single-family for commercial landscaping
            "primary_source": "skip",
            "search_queries": [],
            "apollo_titles": [],
            "fallback_sources": [],
        },
    }
    
    return strategies.get(category, strategies[PropertyCategory.UNKNOWN])


def get_unit_count_from_lbcs(lbcs_structure: Optional[int]) -> Optional[int]:
    """
    Extract unit count from LBCS Structure code for multifamily properties.
    
    LBCS Structure codes 1202-1299 encode unit counts:
    - 1202 = 2 units
    - 1210 = 10 units (or 1-10 units)
    - 1250 = 50 units
    - 1299 = 99+ units
    """
    if lbcs_structure is None:
        return None
    
    if 1202 <= lbcs_structure <= 1299:
        # Last two digits represent unit count (or range midpoint)
        return lbcs_structure - 1200
    
    return None
