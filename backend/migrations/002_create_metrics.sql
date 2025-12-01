-- Migration: create simple metrics table for dashboard analytics
CREATE TABLE IF NOT EXISTS metrics (
    name TEXT PRIMARY KEY,
    value BIGINT DEFAULT 0
);

-- Initialize counters
INSERT INTO metrics (name, value) VALUES
('invites_sent', 0),
('feedback_sent', 0),
('candidates_total', 0)
ON CONFLICT (name) DO NOTHING;
