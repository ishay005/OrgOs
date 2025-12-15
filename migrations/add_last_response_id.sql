-- Migration: Add last_response_id for OpenAI Responses API conversation threading
-- This replaces the old conversation_id approach with proper previous_response_id chaining

-- Add last_response_id to daily_sync_sessions
ALTER TABLE daily_sync_sessions 
ADD COLUMN IF NOT EXISTS last_response_id VARCHAR;

-- Add last_response_id to questions_sessions
ALTER TABLE questions_sessions 
ADD COLUMN IF NOT EXISTS last_response_id VARCHAR;

-- Drop the old conversation_id columns if they exist (optional cleanup)
-- ALTER TABLE daily_sync_sessions DROP COLUMN IF EXISTS conversation_id;
-- ALTER TABLE questions_sessions DROP COLUMN IF EXISTS conversation_id;

-- Add comment explaining the purpose
COMMENT ON COLUMN daily_sync_sessions.last_response_id IS 'OpenAI Responses API response ID for conversation threading via previous_response_id';
COMMENT ON COLUMN questions_sessions.last_response_id IS 'OpenAI Responses API response ID for conversation threading via previous_response_id';

