"""
Lead Enrichment Service

Orchestrates multi-layer enrichment to find Property Manager contact data.

Flow:
1. Classify property type (from Regrid data)
2. Try enrichment sources in order based on property type
3. Return best contact found

Sources (in priority order):
- Google Places: Get business at property, phone, website
- Website Scraping: Extract contacts from property/management website
- Apollo: Find Property Managers at management company
"""

import logging
import re
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from app.core.config import settings
from app.core.property_classifier import (
    PropertyCategory, 
    classify_property, 
    get_enrichment_strategy
)
from app.core.apollo_enrichment_service import apollo_enrichment_service

logger = logging.getLogger(__name__)


@dataclass
class EnrichedContact:
    """Contact data from enrichment."""
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    source: Optional[str] = None  # Which enrichment source found this
    confidence: float = 0.0  # 0-1 confidence score


@dataclass
class EnrichmentResult:
    """Result from the enrichment process."""
    success: bool
    property_category: PropertyCategory
    contact: Optional[EnrichedContact] = None
    management_company: Optional[str] = None
    management_phone: Optional[str] = None
    management_website: Optional[str] = None
    sources_tried: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


class LeadEnrichmentService:
    """
    Multi-layer lead enrichment service.
    
    Finds Property Manager contacts using multiple sources.
    """
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.google_api_key = settings.GOOGLE_PLACES_KEY
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Cache-Control": "max-age=0",
                }
            )
        return self._client
    
    async def enrich_property(
        self,
        address: str,
        property_name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        # LBCS codes (most reliable - Premium tier)
        lbcs_structure: Optional[int] = None,
        lbcs_activity: Optional[int] = None,
        lbcs_function: Optional[int] = None,
        # Text fields (fallback)
        usecode: Optional[str] = None,
        usedesc: Optional[str] = None,
        zoning: Optional[str] = None,
        zoning_description: Optional[str] = None,
        struct_style: Optional[str] = None,
        owner_name: Optional[str] = None,
        business_name: Optional[str] = None,
    ) -> EnrichmentResult:
        """
        Enrich a property to find the Property Manager contact.
        
        Args:
            address: Property street address
            property_name: Name of the property (if known)
            city: City
            state: State code
            lbcs_structure: LBCS structure code (1200-1299=multifamily, etc.)
            lbcs_activity: LBCS activity code
            lbcs_function: LBCS function code
            usecode: Regrid land use code
            usedesc: Regrid land use description
            zoning: Zoning code
            zoning_description: Zoning description
            struct_style: Structure style
            owner_name: Owner name from Regrid
            business_name: Business name (from Google Places)
            
        Returns:
            EnrichmentResult with contact data
        """
        sources_tried = []
        
        # Step 1: Classify property type using LBCS-first logic
        category = classify_property(
            # LBCS codes (most reliable)
            lbcs_structure=lbcs_structure,
            lbcs_activity=lbcs_activity,
            lbcs_function=lbcs_function,
            # Text fields (fallback)
            usecode=usecode,
            usedesc=usedesc,
            zoning=zoning,
            zoning_description=zoning_description,
            struct_style=struct_style,
            business_name=business_name or property_name,
        )
        logger.info(f"  [Enrichment] Property classified as: {category.value}")
        
        # Get enrichment strategy for this category
        strategy = get_enrichment_strategy(category)
        
        # Step 2: Try Google Places first (universal)
        management_company = None
        management_phone = None
        management_website = None
        
        places_result = await self._search_google_places(
            address=address,
            property_name=property_name or business_name,
            city=city,
            state=state,
            property_category=category,
        )
        sources_tried.append("google_places")
        
        if places_result:
            management_company = places_result.get("name")
            management_phone = places_result.get("phone")
            management_website = places_result.get("website")
            logger.info(f"  [Enrichment] Google Places found: {management_company}")
        
        # Step 3: Try website scraping if we have a website
        contact = None
        
        if management_website:
            logger.info(f"  [Enrichment] Scraping website: {management_website}")
            scraped_contacts = await self._scrape_website_contacts(management_website)
            sources_tried.append("website_scrape")
            
            if scraped_contacts:
                # Find best contact (prefer property manager titles)
                contact = self._select_best_contact(scraped_contacts, strategy["apollo_titles"])
                if contact:
                    contact.company_name = management_company
                    contact.company_website = management_website
                    contact.source = "website_scrape"
                    logger.info(f"  [Enrichment] ✅ Found contact from website: {contact.name} ({contact.email})")
        
        # Step 4: Try Apollo if we have a company name and no contact yet
        if not contact and management_company and apollo_enrichment_service.is_configured:
            logger.info(f"  [Enrichment] Searching Apollo for contacts at: {management_company}")
            apollo_contact = await self._search_apollo_management_company(
                company_name=management_company,
                titles=strategy["apollo_titles"],
            )
            sources_tried.append("apollo")
            
            if apollo_contact:
                contact = apollo_contact
                contact.company_name = management_company
                contact.company_website = management_website
                contact.source = "apollo"
                logger.info(f"  [Enrichment] ✅ Found contact from Apollo: {contact.name} ({contact.email})")
        
        # Step 5: If still no contact but we have phone, that's still useful
        if not contact and management_phone:
            contact = EnrichedContact(
                phone=management_phone,
                company_name=management_company,
                company_website=management_website,
                source="google_places",
                confidence=0.5,
            )
            logger.info(f"  [Enrichment] Using phone from Google Places: {management_phone}")
        
        # Build result
        success = contact is not None and (contact.email or contact.phone)
        
        if success:
            logger.info(f"  [Enrichment] ✅ Enrichment successful")
        else:
            logger.info(f"  [Enrichment] ⚠️ Could not find contact data")
        
        return EnrichmentResult(
            success=success,
            property_category=category,
            contact=contact,
            management_company=management_company,
            management_phone=management_phone,
            management_website=management_website,
            sources_tried=sources_tried,
        )
    
    async def _search_google_places(
        self,
        address: str,
        property_name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        property_category: Optional[PropertyCategory] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search Google Places for the property or management company.
        
        Returns dict with name, phone, website if found.
        """
        if not self.google_api_key:
            logger.warning("  [Enrichment] Google Places API key not configured")
            return None
        
        client = await self._get_client()
        
        # Build search queries based on what we know
        search_queries = []
        
        # If we have a property name, use it
        if property_name:
            search_queries.append(f"{property_name} {city or ''} {state or ''}".strip())
        
        # For regrid-first mode, search by property type + address
        # This helps find "Knoll Trail Apartments" when we only have "15820 KNOLL TRAIL DR"
        if property_category:
            if property_category == PropertyCategory.MULTI_FAMILY:
                # Try to find apartment complex at this address
                search_queries.extend([
                    f"apartments at {address}",
                    f"apartments near {address}",
                    f"{address} apartments",
                    f"{address} leasing office",
                ])
            elif property_category == PropertyCategory.RETAIL:
                search_queries.extend([
                    f"shopping center {address}",
                    f"{address} retail",
                    f"{address} plaza",
                ])
            elif property_category == PropertyCategory.OFFICE:
                search_queries.extend([
                    f"office building {address}",
                    f"{address} business center",
                ])
            elif property_category == PropertyCategory.INDUSTRIAL:
                search_queries.extend([
                    f"warehouse {address}",
                    f"{address} industrial",
                ])
            elif property_category == PropertyCategory.INSTITUTIONAL:
                search_queries.extend([
                    f"church {address}",
                    f"school {address}",
                    f"{address}",
                ])
        
        # Fallback: basic address search
        if not search_queries:
            search_queries = [
                f"{address}",
                f"{address} leasing office",
                f"{address} management",
            ]
        
        # Extract street number from our address for verification
        our_street_number = self._extract_street_number(address)
        
        for search_query in search_queries:
            try:
                # Text search
                url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
                params = {
                    "query": search_query,
                    "key": self.google_api_key,
                }
                
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    continue
                
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    continue
                
                # Check each result for address match (not just first one)
                for place in results[:5]:  # Check top 5 results
                    place_id = place.get("place_id")
                    place_address = place.get("formatted_address", "")
                    
                    if not place_id:
                        continue
                    
                    # Get place details (phone, website)
                    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    details_params = {
                        "place_id": place_id,
                        "fields": "name,formatted_phone_number,website,formatted_address,geometry",
                        "key": self.google_api_key,
                    }
                    
                    details_response = await client.get(details_url, params=details_params)
                    
                    if details_response.status_code != 200:
                        continue
                    
                    details_data = details_response.json()
                    result = details_data.get("result", {})
                    
                    # Verify address match
                    result_address = result.get("formatted_address", "")
                    result_street_number = self._extract_street_number(result_address)
                    
                    # Check if street numbers match (within reasonable range)
                    address_matches = self._addresses_match(
                        our_street_number, 
                        result_street_number,
                        address,
                        result_address
                    )
                    
                    if not address_matches:
                        logger.debug(f"  [Enrichment] Skipping {result.get('name')} - address mismatch: {result_address}")
                        continue
                    
                    logger.info(f"  [Enrichment] ✓ Address verified: {result.get('name')} at {result_address}")
                    
                    # Found a matching result with contact info
                    if result.get("formatted_phone_number") or result.get("website"):
                        return {
                            "name": result.get("name"),
                            "phone": result.get("formatted_phone_number"),
                            "website": result.get("website"),
                            "address": result.get("formatted_address"),
                        }
                    
            except Exception as e:
                logger.error(f"  [Enrichment] Google Places error: {e}")
                continue
        
        return None
    
    def _extract_street_number(self, address: str) -> Optional[int]:
        """Extract the street number from an address."""
        if not address:
            return None
        # Match leading numbers (e.g., "4319" from "4319 MCKINNEY AVE")
        match = re.match(r'^(\d+)', address.strip())
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
    
    def _addresses_match(
        self, 
        our_number: Optional[int], 
        their_number: Optional[int],
        our_address: str,
        their_address: str,
    ) -> bool:
        """
        Check if two addresses likely refer to the same property.
        
        Checks:
        1. Street numbers match exactly, OR
        2. Street numbers are within 50 of each other (same block), OR
        3. Street name appears in both addresses
        """
        # If we couldn't extract numbers, try street name matching
        if our_number is None or their_number is None:
            # Fall back to checking if street names match
            our_street = self._extract_street_name(our_address)
            their_street = self._extract_street_name(their_address)
            if our_street and their_street:
                return our_street.lower() in their_street.lower() or their_street.lower() in our_street.lower()
            return False
        
        # Exact match
        if our_number == their_number:
            return True
        
        # Within same block (50 numbers = roughly same block)
        # This handles cases where large complexes have multiple addresses
        if abs(our_number - their_number) <= 100:
            # Also verify street name matches
            our_street = self._extract_street_name(our_address)
            their_street = self._extract_street_name(their_address)
            if our_street and their_street:
                return our_street.lower() in their_street.lower() or their_street.lower() in our_street.lower()
        
        return False
    
    def _extract_street_name(self, address: str) -> Optional[str]:
        """Extract street name from address (e.g., 'MCKINNEY' from '4319 MCKINNEY AVE')."""
        if not address:
            return None
        # Remove number prefix and common suffixes
        cleaned = re.sub(r'^\d+\s*', '', address)  # Remove leading numbers
        cleaned = re.sub(r',.*$', '', cleaned)  # Remove everything after comma
        cleaned = re.sub(r'\s+(AVE|ST|BLVD|DR|RD|LN|CT|WAY|PL|CIR|TRL|PKWY|HWY)\b.*$', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip() if cleaned.strip() else None
    
    async def _scrape_website_contacts(
        self,
        website_url: str,
        max_pages: int = 3,
    ) -> List[EnrichedContact]:
        """
        Scrape a website for contact information.
        
        Looks at /contact, /about, /team pages for emails and phone numbers.
        """
        contacts = []
        client = await self._get_client()
        
        # Normalize URL
        if not website_url.startswith(("http://", "https://")):
            website_url = f"https://{website_url}"
        
        # Pages to check
        pages_to_check = [
            "",  # Homepage
            "/contact",
            "/contact-us",
            "/about",
            "/about-us",
            "/team",
            "/our-team",
            "/staff",
            "/management",
        ]
        
        all_emails = set()
        all_phones = set()
        pages_checked = 0
        
        for page_path in pages_to_check:
            if pages_checked >= max_pages:
                break
            
            try:
                url = urljoin(website_url, page_path)
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code != 200:
                    continue
                
                pages_checked += 1
                html = response.text
                soup = BeautifulSoup(html, "html.parser")
                
                # Extract text
                text = soup.get_text(separator=" ")
                
                # Find emails
                email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
                emails = re.findall(email_pattern, text)
                
                # Filter out common non-contact emails
                excluded = ["example.com", "domain.com", "email.com", "yoursite", "website"]
                for email in emails:
                    if not any(ex in email.lower() for ex in excluded):
                        all_emails.add(email.lower())
                
                # Find phone numbers (US format)
                phone_pattern = r"(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}"
                phones = re.findall(phone_pattern, text)
                
                for phone in phones:
                    # Clean up phone
                    clean_phone = re.sub(r"[^\d]", "", phone)
                    if len(clean_phone) >= 10:
                        all_phones.add(clean_phone[-10:])  # Last 10 digits
                
                # Try to find names with emails (e.g., "John Smith - john@company.com")
                # This is a simple heuristic
                for email in all_emails:
                    contact = EnrichedContact(
                        email=email,
                        confidence=0.6,
                    )
                    
                    # Try to find name near email
                    email_index = text.lower().find(email.lower())
                    if email_index > 0:
                        # Look for name patterns before email
                        context = text[max(0, email_index - 100):email_index]
                        name_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", context)
                        if name_match:
                            full_name = name_match.group(1)
                            parts = full_name.split()
                            contact.name = full_name
                            contact.first_name = parts[0] if parts else None
                            contact.last_name = parts[-1] if len(parts) > 1 else None
                            contact.confidence = 0.8
                    
                    contacts.append(contact)
                    
            except Exception as e:
                logger.debug(f"  [Enrichment] Error scraping {page_path}: {e}")
                continue
        
        # If we found phones but no emails, add phone-only contact
        if all_phones and not contacts:
            for phone in list(all_phones)[:1]:  # Just first phone
                formatted_phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
                contacts.append(EnrichedContact(
                    phone=formatted_phone,
                    confidence=0.5,
                ))
        
        # Add phones to existing contacts
        if all_phones and contacts:
            phone = list(all_phones)[0]
            formatted_phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
            for contact in contacts:
                if not contact.phone:
                    contact.phone = formatted_phone
        
        return contacts
    
    async def _search_apollo_management_company(
        self,
        company_name: str,
        titles: List[str],
    ) -> Optional[EnrichedContact]:
        """
        Search Apollo for contacts at a management company.
        """
        if not apollo_enrichment_service.is_configured:
            return None
        
        try:
            client = await apollo_enrichment_service._get_client()
            
            # First, find the organization
            org_result = await apollo_enrichment_service._search_organization(company_name)
            
            if not org_result:
                logger.debug(f"  [Enrichment] Apollo: Organization not found: {company_name}")
                return None
            
            org_id = org_result.get("id")
            org_domain = org_result.get("primary_domain")
            
            # Search for people with target titles
            url = f"{apollo_enrichment_service.BASE_URL}/mixed_people/api_search"
            
            payload = {
                "organization_ids": [org_id],
                "person_titles": titles,
                "page": 1,
                "per_page": 10,
            }
            
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                logger.debug(f"  [Enrichment] Apollo search failed: {response.status_code}")
                return None
            
            data = response.json()
            people = data.get("people", [])
            
            if not people:
                logger.debug(f"  [Enrichment] Apollo: No people found at {company_name}")
                return None
            
            # Get best match (first result)
            person = people[0]
            
            # Enrich to get email/phone
            enriched = await apollo_enrichment_service._enrich_person(person.get("id"))
            
            if enriched:
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
                
                return EnrichedContact(
                    name=enriched.get("name"),
                    first_name=enriched.get("first_name"),
                    last_name=enriched.get("last_name"),
                    email=enriched.get("email"),
                    phone=phone,
                    title=enriched.get("title"),
                    linkedin_url=enriched.get("linkedin_url"),
                    confidence=0.9,
                )
            else:
                # Return basic info from search
                return EnrichedContact(
                    name=person.get("name"),
                    first_name=person.get("first_name"),
                    last_name=person.get("last_name"),
                    title=person.get("title"),
                    linkedin_url=person.get("linkedin_url"),
                    confidence=0.6,
                )
                
        except Exception as e:
            logger.error(f"  [Enrichment] Apollo error: {e}")
            return None
    
    def _select_best_contact(
        self,
        contacts: List[EnrichedContact],
        preferred_titles: List[str],
    ) -> Optional[EnrichedContact]:
        """
        Select the best contact from a list.
        
        Prioritizes:
        1. Has email
        2. Has preferred title
        3. Higher confidence
        """
        if not contacts:
            return None
        
        def score_contact(c: EnrichedContact) -> float:
            score = c.confidence
            
            # Boost for having email
            if c.email:
                score += 1.0
            
            # Boost for having phone
            if c.phone:
                score += 0.5
            
            # Boost for matching preferred title
            if c.title:
                title_lower = c.title.lower()
                for pref_title in preferred_titles:
                    if pref_title.lower() in title_lower:
                        score += 0.5
                        break
            
            return score
        
        # Sort by score descending
        sorted_contacts = sorted(contacts, key=score_contact, reverse=True)
        
        # Return best contact that has email or phone
        for contact in sorted_contacts:
            if contact.email or contact.phone:
                return contact
        
        return sorted_contacts[0] if sorted_contacts else None
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
lead_enrichment_service = LeadEnrichmentService()
