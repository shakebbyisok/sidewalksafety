"""
Apollo.io Lead Enrichment Service

Finds decision maker contact information for property owners using Apollo.io API.

Flow:
1. Search for organization by name (from Regrid owner)
2. Find people at organization with decision maker titles
3. Enrich person to get email/phone

API Docs: https://docs.apollo.io/
"""

import logging
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result from Apollo enrichment."""
    success: bool
    contact_name: Optional[str] = None
    contact_first_name: Optional[str] = None
    contact_last_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_title: Optional[str] = None
    contact_linkedin_url: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    credits_used: int = 0
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class ContactSearchResult:
    """Result from Apollo contact search (for contact-first discovery)."""
    person_id: str
    first_name: str
    last_name: str
    name: str
    title: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    company_name: str
    company_id: Optional[str]
    company_domain: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    raw_data: Dict


class ApolloEnrichmentService:
    """
    Apollo.io integration for lead enrichment.
    
    Finds decision maker contacts for property management companies.
    """
    
    BASE_URL = "https://api.apollo.io/api/v1"
    
    # Titles that indicate decision makers for property services
    DECISION_MAKER_TITLES = [
        "Owner",
        "Property Manager", 
        "Asset Manager",
        "Facility Manager",
        "Facilities Manager",
        "Operations Manager",
        "Maintenance Manager",
        "Building Manager",
        "President",
        "CEO",
        "Chief Executive Officer",
        "Principal",
        "Partner",
        "Managing Partner",
        "Director of Operations",
        "VP of Operations",
        "Vice President",
        "General Manager",
    ]
    
    def __init__(self):
        self.api_key = settings.APOLLO_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
        
        if self.api_key:
            logger.info("Apollo Enrichment Service initialized")
        else:
            logger.warning("APOLLO_API_KEY not set - Lead enrichment will be disabled")
    
    @property
    def is_configured(self) -> bool:
        """Check if Apollo API is configured."""
        return bool(self.api_key)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": self.api_key or "",  # Apollo requires API key in header
                }
            )
        return self._client
    
    async def enrich_property_owner(
        self,
        owner_name: str,
        property_address: Optional[str] = None,
    ) -> EnrichmentResult:
        """
        Enrich a property owner to find decision maker contact.
        
        Args:
            owner_name: From Regrid (e.g., "WESTFIELD MANAGEMENT LLC")
            property_address: Optional context for matching
            
        Returns:
            EnrichmentResult with contact details or error
        """
        if not self.is_configured:
            return EnrichmentResult(
                success=False,
                error_message="Apollo API key not configured"
            )
        
        if not owner_name or len(owner_name.strip()) < 3:
            return EnrichmentResult(
                success=False,
                error_message="Owner name is required for enrichment"
            )
        
        # Clean up owner name
        clean_name = self._clean_company_name(owner_name)
        logger.info(f"  [Apollo] Enriching owner: {clean_name}")
        
        total_credits = 0
        
        try:
            # Step 1: Search for organization
            org_result = await self._search_organization(clean_name)
            total_credits += 1  # Organization search uses 1 credit
            
            if not org_result:
                logger.info(f"  [Apollo] No organization found for: {clean_name}")
                return EnrichmentResult(
                    success=False,
                    error_message=f"No organization found for '{clean_name}'",
                    credits_used=total_credits,
                )
            
            org_id = org_result.get("id")
            org_name = org_result.get("name")
            org_domain = org_result.get("primary_domain")
            
            logger.info(f"  [Apollo] Found organization: {org_name} (domain: {org_domain})")
            
            # Step 2: Search for people at organization with decision maker titles
            people = await self._search_people_at_org(org_id)
            # People search is free (doesn't consume credits)
            
            if not people:
                logger.info(f"  [Apollo] No decision makers found at {org_name}")
                return EnrichmentResult(
                    success=False,
                    error_message=f"No decision makers found at '{org_name}'",
                    company_name=org_name,
                    company_domain=org_domain,
                    credits_used=total_credits,
                )
            
            # Step 3: Enrich the best match (first person returned)
            best_person = people[0]
            logger.info(f"  [Apollo] Found contact: {best_person.get('name')} - {best_person.get('title')}")
            
            # Enrich to get email/phone (costs credits)
            enriched = await self._enrich_person(best_person.get("id"))
            total_credits += 1  # Person enrichment uses 1 credit
            
            if enriched:
                # Extract contact info
                email = enriched.get("email")
                phone = None
                
                # Check for phone numbers
                phone_numbers = enriched.get("phone_numbers", [])
                if phone_numbers:
                    # Prefer direct dial, then mobile, then any
                    for ph in phone_numbers:
                        if ph.get("type") == "direct":
                            phone = ph.get("sanitized_number") or ph.get("raw_number")
                            break
                    if not phone:
                        for ph in phone_numbers:
                            if ph.get("type") == "mobile":
                                phone = ph.get("sanitized_number") or ph.get("raw_number")
                                break
                    if not phone and phone_numbers:
                        phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
                
                result = EnrichmentResult(
                    success=True,
                    contact_name=enriched.get("name"),
                    contact_first_name=enriched.get("first_name"),
                    contact_last_name=enriched.get("last_name"),
                    contact_email=email,
                    contact_phone=phone,
                    contact_title=enriched.get("title"),
                    contact_linkedin_url=enriched.get("linkedin_url"),
                    company_name=org_name,
                    company_domain=org_domain,
                    credits_used=total_credits,
                    raw_response=enriched,
                )
                
                logger.info(f"  [Apollo] ✅ Enrichment successful: {result.contact_name} ({result.contact_email})")
                return result
            else:
                # Return basic info from search even if enrichment fails
                return EnrichmentResult(
                    success=True,
                    contact_name=best_person.get("name"),
                    contact_first_name=best_person.get("first_name"),
                    contact_last_name=best_person.get("last_name"),
                    contact_title=best_person.get("title"),
                    contact_linkedin_url=best_person.get("linkedin_url"),
                    company_name=org_name,
                    company_domain=org_domain,
                    credits_used=total_credits,
                    error_message="Could not retrieve email/phone",
                )
                
        except Exception as e:
            logger.error(f"  [Apollo] ❌ Enrichment error: {e}")
            return EnrichmentResult(
                success=False,
                error_message=str(e),
                credits_used=total_credits,
            )
    
    async def _search_organization(self, company_name: str) -> Optional[Dict]:
        """Search for an organization by name."""
        client = await self._get_client()
        
        url = f"{self.BASE_URL}/organizations/enrich"
        
        # Try with just the name first
        payload = {
            "name": company_name,
        }
        
        try:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                org = data.get("organization")
                if org:
                    return org
            
            # If not found, try a simpler search
            # Sometimes removing LLC, Inc, etc. helps
            simple_name = self._simplify_company_name(company_name)
            if simple_name != company_name:
                payload["name"] = simple_name
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    org = data.get("organization")
                    if org:
                        return org
            
            return None
            
        except Exception as e:
            logger.error(f"  [Apollo] Organization search error: {e}")
            return None
    
    async def _search_people_at_org(self, org_id: str) -> List[Dict]:
        """Search for decision makers at an organization."""
        client = await self._get_client()
        
        url = f"{self.BASE_URL}/mixed_people/api_search"
        
        payload = {
            "organization_ids": [org_id],
            "person_titles": self.DECISION_MAKER_TITLES,
            "page": 1,
            "per_page": 10,
        }
        
        try:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                people = data.get("people", [])
                return people
            
            return []
            
        except Exception as e:
            logger.error(f"  [Apollo] People search error: {e}")
            return []
    
    async def _enrich_person(self, person_id: str) -> Optional[Dict]:
        """Enrich a person to get full contact details."""
        client = await self._get_client()
        
        url = f"{self.BASE_URL}/people/match"
        
        payload = {
            "id": person_id,
            "reveal_personal_emails": True,
            "reveal_phone_number": True,
        }
        
        try:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                person = data.get("person")
                return person
            
            return None
            
        except Exception as e:
            logger.error(f"  [Apollo] Person enrichment error: {e}")
            return None
    
    def _clean_company_name(self, name: str) -> str:
        """Clean up company name for search."""
        if not name:
            return ""
        
        # Uppercase for consistency
        clean = name.strip()
        
        # Remove common suffixes that may not be in Apollo
        suffixes = [
            " LLC", " L.L.C.", " L.L.C",
            " INC", " INC.", " INCORPORATED",
            " CORP", " CORP.", " CORPORATION",
            " LTD", " LTD.", " LIMITED",
            " LP", " L.P.", " L.P",
            " LLP", " L.L.P.", " L.L.P",
            " CO", " CO.",
            " COMPANY",
        ]
        
        upper_clean = clean.upper()
        for suffix in suffixes:
            if upper_clean.endswith(suffix):
                clean = clean[:-len(suffix)].strip()
                break
        
        return clean
    
    def _simplify_company_name(self, name: str) -> str:
        """Further simplify company name."""
        clean = self._clean_company_name(name)
        
        # Remove common words that might not match
        remove_words = [
            "PROPERTIES", "PROPERTY",
            "MANAGEMENT", "MGMT",
            "HOLDINGS", "HOLDING",
            "INVESTMENTS", "INVESTMENT",
            "ENTERPRISES", "ENTERPRISE",
            "GROUP", "ASSOCIATES",
            "PARTNERS", "PARTNERSHIP",
            "SERVICES", "SERVICE",
            "REAL ESTATE", "REALTY",
        ]
        
        words = clean.split()
        filtered = [w for w in words if w.upper() not in remove_words]
        
        if filtered:
            return " ".join(filtered)
        return clean
    
    # ============ Contact-First Discovery Methods ============
    
    # Job titles for people who own or manage commercial real estate
    PROPERTY_OWNER_TITLES = [
        "Owner",
        "Principal", 
        "Managing Partner",
        "Partner",
        "President",
        "CEO",
        "Chief Executive Officer",
        "Founder",
        "Director of Real Estate",
        "VP of Real Estate",
        "Asset Manager",
        "Managing Director",
    ]
    
    # Industries for real estate companies
    REAL_ESTATE_INDUSTRIES = [
        "real estate",
        "commercial real estate", 
        "property management",
        "real estate investment",
        "real estate development",
    ]
    
    async def search_contacts_by_location(
        self,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: str = "United States",
        job_titles: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> List[ContactSearchResult]:
        """
        Search for contacts by location and job title (for contact-first discovery).
        
        This is the entry point for the Apollo-first flow:
        1. Search for people with property-related titles in a location
        2. Get their company name
        3. Later: Search Regrid for properties owned by that company
        
        Args:
            city: City name (e.g., "Dallas")
            state: State code (e.g., "TX")
            country: Country name
            job_titles: Job titles to search (defaults to PROPERTY_OWNER_TITLES)
            industries: Industries to filter (defaults to REAL_ESTATE_INDUSTRIES)
            max_results: Maximum number of contacts to return
            
        Returns:
            List of ContactSearchResult with contact + company info
        """
        if not self.is_configured:
            logger.warning("Apollo API key not configured")
            return []
        
        client = await self._get_client()
        
        # Use default titles if not specified
        if not job_titles:
            job_titles = self.PROPERTY_OWNER_TITLES
        
        # Use default industries if not specified
        if not industries:
            industries = self.REAL_ESTATE_INDUSTRIES
        
        # Build location filter
        person_locations = []
        if city and state:
            person_locations.append(f"{city}, {state}, {country}")
        elif state:
            person_locations.append(f"{state}, {country}")
        elif city:
            person_locations.append(f"{city}, {country}")
        else:
            person_locations.append(country)
        
        url = f"{self.BASE_URL}/mixed_people/api_search"
        
        payload = {
            "person_titles": job_titles,
            "person_locations": person_locations,
            "organization_industry_tag_ids": [],  # Will use keywords instead
            "q_organization_keyword_tags": industries,
            "page": 1,
            "per_page": min(max_results, 100),  # Apollo max is 100 per page
        }
        
        logger.info(f"  [Apollo] Searching for contacts in {person_locations[0]}")
        logger.info(f"  [Apollo] Titles: {', '.join(job_titles[:3])}...")
        
        results: List[ContactSearchResult] = []
        
        try:
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                logger.error(f"  [Apollo] Search failed: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            people = data.get("people", [])
            
            logger.info(f"  [Apollo] Found {len(people)} contacts")
            
            for person in people:
                # Extract company info
                org = person.get("organization", {}) or {}
                
                # Skip if no company name (we need it for Regrid search)
                company_name = org.get("name") or person.get("organization_name")
                if not company_name:
                    continue
                
                # Extract phone if available
                phone = None
                phone_numbers = person.get("phone_numbers", [])
                if phone_numbers:
                    phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
                
                result = ContactSearchResult(
                    person_id=person.get("id", ""),
                    first_name=person.get("first_name", ""),
                    last_name=person.get("last_name", ""),
                    name=person.get("name", ""),
                    title=person.get("title"),
                    email=person.get("email"),
                    phone=phone,
                    linkedin_url=person.get("linkedin_url"),
                    company_name=company_name,
                    company_id=org.get("id"),
                    company_domain=org.get("primary_domain") or org.get("website_url"),
                    city=person.get("city"),
                    state=person.get("state"),
                    country=person.get("country"),
                    raw_data=person,
                )
                results.append(result)
                
                if len(results) >= max_results:
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"  [Apollo] Contact search error: {e}")
            return []
    
    async def enrich_contact(self, person_id: str) -> Optional[ContactSearchResult]:
        """
        Enrich a contact to get full email/phone details.
        
        Args:
            person_id: Apollo person ID
            
        Returns:
            Updated ContactSearchResult with email/phone, or None if failed
        """
        enriched = await self._enrich_person(person_id)
        
        if not enriched:
            return None
        
        # Extract phone
        phone = None
        phone_numbers = enriched.get("phone_numbers", [])
        if phone_numbers:
            for ph in phone_numbers:
                if ph.get("type") in ["direct", "mobile"]:
                    phone = ph.get("sanitized_number") or ph.get("raw_number")
                    break
            if not phone and phone_numbers:
                phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")
        
        org = enriched.get("organization", {}) or {}
        
        return ContactSearchResult(
            person_id=enriched.get("id", ""),
            first_name=enriched.get("first_name", ""),
            last_name=enriched.get("last_name", ""),
            name=enriched.get("name", ""),
            title=enriched.get("title"),
            email=enriched.get("email"),
            phone=phone,
            linkedin_url=enriched.get("linkedin_url"),
            company_name=org.get("name") or enriched.get("organization_name", ""),
            company_id=org.get("id"),
            company_domain=org.get("primary_domain"),
            city=enriched.get("city"),
            state=enriched.get("state"),
            country=enriched.get("country"),
            raw_data=enriched,
        )
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
apollo_enrichment_service = ApolloEnrichmentService()
