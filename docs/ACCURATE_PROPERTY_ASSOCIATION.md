# Accurate Property Association Design

## Goal
Ensure 100% accuracy that:
1. Scraped business HAS the property type (parking lot, lawn, etc.)
2. Property is correctly ASSOCIATED with the business
3. Property is in BAD STATE (damaged/needs repair)

---

## API Capabilities Analysis

### 1. Apollo.io API

**Filtering Capabilities:**
- `q_organization_keyword_tags`: Filter by keywords/tags
- `industry`: Filter by industry type
- `q_keywords`: Search keywords
- **Limitation**: No direct property type filtering (parking lot, lawn, etc.)

**What We Can Do:**
- Filter by business type (retail, restaurant, office)
- Use industry tags to find businesses likely to have parking lots
- **Cannot**: Directly filter for "businesses with parking lots"

**Recommendation:** Use Apollo for initial business discovery, then validate with Google Places

---

### 2. Google Places API

#### A. Text Search / Nearby Search

**Filtering:**
- `includedType`: Filter by business type (e.g., "shopping_mall", "restaurant")
- `keyword`: Search by keywords
- `locationBias`: Focus on specific area
- `strictTypeFiltering`: Strict type filtering

**Business Types Relevant:**
- `shopping_mall` - Likely has parking lot
- `restaurant` - May have parking lot
- `store` - May have parking lot
- `lodging` - Hotels/motels have parking
- `office` - May have parking

**Limitation:** Cannot directly filter for "businesses with parking lots"

#### B. Place Details API

**Critical Fields Available:**

1. **`geometry`** - Building location & bounds
   ```json
   {
     "location": {"lat": 34.0522, "lng": -118.2437},
     "viewport": {
       "northeast": {"lat": 34.0535, "lng": -118.2424},
       "southwest": {"lat": 34.0509, "lng": -118.2450}
     }
   }
   ```
   - **Use**: Get exact building location and footprint bounds
   - **Accuracy**: High - Google's geocoded building location

2. **`parkingOptions`** - Parking availability data
   ```json
   {
     "parkingOptions": {
       "parkingLot": true,
       "parkingGarage": false,
       "streetParking": true,
       "valetParking": false,
       "accessibleParking": true
     }
   }
   ```
   - **Use**: Verify business HAS parking lot
   - **Accuracy**: Medium - Not all businesses have this data
   - **Limitation**: Doesn't tell us WHERE the parking lot is

3. **`types`** - Business categories
   - **Use**: Verify business type matches filter
   - **Accuracy**: High

**Key Insight:** `geometry.viewport` gives us building bounds - we can use this to:
- Center satellite image on building (not just address point)
- Detect parking lots within building's viewport area
- Associate parking lot to building based on proximity to viewport

---

### 3. Google Maps Static API (Satellite)

**Georeferencing Capabilities:**

**Image Parameters:**
- `center`: lat,lng (center of image)
- `zoom`: 1-20 (higher = more detail)
- `size`: widthxheight in pixels

**Georeferencing Calculation:**
```
For zoom level Z:
- Meters per pixel = 156543.03392 * cos(lat) / (2^Z)
- Image bounds can be calculated from center + size + zoom
- Each pixel can be converted to lat/lng coordinates
```

**Accuracy by Zoom Level:**
- Zoom 18: ~0.6 meters/pixel (good for parking lots)
- Zoom 19: ~0.3 meters/pixel (excellent detail)
- Zoom 20: ~0.15 meters/pixel (very high detail, larger API cost)

**What We Can Do:**
- Download satellite image centered on building viewport
- Calculate exact image bounds (north, south, east, west)
- Convert pixel coordinates to real-world coordinates
- Calculate accurate square footage from pixel area

---

## Accurate Association Strategy

### Phase 1: Business Discovery (Scraping)

**Apollo.io:**
- Filter by industry/keywords for businesses likely to have property type
- Example: For parking lots → search "retail", "shopping", "restaurant"

**Google Places:**
- Use `includedType` to filter business types
- Use `keyword` for property-type-specific searches
- Example: `includedType=shopping_mall` for parking lots

**Output:** List of businesses with addresses and coordinates

---

### Phase 2: Property Existence Validation

**For each business:**

1. **Get Place Details** (Google Places API)
   ```python
   GET /place/details?place_id=XXX&fields=geometry,parkingOptions,types
   ```

2. **Check Property Existence:**
   - **Parking Lot**: Check `parkingOptions.parkingLot == true`
   - **Lawn**: Check business type (office, hotel) + satellite image analysis
   - **Sidewalk**: Check business type (commercial) + satellite image analysis

3. **Get Building Geometry:**
   - Use `geometry.viewport` to get building bounds
   - Use `geometry.location` as building center
   - **This is the KEY** - gives us exact building location

4. **Reject if:**
   - No parking lot data AND cannot detect from satellite
   - Building geometry not available
   - Property type doesn't match

**Output:** Businesses with verified property existence + building geometry

---

### Phase 3: Property Detection & Association

**For each validated business:**

1. **Download Satellite Image:**
   ```python
   # Center on building viewport, not just address point
   center = building_geometry.location
   viewport = building_geometry.viewport
   
   # Calculate optimal zoom and bounds
   zoom = 19  # High detail for parking lot detection
   size = "2048x2048"  # Large enough to see parking lot
   
   # Download image
   image = download_satellite_image(center, zoom, size)
   ```

2. **Calculate Image Bounds:**
   ```python
   # Convert image bounds to lat/lng
   meters_per_pixel = 156543.03392 * cos(lat) / (2^zoom)
   image_width_meters = (size_width_pixels * meters_per_pixel)
   image_height_meters = (size_height_pixels * meters_per_pixel)
   
   north = center.lat + (image_height_meters / 2) / 111320
   south = center.lat - (image_height_meters / 2) / 111320
   east = center.lng + (image_width_meters / 2) / (111320 * cos(lat))
   west = center.lng - (image_width_meters / 2) / (111320 * cos(lat))
   ```

3. **Detect Property:**
   - Detect parking lots/lawns/sidewalks in satellite image
   - Return list of detected properties with pixel coordinates

4. **Associate Property to Building:**
   ```python
   def associate_property_to_building(properties, building_geometry):
       building_center = building_geometry.location
       building_viewport = building_geometry.viewport
       
       best_property = None
       best_score = 0
       
       for property in properties:
           score = 0
           
           # Convert property pixel coords to lat/lng
           property_center = pixel_to_latlng(property.center, image_bounds)
           
           # 1. Proximity to building (40 points)
           distance = calculate_distance(property_center, building_center)
           if distance < 50m: score += 40
           elif distance < 100m: score += 30
           elif distance < 200m: score += 20
           else: continue  # Too far
           
           # 2. Within building viewport (30 points)
           if is_within_viewport(property_center, building_viewport):
               score += 30
           
           # 3. Road connectivity (20 points)
           if has_road_connection(property, building_center):
               score += 20
           
           # 4. Size appropriateness (10 points)
           if property.area > min_area_for_business_type:
               score += 10
           
           if score > best_score:
               best_score = score
               best_property = property
       
       # Only return if confidence is high
       if best_score >= 70:
           return best_property, best_score
       return None, 0
   ```

5. **Reject if:**
   - No property detected
   - Association score < 70 (low confidence)
   - Property too far from building (>200m)

**Output:** Businesses with detected and associated properties

---

### Phase 4: Condition Evaluation

**For each associated property:**

1. **Extract Property Boundaries:**
   - Use detected property mask/polygon
   - Convert to real-world coordinates using georeferencing

2. **Calculate Accurate Area:**
   ```python
   # Convert pixel polygon to lat/lng polygon
   latlng_polygon = []
   for pixel_point in property_polygon:
       lat, lng = pixel_to_latlng(pixel_point, image_bounds)
       latlng_polygon.append((lat, lng))
   
   # Calculate area using Shapely with proper projection
   from shapely.geometry import Polygon
   from pyproj import Transformer
   
   # Project to local UTM for accurate area calculation
   transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
   utm_polygon = Polygon([transformer.transform(lng, lat) for lat, lng in latlng_polygon])
   area_sqft = utm_polygon.area * 10.764  # Convert m² to sqft
   ```

3. **Detect Damage:**
   - Run YOLOv8 for crack detection (parking lots)
   - Run CV analysis for brown patches (lawns)
   - Calculate damage density

4. **Calculate Severity:**
   ```python
   if crack_density > 10%: severity = "high"
   elif crack_density > 5%: severity = "medium"
   else: severity = "low"
   ```

5. **Reject if:**
   - Damage severity != "high" (if user wants only bad state)
   - Deal score < threshold

**Output:** Only deals with verified, associated, damaged properties

---

## Complete Flow

```
1. USER INPUT:
   {
     "property_type": "parking_lot",
     "min_damage_severity": "high",
     "area_type": "zip",
     "value": "90210"
   }

2. SCRAPE BUSINESSES:
   - Apollo: Filter by industry (retail, shopping)
   - Google Places: Filter by includedType (shopping_mall, store)
   - Output: 50 businesses

3. QUICK VALIDATION (Property Existence):
   - For each business:
     - Get Place Details (geometry, parkingOptions)
     - Check parkingOptions.parkingLot == true
     - Get building geometry (viewport, location)
     - Reject if no parking lot data
   - Output: 30 businesses with verified parking lots

4. PROPERTY DETECTION & ASSOCIATION:
   - For each business:
     - Download satellite image (centered on building viewport)
     - Detect parking lots in image
     - Associate parking lot to building (proximity + viewport)
     - Reject if association score < 70
   - Output: 20 businesses with associated parking lots

5. CONDITION EVALUATION:
   - For each associated property:
     - Extract property boundaries
     - Calculate accurate area (georeferencing)
     - Detect damage (cracks, potholes)
     - Calculate severity
     - Reject if severity != "high"
   - Output: 8 businesses with damaged parking lots

6. RETURN RESULTS:
   - Only deals that passed ALL checks
   - 100% accurate: verified property + associated + damaged
```

---

## Key Technical Details

### Building Geometry Usage

**Why `geometry.viewport` is critical:**
- Gives us building footprint bounds (not just point)
- We can center satellite image on building, not address
- Parking lot detection happens within building's area
- Higher accuracy for association

**Example:**
```python
building = place_details.geometry
center = building.location  # Exact building center
viewport = building.viewport  # Building bounds

# Download image centered on building
image = download_satellite_image(
    center=center,
    zoom=19,
    size="2048x2048"
)

# Calculate image bounds
image_bounds = calculate_bounds(center, zoom, size)

# Detect parking lots within building's area
parking_lots = detect_parking_lots(image, viewport_bounds)
```

### Georeferencing for Accurate Area

**Formula:**
```python
# Meters per pixel at given zoom and latitude
meters_per_pixel = 156543.03392 * cos(latitude_radians) / (2 ** zoom_level)

# Convert pixel coordinates to lat/lng
def pixel_to_latlng(pixel_x, pixel_y, image_bounds, image_size):
    lat_range = image_bounds.north - image_bounds.south
    lng_range = image_bounds.east - image_bounds.west
    
    lat = image_bounds.south + (pixel_y / image_size.height) * lat_range
    lng = image_bounds.west + (pixel_x / image_size.width) * lng_range
    
    return lat, lng

# Calculate area using UTM projection (accurate for small areas)
from pyproj import Transformer
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")
utm_coords = [transformer.transform(lng, lat) for lat, lng in polygon_coords]
area_m2 = Polygon(utm_coords).area
area_sqft = area_m2 * 10.764
```

---

## API Usage Strategy

### Cost Optimization:

1. **Scraping Phase:**
   - Apollo: Free tier or paid (check limits)
   - Google Places Text Search: $32 per 1000 requests
   - Use Apollo first, then Google Places

2. **Validation Phase:**
   - Place Details: $17 per 1000 requests
   - Only call for businesses that passed initial scrape
   - Batch requests if possible

3. **Detection Phase:**
   - Static Maps (Satellite): $2 per 1000 requests
   - Only download for businesses with verified parking lots
   - Use appropriate zoom level (19 is good balance)

**Total Cost Estimate (per 100 deals):**
- Scraping: ~$3-5
- Validation: ~$2-3
- Detection: ~$0.20
- **Total: ~$5-8 per 100 deals**

---

## Implementation Priority

### Phase 1: Basic Accuracy (80%)
1. Use Place Details `parkingOptions` to verify parking exists
2. Use `geometry.viewport` for building bounds
3. Simple proximity-based association
4. Basic damage detection

### Phase 2: High Accuracy (95%)
1. Add road connectivity detection
2. Improve association scoring
3. Accurate georeferencing for area calculation
4. Better damage detection

### Phase 3: Perfect Accuracy (98%+)
1. Building detection from satellite
2. ML-based association
3. Advanced damage classification
4. User verification UI

---

## Summary

**To achieve 100% accuracy:**

1. **Use Google Places Place Details API** for:
   - Building geometry (exact location & bounds)
   - Parking lot existence verification
   - Business type validation

2. **Use building viewport** (not just address point) for:
   - Satellite image centering
   - Property detection area
   - Association accuracy

3. **Multi-phase validation:**
   - Scrape → Validate existence → Detect & Associate → Evaluate condition → Filter

4. **Georeferencing** for:
   - Accurate area calculation
   - Precise property boundaries
   - Real-world coordinates

5. **Association scoring** based on:
   - Proximity to building
   - Within building viewport
   - Road connectivity
   - Size appropriateness

This approach ensures the property is:
- ✅ Verified to exist (Place Details API)
- ✅ Correctly associated (building geometry + proximity)
- ✅ In bad state (damage detection + filtering)

