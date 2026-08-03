ALTER TABLE memory_record ADD COLUMN vector_pk INTEGER;
ALTER TABLE memory_record ADD COLUMN record_json JSON NOT NULL DEFAULT '{}';
CREATE UNIQUE INDEX IF NOT EXISTS ix_memory_record_vector_pk
    ON memory_record (vector_pk);

ALTER TABLE idempotency_record
    ADD COLUMN user_id VARCHAR NOT NULL DEFAULT 'legacy';
ALTER TABLE idempotency_record
    ADD COLUMN fingerprint VARCHAR NOT NULL DEFAULT 'legacy';
ALTER TABLE idempotency_record
    ADD COLUMN response_json JSON NOT NULL DEFAULT '{}';

ALTER TABLE audit_log
    ADD COLUMN user_id VARCHAR NOT NULL DEFAULT 'system';
ALTER TABLE audit_log
    ADD COLUMN metadata_json JSON NOT NULL DEFAULT '{}';
