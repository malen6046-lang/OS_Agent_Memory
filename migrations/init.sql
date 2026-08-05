PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memory_record (
    memory_id VARCHAR PRIMARY KEY NOT NULL,
    user_id VARCHAR NOT NULL,
    memory_kind VARCHAR NOT NULL,
    content_text TEXT NOT NULL,
    status VARCHAR NOT NULL,
    confidence FLOAT NOT NULL
        CONSTRAINT ck_memory_record_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    revision INTEGER NOT NULL
        CONSTRAINT ck_memory_record_revision
        CHECK (revision >= 1),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_memory_record_user_id
    ON memory_record (user_id);
CREATE INDEX IF NOT EXISTS ix_memory_record_memory_kind
    ON memory_record (memory_kind);
CREATE INDEX IF NOT EXISTS ix_memory_record_status
    ON memory_record (status);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id VARCHAR PRIMARY KEY NOT NULL,
    operation VARCHAR NOT NULL,
    operator VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_log_operation
    ON audit_log (operation);
CREATE INDEX IF NOT EXISTS ix_audit_log_request_id
    ON audit_log (request_id);

CREATE TABLE IF NOT EXISTS idempotency_record (
    idempotency_key VARCHAR PRIMARY KEY NOT NULL,
    operation VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_idempotency_record_operation
    ON idempotency_record (operation);
CREATE INDEX IF NOT EXISTS ix_idempotency_record_request_id
    ON idempotency_record (request_id);

CREATE TABLE IF NOT EXISTS evaluation_run (
    run_id VARCHAR PRIMARY KEY NOT NULL,
    metric_name VARCHAR NOT NULL,
    value FLOAT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_evaluation_run_metric_name
    ON evaluation_run (metric_name);
