from enum import Enum


class Source(str, Enum):
    TOOL_RESULT = "tool_result"
    USER_BEHAVIOR = "user_behavior"
    MANUAL_CONFIG = "manual_config"
    CROSS_SCENE = "cross_scene"


class MemoryKind(str, Enum):
    PREFERENCE = "preference"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class MemorySubtype(str, Enum):
    OUTPUT_STYLE = "output_style"
    OPERATION_HABIT = "operation_habit"
    SECURITY_POLICY = "security_policy"
    WORKFLOW = "workflow"
    CASE = "case"
    TEMPLATE = "template"
    FACT = "fact"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    PENDING_REVIEW = "pending_review"
    EXPIRED = "expired"
    TOMBSTONED = "tombstoned"


class PreferenceCategory(str, Enum):
    OPERATION_HABIT = "operation_habit"
    OUTPUT_STYLE = "output_style"
    TOOL_CHOICE = "tool_choice"
    SAFETY_POLICY = "safety_policy"


class PreferenceScope(str, Enum):
    GLOBAL = "global"
    SCENE = "scene"
    TOOL = "tool"


class PreferencePolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ConflictRelation(str, Enum):
    DUPLICATE = "duplicate"
    SUPPORT = "support"
    EXTEND = "extend"
    REPLACE = "replace"
    CONTRADICT = "contradict"
    UNRELATED = "unrelated"


class ConflictStrategy(str, Enum):
    KEEP_OLD = "keep_old"
    KEEP_NEW = "keep_new"
    MERGE = "merge"
    MANUAL_REVIEW = "manual_review"


class Provider(str, Enum):
    KYLIN = "kylin"
    FALLBACK = "fallback"
    DETERMINISTIC_TEST = "deterministic_test"


class DistanceMetric(str, Enum):
    COSINE = "cosine"
    INNER_PRODUCT = "inner_product"
    L2 = "l2"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvaluationType(str, Enum):
    PREFERENCE = "preference"
    RETRIEVAL = "retrieval"
    CONFLICT = "conflict"
    SECURITY = "security"
    FORGET = "forget"
    PERFORMANCE = "performance"


class EvaluationStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationStatus(str, Enum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class ItemOutcome(str, Enum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    CONFLICT_PENDING = "conflict_pending"
    FAILED = "failed"


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED_SCOPE = "UNAUTHORIZED_SCOPE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    MEMORY_CONFLICT_PENDING = "MEMORY_CONFLICT_PENDING"
    EMBEDDING_DIMENSION_MISMATCH = "EMBEDDING_DIMENSION_MISMATCH"
    EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE"
    EMBEDDING_INIT_FAILED = "EMBEDDING_INIT_FAILED"
    EMBEDDING_RUNTIME_FAILED = "EMBEDDING_RUNTIME_FAILED"
    EMBEDDING_UNKNOWN_ERROR = "EMBEDDING_UNKNOWN_ERROR"
    VECTOR_PROVIDER_UNAVAILABLE = "VECTOR_PROVIDER_UNAVAILABLE"
    VECTOR_CONFIG_INVALID = "VECTOR_CONFIG_INVALID"
    VECTOR_STORAGE_FAILED = "VECTOR_STORAGE_FAILED"
    VECTOR_METADATA_INVALID = "VECTOR_METADATA_INVALID"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    SENSITIVE_CONTENT_BLOCKED = "SENSITIVE_CONTENT_BLOCKED"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
