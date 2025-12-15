-- Migration: Add Robin v2 architecture tables and columns
-- Date: 2024-12-14

-- Add conversation_id to daily_sync_sessions (for future OpenAI Assistants API)
ALTER TABLE daily_sync_sessions 
ADD COLUMN IF NOT EXISTS conversation_id VARCHAR;

-- Create questions_sessions table for Questions mode tracking
CREATE TABLE IF NOT EXISTS questions_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    thread_id UUID NOT NULL REFERENCES chat_threads(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    conversation_id VARCHAR
);

-- Create index for active session lookup
CREATE INDEX IF NOT EXISTS idx_questions_session_active 
ON questions_sessions(user_id, is_active);

