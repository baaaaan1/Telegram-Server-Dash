"""SQL Schema for TSD Bot database."""

SCHEMA_SQL = """
-- Audit log table (Task 1)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    command TEXT NOT NULL,
    server_name TEXT,
    action TEXT NOT NULL,
    result TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Metric samples table (Task 2)
CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_name TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_metric_samples_server ON metric_samples(server_name);
CREATE INDEX IF NOT EXISTS idx_metric_samples_timestamp ON metric_samples(timestamp);

-- Server registry cache (optional)
CREATE TABLE IF NOT EXISTS server_registry (
    name TEXT PRIMARY KEY,
    group_name TEXT,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_online INTEGER DEFAULT 0
);
"""
