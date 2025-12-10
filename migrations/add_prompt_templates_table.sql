-- Migration: Add prompt_templates table for dynamic Robin configuration
-- Created: 2025-12-10

CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY,
    mode VARCHAR NOT NULL,
    has_pending BOOLEAN NOT NULL,
    prompt_text TEXT NOT NULL,
    context_config JSON NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR,
    notes TEXT
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_prompt_templates_mode_pending_active 
    ON prompt_templates(mode, has_pending, is_active);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_active 
    ON prompt_templates(is_active);

-- Comments
COMMENT ON TABLE prompt_templates IS 'Dynamic prompt templates for Robin AI assistant';
COMMENT ON COLUMN prompt_templates.mode IS 'Conversation mode: morning_brief, user_question, collect_data';
COMMENT ON COLUMN prompt_templates.has_pending IS 'Whether there are pending questions';
COMMENT ON COLUMN prompt_templates.prompt_text IS 'The actual system prompt text';
COMMENT ON COLUMN prompt_templates.context_config IS 'JSON configuration for context building';
COMMENT ON COLUMN prompt_templates.version IS 'Version number for this mode/pending combination';
COMMENT ON COLUMN prompt_templates.is_active IS 'Whether this version is currently active';

