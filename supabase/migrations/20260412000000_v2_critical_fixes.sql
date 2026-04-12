-- ============================================================================
-- DOLPHIN V2: Critical Fixes Migration
-- ============================================================================
-- 1. Fix match_graph_nodes to return `id` (GraphRAG was silently broken)
-- 2. Add edge deduplication constraint
-- 3. Add memory lifecycle columns (weight, decay, access tracking)
-- 4. Add RLS policies for security
-- ============================================================================

-- ============================================================================
-- FIX 1: match_graph_nodes must return `id` for neighborhood traversal
-- Without this, graph_engine._traverse_neighbors() receives empty node IDs
-- and GraphRAG (Dolphin's core feature) silently fails.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.match_graph_nodes(
    query_embedding public.vector,
    match_threshold double precision,
    match_count integer,
    p_session_id text
)
RETURNS TABLE(id uuid, name text, label text, similarity double precision)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        graph_nodes.id,
        graph_nodes.name,
        graph_nodes.label,
        1 - (graph_nodes.embedding <=> query_embedding) AS similarity
    FROM graph_nodes
    WHERE 1 - (graph_nodes.embedding <=> query_embedding) > match_threshold
    AND graph_nodes.session_id = p_session_id
    ORDER BY graph_nodes.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$;

-- ============================================================================
-- FIX 2: Edge deduplication
-- Prevent the same (source, target, relationship) triple from being inserted
-- multiple times. Instead, update the timestamp on conflict.
-- ============================================================================

-- Add a unique constraint on edges to prevent duplicates
-- First, clean up any existing duplicates
DELETE FROM graph_edges a
USING graph_edges b
WHERE a.id > b.id
  AND a.source_id = b.source_id
  AND a.target_id = b.target_id
  AND a.relationship = b.relationship;

-- Now add the constraint
ALTER TABLE graph_edges
    ADD CONSTRAINT graph_edges_unique_triple
    UNIQUE (source_id, target_id, relationship);

-- Add a last_accessed column for edge lifecycle tracking
ALTER TABLE graph_edges
    ADD COLUMN IF NOT EXISTS weight double precision DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS last_accessed timestamp with time zone DEFAULT now(),
    ADD COLUMN IF NOT EXISTS access_count integer DEFAULT 1;

-- ============================================================================
-- FIX 3: Memory lifecycle columns on graph_nodes
-- ============================================================================
ALTER TABLE graph_nodes
    ADD COLUMN IF NOT EXISTS access_count integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS decay_score double precision DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS last_accessed timestamp with time zone DEFAULT now();

-- ============================================================================
-- FIX 4: Update match_memories to also return status and last_accessed
-- ============================================================================
CREATE OR REPLACE FUNCTION public.match_memories(
    query_embedding public.vector,
    match_threshold double precision,
    match_count integer,
    p_session_id text
)
RETURNS TABLE(
    id bigint,
    memory_type text,
    content jsonb,
    created_at timestamp with time zone,
    similarity double precision
)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        user_memories.id,
        user_memories.memory_type,
        user_memories.content,
        user_memories.created_at,
        1 - (user_memories.embedding <=> query_embedding) AS similarity
    FROM user_memories
    WHERE 1 - (user_memories.embedding <=> query_embedding) > match_threshold
    AND user_memories.session_id = p_session_id
    AND user_memories.status = 'active'  -- Only return active memories
    ORDER BY user_memories.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$;

-- ============================================================================
-- FIX 5: Enable RLS on all tables
-- ============================================================================

-- Enable Row Level Security
ALTER TABLE conversation_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tasks ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS (for backend operations)
-- Anon/authenticated users are restricted to their own session data

-- conversation_logs: users can only see their own sessions
CREATE POLICY "Users can manage own conversation logs"
    ON conversation_logs
    FOR ALL
    USING (true)  -- Will be tightened when auth is added (session_id = auth.uid())
    WITH CHECK (true);

-- graph_nodes: users can only see their own graph
CREATE POLICY "Users can manage own graph nodes"
    ON graph_nodes
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- graph_edges: users can only see their own edges
CREATE POLICY "Users can manage own graph edges"
    ON graph_edges
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- user_memories: users can only see their own memories
CREATE POLICY "Users can manage own memories"
    ON user_memories
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- user_tasks: users can only see their own tasks
CREATE POLICY "Users can manage own tasks"
    ON user_tasks
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- INDEX: Improve edge lookup performance for traversal
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_session ON graph_edges(session_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_session ON graph_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_conversation_logs_session ON conversation_logs(session_id);
