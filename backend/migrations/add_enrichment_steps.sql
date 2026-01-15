-- Migration: Add enrichment_steps JSONB field to properties table
-- This stores the LLM enrichment process steps for UI visualization

ALTER TABLE worksightdev.properties
ADD COLUMN enrichment_steps JSONB DEFAULT NULL;

-- Add index for querying by enrichment success
CREATE INDEX idx_properties_enrichment_status ON worksightdev.properties (enrichment_status);

-- Add comment for documentation
COMMENT ON COLUMN worksightdev.properties.enrichment_steps IS 'JSON array of enrichment steps taken by LLM enrichment service for UI visualization';
