-- Create scoring_prompts table in worksightdev schema
CREATE TABLE IF NOT EXISTS worksightdev.scoring_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES worksightdev.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    prompt TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_scoring_prompts_user_id ON worksightdev.scoring_prompts(user_id);
CREATE INDEX IF NOT EXISTS idx_scoring_prompts_is_default ON worksightdev.scoring_prompts(user_id, is_default) WHERE is_default = TRUE;

-- Create partial unique index to ensure only one default per user
-- This ensures that for each user, only one prompt can have is_default = TRUE
CREATE UNIQUE INDEX IF NOT EXISTS idx_scoring_prompts_unique_default 
ON worksightdev.scoring_prompts(user_id) 
WHERE is_default = TRUE;

