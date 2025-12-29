-- Migration: Clean up duplicate parking lots for the same business
-- This removes parking lots that are duplicates (same business, multiple lots)

-- First, identify duplicates: Keep the OLDEST parking lot for each business
WITH duplicates AS (
    SELECT 
        pba.parking_lot_id,
        pba.business_id,
        pl.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY pba.business_id 
            ORDER BY pl.created_at ASC  -- Keep the oldest one
        ) as rn
    FROM parking_lot_business_associations pba
    JOIN parking_lots pl ON pl.id = pba.parking_lot_id
    WHERE pba.is_primary = true
),
lots_to_delete AS (
    SELECT parking_lot_id 
    FROM duplicates 
    WHERE rn > 1  -- Everything except the first (oldest) is a duplicate
)

-- Preview what will be deleted (run this first to check)
SELECT 
    pl.id,
    pl.operator_name,
    pl.address,
    pl.created_at,
    'TO BE DELETED' as status
FROM parking_lots pl
WHERE pl.id IN (SELECT parking_lot_id FROM lots_to_delete);

-- Uncomment below to actually delete (after verifying the preview)
/*
-- Delete property analyses for duplicate lots
DELETE FROM property_analyses 
WHERE parking_lot_id IN (SELECT parking_lot_id FROM lots_to_delete);

-- Delete associations for duplicate lots
DELETE FROM parking_lot_business_associations 
WHERE parking_lot_id IN (SELECT parking_lot_id FROM lots_to_delete);

-- Delete the duplicate parking lots
DELETE FROM parking_lots 
WHERE id IN (SELECT parking_lot_id FROM lots_to_delete);
*/

