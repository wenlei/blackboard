from enum import Enum


class ApiType(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"


class ModelType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    EMBEDDING = "embedding"
    VISION = "vision"
    UNKNOWN = "unknown"


class InitStatusEnum(str, Enum):
    NOT_CONFIGURED = "not_configured"
    KEY_SAVED = "key_saved"
    MODELS_SYNCED = "models_synced"
    READY = "ready"


class PermissionMode(str, Enum):
    WHITELIST = "whitelist"
    APPROVAL_FIRST = "approval_first"
    OPEN = "open"


class OperationType(str, Enum):
    CHAT = "chat"
    ANALYZE = "analyze"
    SEARCH = "search"
    EXECUTE_CODE = "execute_code"
    HTTP_REQUEST = "http_request"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"


class OperationDecision(str, Enum):
    ALLOWED = "allowed"
    REQUIRE_APPROVAL = "require_approval"
    DENIED = "denied"


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


class RemoteType(str, Enum):
    LOCAL_NAS = "local_nas"
    S3 = "s3"
    SFTP = "sftp"


class BlackboardError(Exception):
    status_code: int = 500
    message: str = "Internal error"


class AgentRegistryError(BlackboardError):
    status_code = 404
    message = "Agent not found in registry"


class MissingApiKeyError(BlackboardError):
    status_code = 422
    message = "API key not configured for this agent"


class InvalidApiKeyError(BlackboardError):
    status_code = 502
    message = "LLM API rejected credentials (401/403)"


class SandboxExecutionError(BlackboardError):
    status_code = 500
    message = "Code execution failed in sandbox"


class StorageQuotaError(BlackboardError):
    status_code = 507
    message = "Storage quota exceeded"


class ArchiveFailedError(BlackboardError):
    status_code = 500
    message = "Archive operation failed"


class ApprovalTimeoutError(BlackboardError):
    status_code = 408
    message = "Approval timed out, auto-denied"
