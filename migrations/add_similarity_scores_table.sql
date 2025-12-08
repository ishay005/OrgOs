-- Migration: Add similarity_scores table for pre-calculated alignment scores
-- This table stores pre-calculated similarity scores between answer pairs
-- to avoid recalculating them on every API request

CREATE TABLE IF NOT EXISTS similarity_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- The two answers being compared
    answer_a_id UUID NOT NULL REFERENCES attribute_answers(id) ON DELETE CASCADE,
    answer_b_id UUID NOT NULL REFERENCES attribute_answers(id) ON DELETE CASCADE,
    
    -- Pre-calculated similarity score (0.0 to 1.0)
    similarity_score FLOAT NOT NULL CHECK (similarity_score >= 0.0 AND similarity_score <= 1.0),
    
    -- Metadata
    calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Ensure each pair is only stored once (bidirectional uniqueness)
    CONSTRAINT unique_answer_pair UNIQUE (answer_a_id, answer_b_id),
    
    -- Prevent comparing an answer with itself
    CONSTRAINT different_answers CHECK (answer_a_id != answer_b_id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_similarity_scores_answer_a ON similarity_scores(answer_a_id);
CREATE INDEX IF NOT EXISTS idx_similarity_scores_answer_b ON similarity_scores(answer_b_id);
CREATE INDEX IF NOT EXISTS idx_similarity_scores_score ON similarity_scores(similarity_score);

COMMENT ON TABLE similarity_scores IS 'Pre-calculated similarity scores between attribute answer pairs';
COMMENT ON COLUMN similarity_scores.similarity_score IS 'Similarity score from 0.0 (completely different) to 1.0 (identical)';
COMMENT ON COLUMN similarity_scores.calculated_at IS 'When this score was calculated/updated';

