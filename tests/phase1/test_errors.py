import pytest

from blackboard.config.models import (
    AgentRegistryError,
    ApprovalTimeoutError,
    ArchiveFailedError,
    BlackboardError,
    InvalidApiKeyError,
    MissingApiKeyError,
    OperationDecision,
    OperationType,
    PermissionMode,
    RemoteType,
    SandboxExecutionError,
    SessionStatus,
    StorageQuotaError,
)


class TestErrorTypes:
    def test_agent_registry_error(self):
        err = AgentRegistryError("unknown-agent")
        assert err.status_code == 404
        assert "not found" in str(err.message).lower()
        with pytest.raises(AgentRegistryError) as exc_info:
            raise AgentRegistryError("unknown-agent")
        assert exc_info.value.status_code == 404

    def test_missing_api_key_error(self):
        err = MissingApiKeyError("DEEPSEEK_API_KEY")
        assert err.status_code == 422
        with pytest.raises(MissingApiKeyError) as exc_info:
            raise MissingApiKeyError("DEEPSEEK_API_KEY")
        assert exc_info.value.status_code == 422

    def test_invalid_api_key_error(self):
        err = InvalidApiKeyError()
        assert err.status_code == 502
        with pytest.raises(InvalidApiKeyError) as exc_info:
            raise InvalidApiKeyError()
        assert exc_info.value.status_code == 502

    def test_sandbox_execution_error(self):
        err = SandboxExecutionError("syntax error in user code")
        assert err.status_code == 500
        with pytest.raises(SandboxExecutionError) as exc_info:
            raise SandboxExecutionError("syntax error")
        assert exc_info.value.status_code == 500

    def test_storage_quota_error(self):
        err = StorageQuotaError()
        assert err.status_code == 507
        with pytest.raises(StorageQuotaError) as exc_info:
            raise StorageQuotaError()
        assert exc_info.value.status_code == 507

    def test_archive_failed_error(self):
        err = ArchiveFailedError("NAS unreachable")
        assert err.status_code == 500
        with pytest.raises(ArchiveFailedError) as exc_info:
            raise ArchiveFailedError("NAS unreachable")
        assert exc_info.value.status_code == 500

    def test_approval_timeout_error(self):
        err = ApprovalTimeoutError()
        assert err.status_code == 408
        with pytest.raises(ApprovalTimeoutError) as exc_info:
            raise ApprovalTimeoutError()
        assert exc_info.value.status_code == 408

    def test_all_errors_inherit_from_blackboard_error(self):
        error_classes = [
            AgentRegistryError,
            MissingApiKeyError,
            InvalidApiKeyError,
            SandboxExecutionError,
            StorageQuotaError,
            ArchiveFailedError,
            ApprovalTimeoutError,
        ]
        for cls in error_classes:
            assert issubclass(cls, BlackboardError), (
                f"{cls.__name__} should inherit from BlackboardError"
            )

    def test_error_status_codes_match_architecture_doc(self):
        expected = {
            AgentRegistryError: 404,
            MissingApiKeyError: 422,
            InvalidApiKeyError: 502,
            SandboxExecutionError: 500,
            StorageQuotaError: 507,
            ArchiveFailedError: 500,
            ApprovalTimeoutError: 408,
        }
        for cls, status in expected.items():
            err = cls("test" if cls != MissingApiKeyError else "TEST_KEY")
            assert err.status_code == status, (
                f"{cls.__name__} should have status {status}, got {err.status_code}"
            )


class TestEnums:
    def test_permission_mode_values(self):
        assert PermissionMode.WHITELIST.value == "whitelist"
        assert PermissionMode.APPROVAL_FIRST.value == "approval_first"
        assert PermissionMode.OPEN.value == "open"

    def test_operation_type_values(self):
        assert OperationType.CHAT.value == "chat"
        assert OperationType.EXECUTE_CODE.value == "execute_code"
        assert OperationType.FILE_DELETE.value == "file_delete"
        assert {op.value for op in OperationType} == {
            "chat",
            "analyze",
            "search",
            "execute_code",
            "http_request",
            "file_read",
            "file_write",
            "file_delete",
        }

    def test_operation_decision_values(self):
        assert OperationDecision.ALLOWED.value == "allowed"
        assert OperationDecision.REQUIRE_APPROVAL.value == "require_approval"
        assert OperationDecision.DENIED.value == "denied"

    def test_session_status_values(self):
        assert SessionStatus.CREATED.value == "created"
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.CLOSED.value == "closed"
        assert SessionStatus.ARCHIVED.value == "archived"

    def test_remote_type_values(self):
        assert RemoteType.LOCAL_NAS.value == "local_nas"
        assert RemoteType.S3.value == "s3"
        assert RemoteType.SFTP.value == "sftp"
