# Architecture Overview

## Phase 1: Lead Scraping & Deal Evaluation

### Core Features

1. **Geographic Lead Scraping**
   - User selects ZIP code or county
   - Scrapes businesses from Apollo.io (primary) or Google Places (fallback)
   - Filters commercial properties with parking lots
   - **Property Verification**: Verifies parking lot exists via Google Places Place Details API
   - Only saves businesses with verified parking lots as Deal records

2. **Automated Deal Evaluation**
   - Geocodes address → coordinates
   - Downloads satellite imagery
   - Detects parking lot boundaries (simple CV)
   - Detects cracks/damage (Roboflow YOLOv8 API)
   - Calculates metrics and deal score (0-100)
   - Estimates revenue potential

3. **Deal Management**
   - View all verified deals (only businesses with parking lots)
   - Filter by status
   - View evaluation results with satellite imagery

### Tech Stack

- **Backend**: FastAPI + SQLAlchemy
- **Database**: Supabase (PostgreSQL)
- **Lead Scraping**: Apollo.io API + Google Places Text Search API
- **Property Verification**: Google Places Place Details API
- **AI Evaluation**: Roboflow API (YOLOv8), simple CV for parking lots
- **Geocoding**: Google Maps Geocoding API
- **Satellite Imagery**: Google Maps Static API

### Data Models

**User**
- Email, password, company name, phone
- All users are landscaping companies (no roles in Phase 1)

**Deal**
- Business info (name, address, contact)
- Location (lat/lng, places_id)
- Status (pending/evaluating/evaluated)
- Property verification (has_property_verified, property_verification_method, property_type)
- Belongs to user
- Only businesses with verified parking lots are saved

**Evaluation**
- Deal score (0-100)
- Parking lot area (sqft)
- Crack density (%)
- Damage severity
- Estimated costs/revenue
- Satellite image URL
- AI outputs (masks, detections)

### Authentication

- JWT-based authentication
- All deal/evaluation endpoints require auth
- Users can only see their own deals

---

## Future Phases

### Phase 2: Enhanced Features
- Better parking lot detection
- Improved georeferencing
- Deal filtering and sorting
- Analytics dashboard

### Phase 3: Role-Based Access Control

**User Roles:**
- **Company** - Full access (current users)
- **Worker** - View assigned deals, work measurements
- **Lead** - View-only access to their property evaluation

**Implementation:**
- Add `role` enum to users table
- Add `company_id` for workers
- Role-based endpoint access
- Data filtering by role

### Phase 4: Advanced Features
- Multi-company support
- Worker scheduling
- Customer portal
- Payment integration
- Project documentation

---

## Environment Variables

```env
# Database
SUPABASE_DB_URL=postgresql://...

# Google Maps
GOOGLE_MAPS_KEY=your_key

# Apollo.io (optional)
APOLLO_API_KEY=your_key

# Roboflow (optional)
ROBOFLOW_API_KEY=your_key

# Security
SECRET_KEY=your_secret_key

# Environment
ENVIRONMENT=development
```

