# API Reference

## Authentication

### `POST /api/v1/auth/register`
Register new landscaping company.

**Request:**
```json
{
  "email": "company@example.com",
  "password": "securepassword",
  "company_name": "ABC Landscaping",
  "phone": "+1234567890"
}
```

**Response:**
```json
{
  "access_token": "jwt_token",
  "token_type": "bearer",
  "user": { "id": "...", "email": "...", "company_name": "..." }
}
```

### `POST /api/v1/auth/login`
Login and get JWT token.

**Request:**
```json
{
  "email": "company@example.com",
  "password": "securepassword"
}
```

### `GET /api/v1/auth/me`
Get current user info (requires auth).

---

## Deals

### `POST /api/v1/deals/scrape`
Scrape deals by geographic area (requires auth).

**Request:**
```json
{
  "area_type": "zip" | "county",
  "value": "90210",
  "state": "CA"  // Required if area_type is "county"
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "message": "Scraped and saved 25 deals"
}
```

### `GET /api/v1/deals`
List all deals for current user (requires auth).

**Query Params:**
- `status` (optional): Filter by status (pending/evaluating/evaluated)

### `GET /api/v1/deals/map`
Get deals optimized for map display (requires auth).

**Query Params:**
- `min_lat`, `max_lat`, `min_lng`, `max_lng` (optional): Bounding box
- `status` (optional): Filter by status

**Response:** Array of deals with coordinates and evaluation scores.

### `GET /api/v1/deals/{deal_id}`
Get single deal by ID (requires auth).

---

## Evaluations

### `POST /api/v1/evaluations/{deal_id}`
Evaluate a single deal (requires auth).

**Response:** Full evaluation with score, metrics, satellite image.

### `POST /api/v1/evaluations/batch`
Evaluate multiple deals at once (requires auth).

**Request:**
```json
{
  "deal_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response:**
```json
{
  "evaluated": 2,
  "failed": 1,
  "message": "Evaluated 2 deals, 1 failed"
}
```

### `GET /api/v1/evaluations/{deal_id}`
Get deal with full evaluation data (requires auth).

---

## Geocoding

### `POST /api/v1/geocoding/reverse`
Reverse geocode coordinates to get ZIP code, county, etc.

**Request:**
```json
{
  "latitude": 34.0522,
  "longitude": -118.2437
}
```

**Response:**
```json
{
  "formatted_address": "Los Angeles, CA, USA",
  "zip": "90001",
  "county": "Los Angeles County",
  "state": "CA",
  "city": "Los Angeles",
  "place_id": "ChIJ..."
}
```

---

## Authentication

All endpoints except `/auth/register` and `/auth/login` require authentication.

Include JWT token in Authorization header:
```
Authorization: Bearer <token>
```

