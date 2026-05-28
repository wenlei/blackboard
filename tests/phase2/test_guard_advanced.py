import time
from datetime import datetime, timezone, timedelta

import pytest

from blackboard.config.models import PermissionMode, OperationDecision
from blackboard.guard.guard import SessionGuard


class TestApprovalTimeout:
    def test_timeout_expired_approvals(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=1,
        )
        guard.check("chat")

        time.sleep(1.1)

        expired = guard.check_timeouts()
        assert len(expired) == 1
        assert len(guard._pending_approvals) == 0

    def test_timeout_non_expired(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=300,
        )
        guard.check("chat")

        expired = guard.check_timeouts()
        assert len(expired) == 0
        assert len(guard._pending_approvals) == 1

    def test_timeout_multiple_expired(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=1,
        )
        guard.check("chat")
        guard.check("analyze")
        guard.check("search")

        time.sleep(1.1)

        expired = guard.check_timeouts()
        assert len(expired) == 3
        assert len(guard._pending_approvals) == 0

    def test_timeout_mixed_expired_and_active(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=1,
        )
        guard.check("chat")
        assert len(guard._pending_approvals) == 1

        time.sleep(1.1)

        guard.check("analyze")

        assert len(guard._pending_approvals) == 1


class TestApproveRejectEdgeCases:
    def test_approve_nonexistent(self):
        guard = SessionGuard()
        assert guard.approve("fake-id") is False

    def test_reject_nonexistent(self):
        guard = SessionGuard()
        assert guard.reject("fake-id") is False

    def test_approve_after_timeout(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=1,
        )
        guard.check("chat")
        approval_id = list(guard._pending_approvals.keys())[0]

        time.sleep(1.1)
        guard.check_timeouts()

        assert guard.approve(approval_id) is False

    def test_reject_after_timeout(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            approval_timeout=1,
        )
        guard.check("chat")
        approval_id = list(guard._pending_approvals.keys())[0]

        time.sleep(1.1)
        guard.check_timeouts()

        assert guard.reject(approval_id) is False

    def test_approve_then_check_cleared(self):
        guard = SessionGuard(mode=PermissionMode.APPROVAL_FIRST)
        guard.check("chat")
        approval_id = list(guard._pending_approvals.keys())[0]

        assert guard.approve(approval_id) is True
        assert len(guard._pending_approvals) == 0

    def test_reject_then_check_cleared(self):
        guard = SessionGuard(mode=PermissionMode.APPROVAL_FIRST)
        guard.check("chat")
        approval_id = list(guard._pending_approvals.keys())[0]

        assert guard.reject(approval_id) is True
        assert len(guard._pending_approvals) == 0

    def test_approve_then_check_again_requires_new_approval(self):
        guard = SessionGuard(mode=PermissionMode.APPROVAL_FIRST)
        result1 = guard.check("chat")
        assert result1 == OperationDecision.REQUIRE_APPROVAL

        approval_id = list(guard._pending_approvals.keys())[0]
        guard.approve(approval_id)

        result2 = guard.check("chat")
        assert result2 == OperationDecision.REQUIRE_APPROVAL
        assert len(guard._pending_approvals) == 1


class TestEdgeCases:
    def test_per_agent_override_multiple_agents(self):
        guard = SessionGuard(
            mode=PermissionMode.WHITELIST,
            operations={"file_write": "require_approval"},
            per_agent_overrides={
                "programmer": {"file_write": "allowed"},
                "reviewer": {"file_write": "denied"},
            },
        )
        assert guard.check("file_write", "programmer") == OperationDecision.ALLOWED
        assert guard.check("file_write", "reviewer") == OperationDecision.DENIED
        assert guard.check("file_write") == OperationDecision.REQUIRE_APPROVAL
        assert guard.check("file_write", "architect") == OperationDecision.REQUIRE_APPROVAL

    def test_override_does_not_affect_other_operations(self):
        guard = SessionGuard(
            mode=PermissionMode.WHITELIST,
            operations={"chat": "allowed", "file_write": "denied"},
            per_agent_overrides={"programmer": {"file_write": "allowed"}},
        )
        assert guard.check("chat", "programmer") == OperationDecision.ALLOWED
        assert guard.check("file_write", "programmer") == OperationDecision.ALLOWED
        assert guard.check("file_write") == OperationDecision.DENIED

    def test_open_mode_respects_denied_list(self):
        guard = SessionGuard(
            mode=PermissionMode.OPEN,
            operations={"file_delete": "denied"},
        )
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("execute_code") == OperationDecision.ALLOWED
        assert guard.check("file_write") == OperationDecision.ALLOWED
        assert guard.check("file_delete") == OperationDecision.DENIED

    def test_approval_first_allowed_ops_bypass(self):
        guard = SessionGuard(
            mode=PermissionMode.APPROVAL_FIRST,
            operations={"chat": "allowed", "analyze": "allowed"},
        )
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("analyze") == OperationDecision.ALLOWED
        assert guard.check("search") == OperationDecision.REQUIRE_APPROVAL

    def test_update_mode_preserves_operations(self):
        guard = SessionGuard(
            mode=PermissionMode.WHITELIST,
            operations={"chat": "allowed", "execute_code": "require_approval"},
        )
        assert guard.check("chat") == OperationDecision.ALLOWED

        guard.update_mode(PermissionMode.OPEN)
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("execute_code") == OperationDecision.ALLOWED

        guard.update_mode(PermissionMode.APPROVAL_FIRST)
        assert guard.check("chat") == OperationDecision.ALLOWED

    def test_update_operations_adds_new(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        assert guard.check("chat") == OperationDecision.DENIED

        guard.update_operations({"chat": "allowed"})
        assert guard.check("chat") == OperationDecision.ALLOWED
        assert guard.check("search") == OperationDecision.DENIED

    def test_default_constructor_values(self):
        guard = SessionGuard()
        assert guard.mode == PermissionMode.WHITELIST
        assert guard.operations == {}
        assert guard.approval_timeout == 300
        assert guard.per_agent_overrides == {}
        assert len(guard._pending_approvals) == 0
