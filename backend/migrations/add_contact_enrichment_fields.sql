-- Add Lead Enrichment (Contact) Fields to Properties Table
-- Run this migration to add contact data fields for Apollo enrichment

-- Contact fields
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_first_name VARCHAR(100);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_last_name VARCHAR(100);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_title VARCHAR(255);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS contact_linkedin_url TEXT;
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS enrichment_source VARCHAR(50);
ALTER TABLE worksightdev.properties ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20);

-- Index for filtering by enrichment status
CREATE INDEX IF NOT EXISTS idx_properties_enrichment_status ON worksightdev.properties(enrichment_status);

-- Index for finding properties with contact email
CREATE INDEX IF NOT EXISTS idx_properties_contact_email ON worksightdev.properties(contact_email) WHERE contact_email IS NOT NULL;
