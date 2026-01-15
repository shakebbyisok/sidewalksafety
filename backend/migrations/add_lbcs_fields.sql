-- Migration: Add LBCS (Land Based Classification Standards) fields to properties table
-- These fields enable reliable property classification using Regrid's standardized codes
-- Run this in Supabase SQL editor with schema set to worksightdev

-- Additional owner details
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_owner2 VARCHAR(255);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_owner_type VARCHAR(50);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_owner_city VARCHAR(100);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_owner_state VARCHAR(10);

-- Additional property details
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_zoning_desc VARCHAR(255);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_num_units NUMERIC(6, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_num_stories NUMERIC(4, 1);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS regrid_struct_style VARCHAR(100);

-- LBCS Activity (What people do: 1000=residential, 2000=commercial, etc.)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_activity NUMERIC(5, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_activity_desc VARCHAR(255);

-- LBCS Function (Economic purpose: 1100=household, 2320=property mgmt, etc.)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_function NUMERIC(5, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_function_desc VARCHAR(255);

-- LBCS Structure (Building type: 1200-1299=multifamily with unit count!)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_structure NUMERIC(5, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_structure_desc VARCHAR(255);

-- LBCS Site (Land development status)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_site NUMERIC(5, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_site_desc VARCHAR(255);

-- LBCS Ownership (1000=private, 4000=public)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_ownership NUMERIC(5, 0);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lbcs_ownership_desc VARCHAR(255);

-- Derived property classification
ALTER TABLE properties ADD COLUMN IF NOT EXISTS property_category VARCHAR(50);

-- Contact enrichment fields (if not already present)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS contact_company VARCHAR(255);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS contact_company_website TEXT;

-- Add index on property_category for filtering
CREATE INDEX IF NOT EXISTS idx_properties_category ON properties(property_category);

-- Add index on lbcs_structure for classification queries
CREATE INDEX IF NOT EXISTS idx_properties_lbcs_structure ON properties(lbcs_structure);

-- Comments for documentation
COMMENT ON COLUMN properties.lbcs_structure IS 'LBCS Structure code: 1200-1299=multifamily (with unit count), 2100=office, 2200=retail, 2700=warehouse, 3500=religious, 4100=medical, 4200=school';
COMMENT ON COLUMN properties.property_category IS 'Derived category: multi_family, retail, office, industrial, institutional, hoa, unknown';
