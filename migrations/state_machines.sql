-- =============================================================================
-- State Machines Migration
-- Adds: Task state, TaskAlias, TaskMergeProposal, TaskDependencyV2,
--       AlternativeDependencyProposal, PendingDecision
-- =============================================================================

-- Task state enum
DO $$ BEGIN
    CREATE TYPE taskstate AS ENUM ('DRAFT', 'ACTIVE', 'DONE', 'ARCHIVED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Dependency status enum
DO $$ BEGIN
    CREATE TYPE dependencystatus AS ENUM ('PROPOSED', 'CONFIRMED', 'REJECTED', 'REMOVED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Merge proposal status enum
DO $$ BEGIN
    CREATE TYPE mergeproposalstatus AS ENUM ('PROPOSED', 'ACCEPTED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Alternative dependency status enum
DO $$ BEGIN
    CREATE TYPE alternativedepstatus AS ENUM ('PROPOSED', 'ACCEPTED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Pending decision type enum
DO $$ BEGIN
    CREATE TYPE pendingdecisiontype AS ENUM ('TASK_ACCEPTANCE', 'MERGE_CONSENT', 'DEPENDENCY_ACCEPTANCE', 'ALTERNATIVE_DEP_ACCEPTANCE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =============================================================================
-- Extend Tasks Table
-- =============================================================================

-- Add created_by_user_id
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id);

-- Add state column
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state VARCHAR DEFAULT 'ACTIVE';

-- Add state_changed_at
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state_changed_at TIMESTAMP;

-- Add state_reason
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS state_reason TEXT;

-- Update existing tasks to have proper state
UPDATE tasks SET state = 'ACTIVE' WHERE state IS NULL;

-- Set created_by_user_id = owner_user_id for existing tasks
UPDATE tasks SET created_by_user_id = owner_user_id WHERE created_by_user_id IS NULL;

-- =============================================================================
-- TaskAlias Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    alias_title VARCHAR NOT NULL,
    alias_created_by_user_id UUID NOT NULL REFERENCES users(id),
    merged_from_task_id UUID REFERENCES tasks(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_alias_canonical ON task_aliases(canonical_task_id);

-- =============================================================================
-- TaskMergeProposal Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_merge_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    to_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    proposed_by_user_id UUID NOT NULL REFERENCES users(id),
    proposal_reason TEXT NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
    rejected_by_user_id UUID REFERENCES users(id),
    rejected_reason TEXT,
    accepted_by_user_id UUID REFERENCES users(id),
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_merge_proposal_from_task ON task_merge_proposals(from_task_id);
CREATE INDEX IF NOT EXISTS idx_merge_proposal_status ON task_merge_proposals(status);

-- =============================================================================
-- TaskDependencyV2 Table (Enhanced with state machine)
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_dependencies_v2 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    downstream_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    upstream_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
    created_by_user_id UUID NOT NULL REFERENCES users(id),
    accepted_by_user_id UUID REFERENCES users(id),
    accepted_at TIMESTAMP,
    rejected_by_user_id UUID REFERENCES users(id),
    rejected_at TIMESTAMP,
    rejected_reason TEXT,
    removed_by_user_id UUID REFERENCES users(id),
    removed_at TIMESTAMP,
    removed_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dep_v2_downstream ON task_dependencies_v2(downstream_task_id);
CREATE INDEX IF NOT EXISTS idx_dep_v2_upstream ON task_dependencies_v2(upstream_task_id);
CREATE INDEX IF NOT EXISTS idx_dep_v2_status ON task_dependencies_v2(status);

-- =============================================================================
-- AlternativeDependencyProposal Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS alternative_dependency_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_dependency_id UUID NOT NULL REFERENCES task_dependencies_v2(id) ON DELETE CASCADE,
    downstream_task_id UUID NOT NULL REFERENCES tasks(id),
    original_upstream_task_id UUID NOT NULL REFERENCES tasks(id),
    suggested_upstream_task_id UUID NOT NULL REFERENCES tasks(id),
    proposed_by_user_id UUID NOT NULL REFERENCES users(id),
    proposal_reason TEXT NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'PROPOSED',
    rejected_by_user_id UUID REFERENCES users(id),
    rejected_reason TEXT,
    accepted_by_user_id UUID REFERENCES users(id),
    accepted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alt_dep_status ON alternative_dependency_proposals(status);
CREATE INDEX IF NOT EXISTS idx_alt_dep_downstream ON alternative_dependency_proposals(downstream_task_id);

-- =============================================================================
-- PendingDecision Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS pending_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    decision_type VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    description TEXT NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolution VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_decision_user ON pending_decisions(user_id, is_resolved);
CREATE INDEX IF NOT EXISTS idx_pending_decision_entity ON pending_decisions(entity_type, entity_id);

-- =============================================================================
-- Migrate existing dependencies to V2 (as CONFIRMED)
-- =============================================================================

INSERT INTO task_dependencies_v2 (id, downstream_task_id, upstream_task_id, status, created_by_user_id, accepted_at)
SELECT 
    gen_random_uuid(),
    td.task_id,
    td.depends_on_task_id,
    'CONFIRMED',
    t.owner_user_id,
    NOW()
FROM task_dependencies td
JOIN tasks t ON t.id = td.task_id
WHERE NOT EXISTS (
    SELECT 1 FROM task_dependencies_v2 v2 
    WHERE v2.downstream_task_id = td.task_id 
    AND v2.upstream_task_id = td.depends_on_task_id
);

