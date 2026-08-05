PRAGMA foreign_keys = ON;

-- The four existing tables remain owned by migrations 0001 and 0002.
-- This migration adds only the nine non-duplicated backend domain tables.

CREATE TABLE IF NOT EXISTS preference_current (
    preference_id VARCHAR(64) PRIMARY KEY NOT NULL,
    memory_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    preference_key VARCHAR(128) NOT NULL,
    value JSON NOT NULL,
    category VARCHAR(64) NOT NULL,
    scope VARCHAR(32) NOT NULL,
    scope_value VARCHAR(128) NOT NULL,
    polarity VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    evidence_count INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at VARCHAR(35) NOT NULL,
    updated_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_preference_current_memory_id_memory_record
        FOREIGN KEY (memory_id) REFERENCES memory_record (memory_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_preference_current_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT ck_preference_current_evidence_count
        CHECK (evidence_count >= 0),
    CONSTRAINT ck_preference_current_revision
        CHECK (revision >= 1),
    CONSTRAINT ck_preference_current_scope_value
        CHECK (length(trim(scope_value)) > 0),
    CONSTRAINT uq_preference_current_memory_id UNIQUE (memory_id),
    CONSTRAINT uq_preference_current_scope
        UNIQUE (user_id, preference_key, scope, scope_value)
);

CREATE INDEX IF NOT EXISTS ix_preference_current_user_id
    ON preference_current (user_id);
CREATE INDEX IF NOT EXISTS ix_preference_current_status
    ON preference_current (status);
CREATE INDEX IF NOT EXISTS ix_preference_current_updated_at
    ON preference_current (updated_at);

CREATE TABLE IF NOT EXISTS preference_versions (
    version_id VARCHAR(64) PRIMARY KEY NOT NULL,
    preference_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    revision INTEGER NOT NULL,
    value JSON NOT NULL,
    category VARCHAR(64) NOT NULL,
    scope VARCHAR(32) NOT NULL,
    scope_value VARCHAR(128) NOT NULL,
    polarity VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    evidence JSON NOT NULL,
    evidence_count INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    recorded_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_preference_versions_preference_id_preference_current
        FOREIGN KEY (preference_id)
        REFERENCES preference_current (preference_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_preference_versions_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT ck_preference_versions_evidence_count
        CHECK (evidence_count >= 0),
    CONSTRAINT ck_preference_versions_revision CHECK (revision >= 1),
    CONSTRAINT ck_preference_versions_scope_value
        CHECK (length(trim(scope_value)) > 0),
    CONSTRAINT uq_preference_versions_preference_revision
        UNIQUE (preference_id, revision)
);

CREATE INDEX IF NOT EXISTS ix_preference_versions_user_id
    ON preference_versions (user_id);
CREATE INDEX IF NOT EXISTS ix_preference_versions_recorded_at
    ON preference_versions (recorded_at);

CREATE TABLE IF NOT EXISTS knowledge (
    knowledge_id VARCHAR(64) PRIMARY KEY NOT NULL,
    memory_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    current_revision INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at VARCHAR(35) NOT NULL,
    updated_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_knowledge_memory_id_memory_record
        FOREIGN KEY (memory_id) REFERENCES memory_record (memory_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_knowledge_current_revision CHECK (current_revision >= 1),
    CONSTRAINT uq_knowledge_memory_id UNIQUE (memory_id)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_user_id ON knowledge (user_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_status ON knowledge (status);
CREATE INDEX IF NOT EXISTS ix_knowledge_updated_at ON knowledge (updated_at);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    version_id VARCHAR(64) PRIMARY KEY NOT NULL,
    knowledge_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    revision INTEGER NOT NULL,
    title VARCHAR(512) NOT NULL,
    knowledge_type VARCHAR(32) NOT NULL,
    body TEXT NOT NULL,
    steps JSON NOT NULL,
    keywords JSON NOT NULL,
    source_uri TEXT,
    source_reliability FLOAT NOT NULL,
    effective_at VARCHAR(35) NOT NULL,
    recorded_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_knowledge_versions_knowledge_id_knowledge
        FOREIGN KEY (knowledge_id) REFERENCES knowledge (knowledge_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_knowledge_versions_revision CHECK (revision >= 1),
    CONSTRAINT ck_knowledge_versions_source_reliability
        CHECK (source_reliability >= 0.0 AND source_reliability <= 1.0),
    CONSTRAINT uq_knowledge_versions_knowledge_revision
        UNIQUE (knowledge_id, revision)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_versions_user_id
    ON knowledge_versions (user_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_versions_recorded_at
    ON knowledge_versions (recorded_at);

CREATE TABLE IF NOT EXISTS knowledge_relations (
    relation_id VARCHAR(64) PRIMARY KEY NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    source_memory_id VARCHAR(64) NOT NULL,
    target_memory_id VARCHAR(64) NOT NULL,
    relation VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    created_at VARCHAR(35) NOT NULL,
    updated_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_knowledge_relations_source_memory_id_memory_record
        FOREIGN KEY (source_memory_id) REFERENCES memory_record (memory_id),
    CONSTRAINT fk_knowledge_relations_target_memory_id_memory_record
        FOREIGN KEY (target_memory_id) REFERENCES memory_record (memory_id),
    CONSTRAINT ck_knowledge_relations_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT uq_knowledge_relations_edge
        UNIQUE (source_memory_id, target_memory_id, relation)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_relations_user_id
    ON knowledge_relations (user_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_relations_updated_at
    ON knowledge_relations (updated_at);

CREATE TABLE IF NOT EXISTS conflict (
    conflict_id VARCHAR(64) PRIMARY KEY NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    old_memory_id VARCHAR(64) NOT NULL,
    new_memory_id VARCHAR(64) NOT NULL,
    relation VARCHAR(32) NOT NULL,
    confidence FLOAT NOT NULL,
    strategy VARCHAR(32) NOT NULL,
    reason_codes JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at VARCHAR(35) NOT NULL,
    updated_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_conflict_old_memory_id_memory_record
        FOREIGN KEY (old_memory_id) REFERENCES memory_record (memory_id),
    CONSTRAINT fk_conflict_new_memory_id_memory_record
        FOREIGN KEY (new_memory_id) REFERENCES memory_record (memory_id),
    CONSTRAINT ck_conflict_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS ix_conflict_user_id ON conflict (user_id);
CREATE INDEX IF NOT EXISTS ix_conflict_status ON conflict (status);
CREATE INDEX IF NOT EXISTS ix_conflict_updated_at ON conflict (updated_at);

CREATE TABLE IF NOT EXISTS forget_audits (
    audit_id VARCHAR(64) PRIMARY KEY NOT NULL,
    plan_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(64) NOT NULL,
    requested_ids JSON NOT NULL,
    tombstoned_ids JSON NOT NULL,
    failed_items JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    executed_at VARCHAR(35) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_forget_audits_user_id
    ON forget_audits (user_id);
CREATE INDEX IF NOT EXISTS ix_forget_audits_status
    ON forget_audits (status);
CREATE INDEX IF NOT EXISTS ix_forget_audits_executed_at
    ON forget_audits (executed_at);

CREATE TABLE IF NOT EXISTS memory_transitions (
    transition_id VARCHAR(64) PRIMARY KEY NOT NULL,
    memory_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    from_memory_kind VARCHAR(32) NOT NULL,
    to_memory_kind VARCHAR(32) NOT NULL,
    from_status VARCHAR(32) NOT NULL,
    to_status VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    source_event_id VARCHAR(64) NOT NULL,
    transitioned_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_memory_transitions_memory_id_memory_record
        FOREIGN KEY (memory_id) REFERENCES memory_record (memory_id)
);

CREATE INDEX IF NOT EXISTS ix_memory_transitions_user_id
    ON memory_transitions (user_id);
CREATE INDEX IF NOT EXISTS ix_memory_transitions_to_memory_kind
    ON memory_transitions (to_memory_kind);
CREATE INDEX IF NOT EXISTS ix_memory_transitions_to_status
    ON memory_transitions (to_status);
CREATE INDEX IF NOT EXISTS ix_memory_transitions_transitioned_at
    ON memory_transitions (transitioned_at);

CREATE TABLE IF NOT EXISTS vector_mappings (
    mapping_id VARCHAR(64) PRIMARY KEY NOT NULL,
    memory_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    vector_pk BIGINT NOT NULL,
    collection_name VARCHAR(128) NOT NULL,
    model_fingerprint VARCHAR(256) NOT NULL,
    dimension INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at VARCHAR(35) NOT NULL,
    updated_at VARCHAR(35) NOT NULL,
    CONSTRAINT fk_vector_mappings_memory_id_memory_record
        FOREIGN KEY (memory_id) REFERENCES memory_record (memory_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_vector_mappings_vector_pk CHECK (vector_pk >= 0),
    CONSTRAINT ck_vector_mappings_dimension CHECK (dimension > 0),
    CONSTRAINT uq_vector_mappings_memory_id UNIQUE (memory_id),
    CONSTRAINT uq_vector_mappings_collection_vector_pk
        UNIQUE (collection_name, vector_pk)
);

CREATE INDEX IF NOT EXISTS ix_vector_mappings_user_id
    ON vector_mappings (user_id);
CREATE INDEX IF NOT EXISTS ix_vector_mappings_status
    ON vector_mappings (status);
CREATE INDEX IF NOT EXISTS ix_vector_mappings_updated_at
    ON vector_mappings (updated_at);
