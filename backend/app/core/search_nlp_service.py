"""
NLP Search Parser Service

Uses LLM via OpenRouter to parse natural language queries into structured SearchQuery objects.

Examples:
- "parking lots in miami" → category=parking, city=Miami
- "gas stations over 1 acre in 33139" → category=gas_station, min_acres=1, zip=33139  
- "McDonald's near downtown LA" → brand=McDonald's, viewport around LA
- "large industrial properties in Texas" → category=industrial, min_acres=5, state=TX
"""

import logging
import json
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.search_service import (
    SearchQuery, SearchFilters, SearchType, PROPERTY_CATEGORIES
)

logger = logging.getLogger(__name__)


# System prompt for Claude to parse search queries
NLP_SYSTEM_PROMPT = """You are a search query parser for a commercial property search system.

Your job is to parse natural language queries into structured search parameters.

## Available Property Categories (use category_id exactly as shown):
- parking: Parking Lots (surface and structured parking)
- gas_station: Gas Stations (fuel stations)
- retail: Retail (shopping centers, stores)
- restaurant: Restaurants (food service)
- industrial: Industrial (warehouses, manufacturing)
- vacant: Vacant Land (undeveloped)
- office: Office (office buildings)
- multifamily: Multi-Family (apartment complexes)

## Available Search Types:
- category: Search by property type within an area
- zip: Search by ZIP code (requires category or size filter)
- brand: Search for specific business/franchise names (e.g., McDonald's, Starbucks)
- polygon: Search within a drawn area (user must draw)

## Output Format (JSON):
{
  "search_type": "category" | "zip" | "brand",
  "category_id": "parking" | "gas_station" | etc (if searching by type),
  "brand_name": "string" (if searching for a brand),
  "zip_code": "string" (5 digit ZIP if mentioned),
  "city": "string" (if mentioned),
  "state_code": "string" (2 letter state code if mentioned),
  "min_acres": number (if size mentioned, convert to acres),
  "max_acres": number (if size mentioned),
  "requires_draw": boolean (true if user needs to draw an area)
}

## Rules:
1. If user mentions a brand name (McDonald's, Starbucks, Walmart, etc), use search_type="brand"
2. If user mentions a property type (parking, retail, etc), use search_type="category"
3. If user mentions a ZIP code, include it
4. If user mentions a city/state without ZIP, include city and state_code
5. If the query is vague about location, set requires_draw=true
6. Convert size mentions: "large" = min_acres 2, "over X acres" = min_acres X
7. Always return valid JSON

## Examples:
"parking lots in 33139" → {"search_type": "category", "category_id": "parking", "zip_code": "33139"}
"McDonald's in Florida" → {"search_type": "brand", "brand_name": "McDonald's", "state_code": "FL"}
"large industrial" → {"search_type": "category", "category_id": "industrial", "min_acres": 2, "requires_draw": true}
"gas stations over 1 acre near Miami" → {"search_type": "category", "category_id": "gas_station", "min_acres": 1, "city": "Miami", "state_code": "FL"}
"""


class NLPSearchService:
    """
    Service to parse natural language search queries using LLM via OpenRouter.
    """
    
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "openai/gpt-4o-mini"  # Fast and cheap for parsing
    
    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        if settings.OPENROUTER_API_KEY:
            self.client = AsyncOpenAI(
                base_url=self.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
            )
            logger.info("NLP Search Service initialized with OpenRouter")
        else:
            logger.warning("OPENROUTER_API_KEY not set - NLP search will not work")
    
    async def parse_query(
        self,
        natural_query: str,
        current_viewport: Optional[Dict] = None,
    ) -> SearchQuery:
        """
        Parse a natural language query into a structured SearchQuery.
        
        Args:
            natural_query: The user's natural language search query
            current_viewport: Current map viewport for context
            
        Returns:
            Structured SearchQuery object
        """
        logger.info(f"🧠 NLP: Parsing query '{natural_query}'")
        
        if not self.client:
            logger.warning("NLP client not available, returning default query")
            return SearchQuery(
                search_type=SearchType.CATEGORY,
                raw_query=natural_query,
                filters=SearchFilters(),
            )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.DEFAULT_MODEL,
                max_tokens=500,
                messages=[
                    {
                        "role": "system",
                        "content": NLP_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Parse this search query: \"{natural_query}\"\n\nReturn only valid JSON."
                    }
                ]
            )
            
            # Extract JSON from response
            response_text = response.choices[0].message.content.strip() if response.choices else ""
            
            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)
            
            parsed = json.loads(response_text)
            logger.info(f"   Parsed: {parsed}")
            
            # Convert to SearchQuery
            return self._build_search_query(parsed, natural_query, current_viewport)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse NLP response as JSON: {e}")
            # Return a fallback query that requires user action
            return SearchQuery(
                search_type=SearchType.CATEGORY,
                raw_query=natural_query,
                filters=SearchFilters(),
            )
        except Exception as e:
            logger.error(f"NLP parsing error: {e}")
            import traceback
            traceback.print_exc()
            return SearchQuery(
                search_type=SearchType.CATEGORY,
                raw_query=natural_query,
                filters=SearchFilters(),
            )
    
    def _build_search_query(
        self,
        parsed: Dict,
        raw_query: str,
        viewport: Optional[Dict],
    ) -> SearchQuery:
        """Build a SearchQuery from parsed NLP output."""
        
        search_type_str = parsed.get("search_type", "category")
        
        # Map to SearchType enum
        if search_type_str == "brand":
            search_type = SearchType.BRAND
        elif search_type_str == "zip":
            search_type = SearchType.ZIP
        else:
            search_type = SearchType.CATEGORY
        
        # Build filters
        filters = SearchFilters(
            category_id=parsed.get("category_id"),
            min_acres=parsed.get("min_acres"),
            max_acres=parsed.get("max_acres"),
        )
        
        # Build query
        query = SearchQuery(
            search_type=search_type,
            raw_query=raw_query,
            zip_code=parsed.get("zip_code"),
            state_code=parsed.get("state_code"),
            brand_name=parsed.get("brand_name"),
            filters=filters,
        )
        
        # Add viewport if no specific location given
        if viewport and parsed.get("requires_draw", False) is False:
            # If we have a city but no ZIP, we might want to geocode it
            # For now, use viewport as fallback
            if not query.zip_code and not query.state_code:
                query.viewport = viewport
        
        return query
    
    async def suggest_completions(
        self,
        partial_query: str,
    ) -> List[str]:
        """
        Get search suggestions for partial query.
        
        Args:
            partial_query: Partially typed query
            
        Returns:
            List of suggested complete queries
        """
        # Simple prefix-based suggestions
        suggestions = []
        
        partial_lower = partial_query.lower()
        
        # Category suggestions
        for cat_id, cat_info in PROPERTY_CATEGORIES.items():
            if partial_lower in cat_info["label"].lower():
                suggestions.append(f"{cat_info['label']} in current view")
                suggestions.append(f"{cat_info['label']} in ZIP...")
        
        # Brand suggestions
        common_brands = ["McDonald's", "Starbucks", "Walmart", "Target", "CVS", "Walgreens", "Shell", "7-Eleven"]
        for brand in common_brands:
            if partial_lower in brand.lower():
                suggestions.append(f"{brand} nearby")
        
        # Size suggestions
        if "large" in partial_lower or "over" in partial_lower:
            suggestions.append("Large parking lots in ZIP...")
            suggestions.append("Industrial over 5 acres")
        
        return suggestions[:5]  # Limit to 5 suggestions


# Singleton instance
nlp_search_service = NLPSearchService()
