import pytest

from blackboard.config.models import PermissionMode, OperationDecision
from blackboard.guard.guard import SessionGuard


class TestSessionGuard:
    def test_whitelist_allowed(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={"chat": "allowed"})
        assert guard.check("chat") == OperationDecision.ALLOWED

    def test_whitelist_denied(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        assert guard.check("chat") == OperationDecision.DENIED

    def test_whitelist_unlisted(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={"chat": "allowed"})
        assert guard.check("execute_code") == OperationDecision.DENIED

    def test_approval_first(self):
        guard = SessionGuard(mode=PermissionMode.APPROVAL_FIRST, operations={"chat": "allowed"})
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("execute_code") == OperationDecision.REQUIRE_APPROVAL

    def test_approval_first_respects_denied(self):
        guard = SessionGuard(mode=PermissionMode.APPROVAL_FIRST, operations={"file_delete": "denied"})
        assert guard.check("file_delete") == OperationDecision.DENIED

    def test_open_mode(self):
        guard = SessionGuard(mode=PermissionMode.OPEN, operations={"file_delete": "denied"})
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("file_delete") == OperationDecision.DENIED

    def test_agent_override(self):
        guard = SessionGuard(
            mode=PermissionMode.WHITELIST,
            operations={"file_write": "require_approval"},
            per_agent_overrides={"programmer": {"file_write": "allowed"}},
        )
        assert guard.check("file_write") == OperationDecision.REQUIRE_APPROVAL
        assert guard.check("file_write", "programmer") == OperationDecision.ALLOWED

    def test_approval_flow(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={"file_write": "require_approval"})
        decision = guard.check("file_write")
        assert decision == OperationDecision.REQUIRE_APPROVAL
        approvals = list(guard._pending_approvals.keys())
        assert len(approvals) == 1

        aid = approvals[0]
        assert guard.approve(aid)
        assert len(guard._pending_approvals) == 0

    def test_approval_reject(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={"execute_code": "require_approval"})
        guard.check("execute_code")
        aid = list(guard._pending_approvals.keys())[0]
        assert guard.reject(aid)

    def test_update_mode(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        assert guard.check("chat") == OperationDecision.DENIED
        guard.update_mode(PermissionMode.OPEN)
        assert guard.check("chat") == OperationDecision.ALLOWED

    def test_update_operations(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        assert guard.check("chat") == OperationDecision.DENIED
        guard.update_operations({"chat": "allowed"})
        assert guard.check("chat") == OperationDecision.ALLOWED
