import logging
from datetime import datetime, timezone

from blackboard.config.models import (
    OperationDecision,
    OperationType,
    PermissionMode,
    ApprovalTimeoutError,
)


logger = logging.getLogger(__name__)


class SessionGuard:
    def __init__(
        self,
        mode: PermissionMode = PermissionMode.WHITELIST,
        operations: dict[str, str] | None = None,
        approval_timeout: int = 300,
        per_agent_overrides: dict[str, dict[str, str]] | None = None,
    ):
        self.mode = mode
        self.operations = operations or {}
        self.approval_timeout = approval_timeout
        self.per_agent_overrides = per_agent_overrides or {}
        self._pending_approvals: dict[str, dict] = {}

    def check(self, operation: str, agent_name: str | None = None) -> OperationDecision:
        self.check_timeouts()
        decision = self._resolve_decision(operation, agent_name)

        if decision == OperationDecision.REQUIRE_APPROVAL:
            approval_id = f"{operation}-{datetime.now(timezone.utc).timestamp()}"
            self._pending_approvals[approval_id] = {
                "operation": operation,
                "agent_name": agent_name,
                "started_at": datetime.now(timezone.utc),
            }
            logger.info("[Guard] Approval required: %s by %s (id=%s)", operation, agent_name, approval_id)

        return decision

    def approve(self, approval_id: str) -> bool:
        if approval_id not in self._pending_approvals:
            return False
        del self._pending_approvals[approval_id]
        return True

    def reject(self, approval_id: str) -> bool:
        if approval_id not in self._pending_approvals:
            return False
        del self._pending_approvals[approval_id]
        return True

    def check_timeouts(self) -> list[str]:
        now = datetime.now(timezone.utc)
        expired = []
        for aid, info in self._pending_approvals.items():
            elapsed = (now - info["started_at"]).total_seconds()
            if elapsed > self.approval_timeout:
                expired.append(aid)
        for aid in expired:
            del self._pending_approvals[aid]
            logger.warning("[Guard] Approval timeout: %s", aid)
        return expired

    def update_operations(self, operations: dict[str, str]):
        self.operations.update(operations)

    def update_mode(self, mode: PermissionMode):
        self.mode = mode

    def _resolve_decision(self, operation: str, agent_name: str | None) -> OperationDecision:
        if agent_name and agent_name in self.per_agent_overrides:
            override = self.per_agent_overrides[agent_name].get(operation)
            if override:
                return OperationDecision(override)

        if self.mode == PermissionMode.OPEN:
            if operation in self.operations:
                declared = OperationDecision(self.operations[operation])
                if declared == OperationDecision.DENIED:
                    return OperationDecision.DENIED
            return OperationDecision.ALLOWED

        if self.mode == PermissionMode.APPROVAL_FIRST:
            if operation in self.operations:
                declared = OperationDecision(self.operations[operation])
                if declared == OperationDecision.DENIED:
                    return OperationDecision.DENIED
                if declared == OperationDecision.ALLOWED:
                    return OperationDecision.ALLOWED
            return OperationDecision.REQUIRE_APPROVAL

        if self.mode == PermissionMode.WHITELIST:
            if operation in self.operations:
                return OperationDecision(self.operations[operation])
            return OperationDecision.DENIED

        return OperationDecision.DENIED
