"""
LLM-Powered Enrichment Service

Intelligent enrichment that uses LLM to:
1. Plan search strategies based on property type
2. Analyze web pages to find contact info
3. Navigate through pages following relevant links
4. Extract and validate contact data

Steps are simple text for UI display as: Step1 → Step2 → Step3
"""

import logging
import re
import json
import time
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote_plus

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class ExtractedContact:
    """Contact extracted by LLM."""
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    confidence: float = 0.0


@dataclass
class EnrichmentStep:
    """Detailed enrichment step with output and reasoning."""
    action: str  # e.g., "search_google", "verify_match", "extract_contact"
    description: str  # Human-readable description
    output: Optional[str] = None  # What was found/result
    reasoning: Optional[str] = None  # Why/verification reasoning
    status: str = "success"  # "success", "failed", "skipped"
    confidence: Optional[float] = None  # Confidence score if applicable
    url: Optional[str] = None  # Resource URL (search URL, website, etc.)
    source: Optional[str] = None  # Source name (apartments.com, Google Places, etc.)
    
    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "description": self.description,
            "output": self.output,
            "reasoning": self.reasoning,
            "status": self.status,
            "confidence": self.confidence,
            "url": self.url,
            "source": self.source,
        }
    
    def to_simple_string(self) -> str:
        """Convert to simple string for backwards compatibility."""
        parts = [self.description]
        if self.output:
            parts.append(self.output)
        if self.reasoning:
            parts.append(f"({self.reasoning})")
        return " ".join(parts)


@dataclass
class LLMEnrichmentResult:
    """Result from LLM-powered enrichment."""
    success: bool
    contact: Optional[ExtractedContact] = None
    management_company: Optional[str] = None
    management_website: Optional[str] = None
    management_phone: Optional[str] = None
    
    # Detailed steps with output and reasoning
    detailed_steps: List[EnrichmentStep] = field(default_factory=list)
    # Simple text steps for backwards compatibility
    steps: List[str] = field(default_factory=list)
    
    confidence: float = 0.0
    tokens_used: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        # Generate simple steps from detailed steps if needed
        if not self.steps and self.detailed_steps:
            self.steps = [step.to_simple_string() for step in self.detailed_steps]
        
        return {
            "success": self.success,
            "contact": asdict(self.contact) if self.contact else None,
            "management_company": self.management_company,
            "management_website": self.management_website,
            "management_phone": self.management_phone,
            "steps": self.steps,
            "detailed_steps": [step.to_dict() for step in self.detailed_steps],
            "steps_display": " → ".join(self.steps) if self.steps else None,
            "confidence": self.confidence,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
        }


# ============================================================
# LLM PROMPTS
# ============================================================

STRATEGY_PROMPT = """You are an expert at finding property manager contact information for commercial properties.

PROPERTY DATA:
- Address: {address}
- Type: {property_type}
- Owner (from records): {owner_name}

Plan 6-10 diverse search strategies to find the property manager, leasing office, or management company contact.
BE THOROUGH - try multiple angles:

1. PROPERTY NAME SEARCHES: Search for the property itself on listing sites
2. OWNER/COMPANY SEARCHES: Search for the owner company directly
3. ADDRESS VARIATIONS: Try different address formats
4. MANAGEMENT COMPANY: Look for property management company
5. DIRECT WEBSITES: Try likely website URLs

Return ONLY valid JSON (no markdown):
{{
  "strategies": [
    {{"action": "search_apartments_com", "query": "specific search"}},
    {{"action": "search_google", "query": "property name + city"}},
    {{"action": "search_google", "query": "owner company + property management"}},
    {{"action": "search_zillow", "query": "address search"}},
    {{"action": "search_yelp", "query": "property or management company"}},
    {{"action": "visit_url", "url": "https://likely-website.com"}}
  ]
}}

Valid actions: search_apartments_com, search_google, search_zillow, search_yelp, search_linkedin, visit_url

IMPORTANT: Generate at least 6 strategies with DIFFERENT queries and sources. Don't give up easy!"""


ANALYZE_PAGE_PROMPT = """Extract ALL contact information from this webpage for a property manager or leasing office.

TARGET PROPERTY: {address} ({property_type})
URL: {url}

PAGE CONTENT:
{content}

EXTRACT THOROUGHLY:
1. Look for phone numbers (main office, leasing, management)
2. Look for email addresses (leasing@, contact@, info@, manager@)
3. Look for contact form links
4. Look for management company names
5. Look for staff/team pages with individual contacts
6. Look for "Contact Us" or "About" links to follow

Return ONLY valid JSON:
{{
  "is_correct_property": true/false,
  "property_name": "Name if found",
  "contacts_found": [{{"name": "Name", "title": "Title", "phone": "Phone", "email": "Email"}}],
  "management_company": "Company name if found",
  "management_phone": "Main phone if found",
  "management_email": "Main email if found",
  "links_to_follow": [{{"href": "/contact", "reason": "Contact page"}}]
}}

Be aggressive in extraction - capture ALL phone numbers and emails you see!"""


VERIFY_PLACE_PROMPT = """Verify if this Google Places result matches the target property address.

TARGET PROPERTY: {target_address}
GOOGLE PLACES RESULT:
- Name: {place_name}
- Address: {place_address}

Return ONLY valid JSON:
{{
  "is_correct_property": true/false,
  "confidence": 0.0-1.0,
  "reason": "Brief explanation"
}}

Consider: street number, street name, city, state. Allow small variations (e.g., "Ave" vs "Avenue", nearby numbers)."""


SELECT_CONTACT_PROMPT = """Select the best property manager contact from collected data.

TARGET PROPERTY: {address}

COLLECTED DATA FROM MULTIPLE SOURCES:
{collected_data}

SELECTION CRITERIA (in order of preference):
1. Direct leasing office with both phone AND email
2. Property manager with phone OR email
3. Management company main contact
4. Any phone number associated with the property
5. Any email associated with the property

Return ONLY valid JSON:
{{
  "selected_contact": {{
    "name": "Name or leave empty",
    "title": "Title or leave empty", 
    "email": "Best email found",
    "phone": "Best phone found",
    "company": "Management company name"
  }},
  "confidence": 0.0-1.0,
  "verification": "Why this is the best contact for the property"
}}

IMPORTANT: Return a contact if you found ANY phone or email. Something is better than nothing!"""


# ============================================================
# LLM ENRICHMENT SERVICE
# ============================================================

class LLMEnrichmentService:
    """LLM-powered intelligent enrichment service."""
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.model = "openai/gpt-4o-mini"
        self.api_key = settings.OPENROUTER_API_KEY
        
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
        return self._client
    
    async def enrich(
        self,
        address: str,
        property_type: str,
        owner_name: Optional[str] = None,
        lbcs_code: Optional[int] = None,
    ) -> LLMEnrichmentResult:
        """
        Main enrichment flow with simple step logging.
        """
        if not self.is_configured:
            return LLMEnrichmentResult(
                success=False,
                error_message="OpenRouter API key not configured",
                steps=["❌ API not configured"]
            )
        
        detailed_steps: List[EnrichmentStep] = []
        steps: List[str] = []  # For backwards compatibility
        tokens_used = 0
        collected_data: List[Dict[str, Any]] = []
        
        try:
            # ============ Step 1: Plan Strategy ============
            logger.info(f"  [LLM] Planning strategy for {address}")
            
            # Format property type for display
            property_type_display = property_type.replace("_", " ").title()
            
            detailed_steps.append(EnrichmentStep(
                action="plan_strategy",
                description=f"Analyzing property type: {property_type_display}",
                output=f"LLM selecting best sources for {property_type_display} properties",
                reasoning=f"Strategy tailored for {property_type_display} (apartments.com for residential, Yelp for commercial, etc.)",
                status="success"
            ))
            
            strategy_response, plan_tokens = await self._call_llm(
                STRATEGY_PROMPT.format(
                    address=address,
                    property_type=property_type,
                    owner_name=owner_name or "Unknown",
                )
            )
            tokens_used += plan_tokens
            strategies = strategy_response.get("strategies", [])
            
            if not strategies:
                detailed_steps.append(EnrichmentStep(
                    action="plan_strategy",
                    description="No strategies found",
                    status="failed"
                ))
                # Generate simple steps from detailed_steps
                steps = [step.to_simple_string() for step in detailed_steps]
                return LLMEnrichmentResult(
                    success=False,
                    detailed_steps=detailed_steps,
                    steps=steps,
                    tokens_used=tokens_used,
                    error_message="LLM couldn't plan search strategy"
                )
            
            strategy_list = ", ".join([s.get("action", "").replace("_", " ") for s in strategies[:8]])
            detailed_steps[-1].output = f"Selected {len(strategies)} sources for {property_type_display}: {strategy_list}"
            
            # ============ Step 2: Execute Strategies ============
            # Execute MORE strategies - be persistent!
            max_strategies = min(len(strategies), 8)  # Try up to 8 strategies
            
            for strategy in strategies[:max_strategies]:
                action = strategy.get("action", "")
                query = strategy.get("query", address)
                
                if action == "search_apartments_com":
                    search_url = f"https://www.apartments.com/search/?query={quote_plus(query)}"
                    step = EnrichmentStep(
                        action="search_apartments_com",
                        description="Searching apartments.com",
                        status="success",
                        url=search_url,
                        source="apartments.com"
                    )
                    detailed_steps.append(step)
                    
                    result = await self._search_apartments_com(query, address, property_type)
                    if result:
                        if result.get("property_name"):
                            step.output = f"Found {result['property_name']}"
                            if result.get("source_url"):
                                step.url = result["source_url"]  # Use actual listing URL
                            if result.get("is_correct_property") is False:
                                step.reasoning = "Property name found but address doesn't match"
                                step.status = "failed"
                            else:
                                step.reasoning = "Property verified"
                        collected_data.append(result)
                        tokens_used += result.get("tokens_used", 0)
                    else:
                        step.status = "failed"
                        step.output = "No results found"
                        
                elif action == "search_google":
                    step = EnrichmentStep(
                        action="search_google",
                        description="Searching Google Places",
                        status="success",
                        source="Google Places"
                    )
                    detailed_steps.append(step)
                    
                    result = await self._search_google_places(query, address, property_type)
                    if result:
                        # Update step with source URL
                        if result.get("source_url"):
                            step.url = result["source_url"]
                        
                        # Only add if verified as correct property
                        if result.get("is_correct_property", False):
                            step.output = f"Found {result.get('property_name', 'property')}"
                            step.reasoning = result.get("verification_reason", "Address verified")
                            step.confidence = result.get("verification_confidence")
                            collected_data.append(result)
                            tokens_used += result.get("tokens_used", 0)
                        else:
                            step.status = "failed"
                            step.output = result.get("property_name", "Result found")
                            step.reasoning = result.get("verification_reason", "Address doesn't match target property")
                            step.confidence = result.get("verification_confidence", 0.0)
                        
                elif action == "visit_url":
                    url = strategy.get("url")
                    if url:
                        domain = urlparse(url).netloc
                        step = EnrichmentStep(
                            action="visit_url",
                            description=f"Visiting {domain}",
                            status="success",
                            url=url,
                            source=domain
                        )
                        detailed_steps.append(step)
                        
                        result = await self._visit_and_analyze(url, address, property_type)
                        if result:
                            step.output = result.get("property_name") or "Page analyzed"
                            if result.get("is_correct_property", False):
                                step.reasoning = "Page verified for target property"
                            else:
                                step.reasoning = "Page doesn't match target property"
                                step.status = "failed"
                            collected_data.append(result)
                            tokens_used += result.get("tokens_used", 0)
                        else:
                            step.status = "failed"
                            step.output = "Failed to analyze page"
                
                elif action == "search_yelp":
                    yelp_search_url = f"https://www.yelp.com/search?find_desc={quote_plus(query)}"
                    step = EnrichmentStep(
                        action="search_yelp",
                        description="Searching Yelp",
                        status="success",
                        url=yelp_search_url,
                        source="Yelp"
                    )
                    detailed_steps.append(step)
                    
                    result = await self._search_yelp(query, address, property_type)
                    if result:
                        if result.get("source_url"):
                            step.url = result["source_url"]  # Use actual business URL
                        if result.get("is_correct_property", False):
                            step.output = f"Found {result.get('property_name', 'business')}"
                            step.reasoning = "Business verified"
                            collected_data.append(result)
                            tokens_used += result.get("tokens_used", 0)
                        else:
                            step.status = "failed"
                            step.output = "No verified match found"
                    else:
                        step.status = "failed"
                        step.output = "No results found"
                
                elif action == "search_linkedin":
                    step = EnrichmentStep(
                        action="search_linkedin",
                        description="Searching LinkedIn (via Google)",
                        status="success",
                        source="LinkedIn/Google"
                    )
                    detailed_steps.append(step)
                    
                    result = await self._search_linkedin_company(query, address, property_type)
                    if result:
                        if result.get("source_url"):
                            step.url = result["source_url"]
                        if result.get("management_company"):
                            step.output = f"Found: {result['management_company']}"
                        else:
                            step.output = "Found company info"
                        collected_data.append(result)
                        tokens_used += result.get("tokens_used", 0)
                    else:
                        step.status = "failed"
                        step.output = "No LinkedIn company found"
                
                elif action == "search_zillow":
                    zillow_url = f"https://www.zillow.com/homes/{quote_plus(query)}"
                    step = EnrichmentStep(
                        action="search_zillow",
                        description="Searching Zillow",
                        status="success",
                        url=zillow_url,
                        source="Zillow"
                    )
                    detailed_steps.append(step)
                    
                    # Use visit_and_analyze on Zillow search results
                    result = await self._visit_and_analyze(zillow_url, address, property_type)
                    if result:
                        if result.get("source_url"):
                            step.url = result["source_url"]
                        if result.get("is_correct_property", False):
                            step.output = f"Found {result.get('property_name', 'property')}"
                            step.reasoning = "Property verified"
                            collected_data.append(result)
                            tokens_used += result.get("tokens_used", 0)
                        else:
                            step.status = "failed"
                            step.output = "No verified match found"
                    else:
                        step.status = "failed"
                        step.output = "No results found"
                
                # Check if we have a verified contact
                verified_contact = any(
                    d.get("is_correct_property") and (
                        any(c.get("email") or c.get("phone") for c in d.get("contacts_found", [])) or
                        d.get("management_phone")
                    )
                    for d in collected_data
                )
                
                # Only early exit if we have a VERIFIED contact with phone/email
                if verified_contact:
                    logger.info(f"  [LLM] Found verified contact, stopping search")
                    break
            
            # ============ Step 2b: Fallback Strategies if no verified results ============
            verified_data = [d for d in collected_data if d.get("is_correct_property", False)]
            
            if not verified_data:
                logger.info(f"  [LLM] No verified results, trying fallback strategies...")
                
                # Fallback 1: Try owner-based search
                if owner_name and owner_name != "Unknown":
                    fallback_step = EnrichmentStep(
                        action="fallback_owner_search",
                        description=f"Fallback: Owner search '{owner_name[:25]}...'",
                        status="success",
                        source="Google Places (owner)"
                    )
                    detailed_steps.append(fallback_step)
                    
                    owner_query = f"{owner_name} property management contact"
                    result = await self._search_google_places(owner_query, address, property_type)
                    if result:
                        if result.get("management_phone") or result.get("contacts_found"):
                            fallback_step.output = f"Found via owner search"
                            collected_data.append(result)
                            tokens_used += result.get("tokens_used", 0)
                        else:
                            fallback_step.status = "failed"
                            fallback_step.output = "No contact info"
                    else:
                        fallback_step.status = "failed"
                        fallback_step.output = "No results"
                
                # Fallback 2: Try address-only search
                fallback_addr_step = EnrichmentStep(
                    action="fallback_address_search",
                    description="Fallback: Direct address search",
                    status="success",
                    source="Google Places (address)"
                )
                detailed_steps.append(fallback_addr_step)
                
                addr_result = await self._search_google_places(address, address, property_type)
                if addr_result:
                    if addr_result.get("management_phone") or addr_result.get("contacts_found"):
                        fallback_addr_step.output = "Found via address"
                        # For direct address search, mark as verified if address closely matches
                        addr_result["is_correct_property"] = True
                        collected_data.append(addr_result)
                        tokens_used += addr_result.get("tokens_used", 0)
                    else:
                        fallback_addr_step.status = "failed"
                        fallback_addr_step.output = "No contact info"
                else:
                    fallback_addr_step.status = "failed"
                    fallback_addr_step.output = "No results"
                
                # Fallback 3: Try generic property type search in area
                if property_type in ["multi_family", "retail", "office"]:
                    # Parse city from address
                    addr_parts = address.split(",")
                    city = addr_parts[1].strip() if len(addr_parts) > 1 else ""
                    
                    if city:
                        fallback_type_step = EnrichmentStep(
                            action="fallback_area_search",
                            description=f"Fallback: {property_type} in {city}",
                            status="success",
                            source="Google Places (area)"
                        )
                        detailed_steps.append(fallback_type_step)
                        
                        type_query = f"{property_type.replace('_', ' ')} leasing office {city}"
                        type_result = await self._search_google_places(type_query, address, property_type)
                        if type_result:
                            if type_result.get("management_phone"):
                                fallback_type_step.output = f"Found {type_result.get('property_name', 'property')}"
                                collected_data.append(type_result)
                                tokens_used += type_result.get("tokens_used", 0)
                            else:
                                fallback_type_step.status = "failed"
                                fallback_type_step.output = "No contact info"
                        else:
                            fallback_type_step.status = "failed"
                            fallback_type_step.output = "No results"
            
            # ============ Step 3: Filter and Select Best Contact ============
            # Filter out unverified results
            verified_data = [
                d for d in collected_data 
                if d.get("is_correct_property", False)
            ]
            
            if not verified_data:
                detailed_steps.append(EnrichmentStep(
                    action="filter_results",
                    description="Filtering verified results",
                    output=f"Searched {len(collected_data)} sources, none verified",
                    reasoning="No matches found that could be verified against property address",
                    status="failed"
                ))
                # Generate simple steps from detailed_steps
                steps = [step.to_simple_string() for step in detailed_steps]
                return LLMEnrichmentResult(
                    success=False,
                    detailed_steps=detailed_steps,
                    steps=steps,
                    tokens_used=tokens_used,
                    error_message=f"Tried {len(detailed_steps)} search strategies but could not find verified contact information"
                )
            
            filter_step = EnrichmentStep(
                action="filter_results",
                description="Filtering verified results",
                output=f"{len(verified_data)} verified sources",
                reasoning="Only using sources that match target property address",
                status="success"
            )
            detailed_steps.append(filter_step)
            
            # Select best contact via LLM (only from verified sources)
            select_step = EnrichmentStep(
                action="select_contact",
                description="Selecting best contact",
                status="success"
            )
            detailed_steps.append(select_step)
            
            final_response, select_tokens = await self._call_llm(
                SELECT_CONTACT_PROMPT.format(
                    address=address,
                    collected_data=json.dumps(verified_data, indent=2)[:4000]
                )
            )
            tokens_used += select_tokens
            
            selected = final_response.get("selected_contact", {})
            confidence = final_response.get("confidence", 0.0)
            verification = final_response.get("verification", "")
            
            # Get management info first (from verified sources)
            management_company = None
            management_website = None
            management_phone = None
            management_email = None
            
            for data in verified_data:
                if data.get("management_company") and not management_company:
                    management_company = data["management_company"]
                if data.get("source_url") and not management_website:
                    management_website = data["source_url"]
                if data.get("management_phone") and not management_phone:
                    management_phone = data["management_phone"]
                if data.get("management_email") and not management_email:
                    management_email = data["management_email"]
            
            # Build result
            contact = None
            contact_phone = selected.get("phone") or management_phone
            contact_email = selected.get("email") or management_email
            
            if selected and (contact_email or contact_phone):
                name = selected.get("name")
                contact = ExtractedContact(
                    name=name,
                    first_name=name.split()[0] if name and " " in name else name,
                    last_name=name.split()[-1] if name and " " in name else None,
                    email=contact_email,
                    phone=contact_phone,
                    title=selected.get("title"),
                    company=selected.get("company") or management_company,
                    confidence=confidence,
                )
                
                # Update select step with results
                output_parts = []
                if contact.phone:
                    output_parts.append(f"Phone: {contact.phone}")
                if contact.email:
                    output_parts.append(f"Email: {contact.email}")
                if contact.company:
                    output_parts.append(f"Company: {contact.company}")
                
                select_step.output = ", ".join(output_parts)
                select_step.reasoning = verification or f"Selected with {confidence:.0%} confidence"
                select_step.confidence = confidence
            
            if contact:
                detailed_steps.append(EnrichmentStep(
                    action="complete",
                    description="✓ Contact found",
                    output=f"{contact.name or 'Contact'} at {contact.company or 'property'}",
                    status="success",
                    confidence=confidence,
                    url=management_website,
                    source=management_company or "Property"
                ))
            else:
                select_step.status = "failed"
                select_step.output = "No contact extracted"
                detailed_steps.append(EnrichmentStep(
                    action="complete",
                    description="No contact extracted",
                    status="failed"
                ))
            
            # Generate simple steps from detailed_steps for backwards compatibility
            steps = [step.to_simple_string() for step in detailed_steps]
            
            return LLMEnrichmentResult(
                success=contact is not None,
                contact=contact,
                management_company=management_company or selected.get("company"),
                management_website=management_website,
                management_phone=management_phone or selected.get("phone"),
                detailed_steps=detailed_steps,
                steps=steps,  # Always populate steps
                confidence=confidence,
                tokens_used=tokens_used,
            )
                
        except Exception as e:
            logger.error(f"  [LLM] Error: {e}")
            import traceback
            traceback.print_exc()
            steps.append(f"Error: {str(e)[:50]}")
            
            return LLMEnrichmentResult(
                success=False,
                steps=steps,
                tokens_used=tokens_used,
                error_message=str(e),
            )
    
    # ============================================================
    # SEARCH METHODS
    # ============================================================
    
    async def _search_apartments_com(
        self,
        query: str,
        address: str,
        property_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Search apartments.com for property."""
        try:
            client = await self._get_client()
            search_url = f"https://www.apartments.com/search/?query={quote_plus(query)}"
            
            logger.info(f"  [LLM] Searching apartments.com: {query}")
            response = await client.get(search_url, follow_redirects=True)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find listing links
            listing_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/apartments/' in href or '/apartment/' in href:
                    if href.startswith('/'):
                        href = f"https://www.apartments.com{href}"
                    listing_links.append(href)
            
            listing_links = list(set(listing_links))[:3]
            
            if not listing_links:
                return None
            
            # Visit first listing
            for url in listing_links:
                result = await self._visit_and_analyze(url, address, property_type)
                if result and result.get("is_correct_property"):
                    result["source"] = "apartments.com"
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"  [LLM] apartments.com error: {e}")
            return None
    
    async def _search_google_places(
        self,
        query: str,
        address: str,
        property_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Search using Google Places API."""
        if not settings.GOOGLE_PLACES_KEY:
            return None
        
        try:
            client = await self._get_client()
            
            # Text search
            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            params = {"query": query, "key": settings.GOOGLE_PLACES_KEY}
            
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return None
            
            results = response.json().get("results", [])
            if not results:
                return None
            
            # Get details
            place = results[0]
            place_id = place.get("place_id")
            
            if place_id:
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {
                    "place_id": place_id,
                    "fields": "name,formatted_phone_number,website,formatted_address",
                    "key": settings.GOOGLE_PLACES_KEY,
                }
                
                details_response = await client.get(details_url, params=details_params)
                if details_response.status_code == 200:
                    result = details_response.json().get("result", {})
                    
                    name = result.get("name")
                    place_address = result.get("formatted_address", "")
                    phone = result.get("formatted_phone_number")
                    website = result.get("website")
                    
                    # Verify with LLM that this place matches the target address
                    verification, verify_tokens = await self._call_llm(
                        VERIFY_PLACE_PROMPT.format(
                            target_address=address,
                            place_name=name or "",
                            place_address=place_address
                        )
                    )
                    
                    is_correct = verification.get("is_correct_property", False)
                    verification_confidence = verification.get("confidence", 0.0)
                    
                    # Return verification details even if failed (for UI display)
                    if not is_correct:
                        logger.info(f"  [LLM] Google Places result '{name}' does not match '{address}' (confidence: {verification_confidence:.2f})")
                        return {
                            "source": "google_places",
                            "property_name": name,
                            "property_address": place_address,
                            "is_correct_property": False,
                            "verification_confidence": verification_confidence,
                            "verification_reason": verification.get("reason", "Address doesn't match"),
                            "tokens_used": verify_tokens,
                        }
                    
                    logger.info(f"  [LLM] Verified Google Places match: '{name}' = '{address}' (confidence: {verification_confidence:.2f})")
                    
                    if phone or website:
                        data = {
                            "source": "google_places",
                            "property_name": name,
                            "property_address": place_address,
                            "management_phone": phone,
                            "source_url": website,
                            "is_correct_property": True,
                            "verification_confidence": verification_confidence,
                            "verification_reason": verification.get("reason", ""),
                            "contacts_found": [],
                            "tokens_used": verify_tokens,
                        }
                        
                        # Visit website if available
                        if website:
                            web_result = await self._visit_and_analyze(website, address, property_type)
                            if web_result:
                                data["management_company"] = web_result.get("management_company") or name
                                data["contacts_found"] = web_result.get("contacts_found", [])
                                data["tokens_used"] += web_result.get("tokens_used", 0)
                        
                        return data
            
            return None
            
        except Exception as e:
            logger.error(f"  [LLM] Google Places error: {e}")
            return None
    
    async def _search_yelp(
        self,
        query: str,
        address: str,
        property_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Search Yelp for business contact info."""
        try:
            client = await self._get_client()
            search_url = f"https://www.yelp.com/search?find_desc={quote_plus(query)}"
            
            logger.info(f"  [LLM] Searching Yelp: {query}")
            response = await client.get(search_url, follow_redirects=True)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for business listings
            business_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/biz/' in href and not '/biz_photos/' in href:
                    if href.startswith('/'):
                        href = f"https://www.yelp.com{href}"
                    business_links.append(href)
            
            business_links = list(set(business_links))[:3]
            
            if not business_links:
                return None
            
            # Visit first business page
            for url in business_links:
                result = await self._visit_and_analyze(url, address, property_type)
                if result:
                    result["source"] = "yelp"
                    if result.get("is_correct_property"):
                        return result
            
            return None
            
        except Exception as e:
            logger.error(f"  [LLM] Yelp error: {e}")
            return None
    
    async def _search_linkedin_company(
        self,
        query: str,
        address: str,
        property_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Search for company info via Google (LinkedIn results)."""
        try:
            # We can't directly access LinkedIn, but we can search Google for LinkedIn company pages
            # and extract basic info from search results
            search_query = f"site:linkedin.com/company {query} property management"
            
            # Use Google Places API with a different query to find company info
            if not settings.GOOGLE_PLACES_KEY:
                return None
            
            client = await self._get_client()
            
            # Search for management company directly
            company_query = f"{query} property management company"
            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            params = {"query": company_query, "key": settings.GOOGLE_PLACES_KEY}
            
            logger.info(f"  [LLM] Searching for management company: {company_query}")
            
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return None
            
            results = response.json().get("results", [])
            if not results:
                return None
            
            # Get details for first result
            place = results[0]
            place_id = place.get("place_id")
            
            if place_id:
                details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                details_params = {
                    "place_id": place_id,
                    "fields": "name,formatted_phone_number,website,formatted_address",
                    "key": settings.GOOGLE_PLACES_KEY,
                }
                
                details_response = await client.get(details_url, params=details_params)
                if details_response.status_code == 200:
                    result = details_response.json().get("result", {})
                    
                    name = result.get("name")
                    phone = result.get("formatted_phone_number")
                    website = result.get("website")
                    company_address = result.get("formatted_address", "")
                    
                    if phone or website:
                        data = {
                            "source": "linkedin_company_search",
                            "management_company": name,
                            "management_phone": phone,
                            "source_url": website,
                            "company_address": company_address,
                            "is_correct_property": True,  # Management company doesn't need address verification
                            "contacts_found": [],
                            "tokens_used": 0,
                        }
                        
                        # Visit website if available to find contacts
                        if website:
                            web_result = await self._visit_and_analyze(website, address, property_type)
                            if web_result:
                                data["contacts_found"] = web_result.get("contacts_found", [])
                                data["tokens_used"] += web_result.get("tokens_used", 0)
                        
                        return data
            
            return None
            
        except Exception as e:
            logger.error(f"  [LLM] LinkedIn company search error: {e}")
            return None
    
    async def _visit_and_analyze(
        self,
        url: str,
        address: str,
        property_type: str,
        depth: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Visit URL and use LLM to extract contact info."""
        if depth > 1:
            return None
        
        try:
            client = await self._get_client()
            logger.info(f"  [LLM] Visiting: {url}")
            
            response = await client.get(url, follow_redirects=True)
            if response.status_code != 200:
                return None
            
            # Simplify HTML
            simplified = self._simplify_html(response.text)
            
            # LLM analyzes
            analysis, tokens = await self._call_llm(
                ANALYZE_PAGE_PROMPT.format(
                    address=address,
                    property_type=property_type,
                    url=url,
                    content=simplified[:6000]
                )
            )
            
            contacts = analysis.get("contacts_found", [])
            links = analysis.get("links_to_follow", [])
            
            result = {
                "source_url": url,
                "is_correct_property": analysis.get("is_correct_property", False),
                "property_name": analysis.get("property_name"),
                "contacts_found": contacts,
                "management_company": analysis.get("management_company"),
                "management_phone": analysis.get("management_phone"),
                "tokens_used": tokens,
            }
            
            # Follow contact links to find more info
            if links and depth < 2:  # Allow 2 levels deep
                # No contacts yet - try multiple links
                links_to_try = 3 if not contacts else 1
                for link in links[:links_to_try]:
                    href = link.get("href")
                    if href:
                        if href.startswith("/"):
                            href = urljoin(url, href)
                        sub = await self._visit_and_analyze(href, address, property_type, depth + 1)
                        if sub:
                            # Merge contacts
                            if sub.get("contacts_found"):
                                result["contacts_found"].extend(sub["contacts_found"])
                            # Update management info if found
                            if sub.get("management_phone") and not result.get("management_phone"):
                                result["management_phone"] = sub["management_phone"]
                            if sub.get("management_company") and not result.get("management_company"):
                                result["management_company"] = sub["management_company"]
                            result["tokens_used"] += sub.get("tokens_used", 0)
                            
                            # Stop if we have good contact info
                            if result.get("contacts_found") or result.get("management_phone"):
                                break
            
            return result
            
        except Exception as e:
            logger.error(f"  [LLM] Visit error: {e}")
            return None
    
    # ============================================================
    # HELPERS
    # ============================================================
    
    async def _call_llm(self, prompt: str) -> tuple[Dict[str, Any], int]:
        """Call LLM and return parsed JSON + token count."""
        try:
            client = await self._get_client()
            
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                }
            )
            
            if response.status_code != 200:
                logger.error(f"  [LLM] API error: {response.status_code}")
                return {}, 0
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            tokens = data.get("usage", {}).get("total_tokens", 0)
            
            # Parse JSON
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r'^```\w*\n?', '', content)
                content = re.sub(r'\n?```$', '', content)
            
            try:
                return json.loads(content), tokens
            except json.JSONDecodeError:
                logger.error(f"  [LLM] JSON parse failed")
                return {}, tokens
                
        except Exception as e:
            logger.error(f"  [LLM] Error: {e}")
            return {}, 0
    
    def _simplify_html(self, html: str) -> str:
        """Simplify HTML for LLM."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove noise
            for tag in soup.find_all(['script', 'style', 'meta', 'link', 'noscript', 'svg']):
                tag.decompose()
            
            parts = []
            
            # Title
            title = soup.find('title')
            if title:
                parts.append(f"TITLE: {title.get_text().strip()}")
            
            # Headings
            for h in soup.find_all(['h1', 'h2', 'h3'])[:5]:
                text = h.get_text().strip()
                if text:
                    parts.append(f"HEADING: {text}")
            
            # Contact links
            for a in soup.find_all('a', href=True):
                text = a.get_text().strip().lower()
                if text and len(text) < 30 and any(w in text for w in ['contact', 'about', 'team', 'staff']):
                    parts.append(f"LINK: {a.get_text().strip()} -> {a['href']}")
            
            # Body text
            body = soup.find('body')
            if body:
                body_text = body.get_text(separator=' ', strip=True)
                body_text = re.sub(r'\s+', ' ', body_text)
                parts.append(f"CONTENT: {body_text[:4000]}")
            
            return "\n".join(parts)
            
        except:
            return html[:4000]
    
    def _has_contact(self, collected_data: List[Dict]) -> bool:
        """Check if we found a contact with email or phone."""
        for data in collected_data:
            for contact in data.get("contacts_found", []):
                if contact.get("email") or contact.get("phone"):
                    return True
            if data.get("management_phone"):
                return True
        return False


# Singleton
llm_enrichment_service = LLMEnrichmentService()
