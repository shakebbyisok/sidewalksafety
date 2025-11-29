# Property Verification

## Overview

The system automatically verifies that scraped businesses have parking lots before saving them as deals. Only businesses with verified parking lots are displayed to users.

## Verification Process

### Flow

```
1. Scrape Business → Get business info + place_id
2. Geocode Address → Get coordinates if missing
3. Verify Parking Lot → Call Google Places Place Details API
4. Check parkingOptions.parkingLot field
5. Save Deal → Only if has_parking_lot = true
```

### Verification Methods

**Primary Method: Google Places Place Details API**
- Uses `parkingOptions.parkingLot` field
- Verification method stored as: `"place_details"`
- Most accurate and reliable

**Fallback Scenarios:**
- `"no_place_id"` - Business has no place_id (cannot verify)
- `"field_unavailable"` - Place Details API doesn't have parking data
- `"api_error"` - Place Details API returned an error
- `"timeout"` - API request timed out
- `"error"` - General error during verification

## Database Schema

### Deal Model Fields

- `has_property_verified` (Boolean, NOT NULL, default: false, indexed)
  - Indicates if parking lot was verified
  - Only deals with `true` are displayed

- `property_verification_method` (String, nullable)
  - How verification was performed: `"place_details"`, `"no_place_id"`, etc.

- `property_type` (String, NOT NULL, default: `"parking_lot"`)
  - Type of property (for future expansion: lawn, sidewalk, etc.)

## API Integration

### Google Places Place Details API

**Endpoint:** `https://maps.googleapis.com/maps/api/place/details/json`

**Request Fields:**
- `place_id`: Google Places place_id
- `fields`: `geometry,parkingOptions` (minimal fields to reduce cost)
- `key`: GOOGLE_MAPS_KEY

**Response Handling:**
- `parkingOptions.parkingLot == true` → Verified, save deal
- `parkingOptions.parkingLot == false` → No parking lot, skip
- `parkingOptions.parkingLot == null` → Field unavailable, skip

**Cost:** ~$17 per 1,000 Place Details requests (only requesting 2 fields)

## User Experience

### Default Behavior

- **Scraping:** Only saves businesses with verified parking lots
- **List Endpoints:** Only returns deals with `has_property_verified = true`
- **Response Message:** Shows statistics (scraped, verified, skipped)

### Example Response

```json
{
  "job_id": "uuid",
  "status": "completed",
  "message": "Scraped 50 businesses. Verified 35 with parking lots. Skipped 15 without parking lots."
}
```

## Error Handling

- **API Failures:** Business is skipped, scraping continues
- **Missing place_id:** Business is skipped (cannot verify without place_id)
- **Timeout:** Business is skipped, logged for review
- **Rate Limiting:** Handled by Google API (429 responses logged)

## Future Enhancements

- **Satellite Detection Fallback:** If Place Details unavailable, use CV to detect parking lot from satellite imagery
- **Multiple Property Types:** Verify lawns, sidewalks, driveways
- **Verification Confidence Score:** Store confidence level of verification

