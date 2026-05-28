import asyncio
from unittest.mock import AsyncMock

import pytest

from blackboard.config.models import OperationDecision, PermissionMode
from blackboard.guard.guard import SessionGuard
from blackboard.host.compiler import NodeType, compile_psc
from blackboard.host.executor import Executor


class TestOperationInference:
    def _make_executor(self, guard=None):
        return Executor(None, guard, "test-session")  # type: ignore[arg-type]

    def test_infer_chat_write(self):
        ex = self._make_executor()
        assert ex._infer_operation("写一个函数") == "chat"
        assert ex._infer_operation("write a function") == "chat"

    def test_infer_chat_generate(self):
        ex = self._make_executor()
        assert ex._infer_operation("生成代码") == "chat"
        assert ex._infer_operation("create a file") == "chat"
        assert ex._infer_operation("build something") == "chat"

    def test_infer_analyze(self):
        ex = self._make_executor()
        assert ex._infer_operation("分析代码性能") == "analyze"
        assert ex._infer_operation("审查这段代码") == "analyze"
        assert ex._infer_operation("review PR") == "analyze"
        assert ex._infer_operation("explain this") == "analyze"

    def test_infer_search(self):
        ex = self._make_executor()
        assert ex._infer_operation("搜索最新资料") == "search"
        assert ex._infer_operation("find the bug") == "search"

    def test_infer_execute_code(self):
        ex = self._make_executor()
        assert ex._infer_operation("执行测试") == "execute_code"
        assert ex._infer_operation("run the script") == "execute_code"

    def test_infer_defaults_to_chat(self):
        ex = self._make_executor()
        assert ex._infer_operation("你好") == "chat"
        assert ex._infer_operation("hello world") == "chat"


class TestConditionEvaluation:
    def _make_executor(self):
        return Executor(None, None, "test")  # type: ignore[arg-type]

    def test_pass_condition_true(self):
        ex = self._make_executor()
        assert ex._evaluate_condition("通过", []) is True
        assert ex._evaluate_condition("pass", []) is True
        assert ex._evaluate_condition("成功", []) is True
        assert ex._evaluate_condition("代码审查通过", []) is True

    def test_fail_condition_false(self):
        ex = self._make_executor()
        assert ex._evaluate_condition("失败", []) is False
        assert ex._evaluate_condition("fail", []) is False
        assert ex._evaluate_condition("评审失败", []) is False

    def test_condition_bug_not_through(self):
        ex = self._make_executor()
        assert ex._evaluate_condition("不通过", []) is True

    def test_unknown_condition_defaults_true(self):
        ex = self._make_executor()
        assert ex._evaluate_condition("unknown", []) is True


class TestExecutorCompilerIntegration:
    def _make_executor(self, guard=None, mq=None):
        return Executor(mq, guard, "test-session")

    def _make_mock_mq(self):
        mq = AsyncMock()
        return mq

    def test_agent_node_dispatch_denied(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        ex = self._make_executor(guard)

        psc = "WORKFLOW: Test\n  PROGRAMMER: 写代码"
        ast = compile_psc(psc)

        class FakeRegistry:
            pass

        results = asyncio.run(ex.execute(ast, FakeRegistry()))
        assert len(results) == 1
        assert "[DENIED]" in results[0]

    def test_multi_agent_chain_denied_all(self):
        guard = SessionGuard(mode=PermissionMode.WHITELIST, operations={})
        ex = self._make_executor(guard)

        psc = "WORKFLOW: Test\n  ARCHITECT: 设计\n  PROGRAMMER: 实现\n  REVIEWER: 审查"
        ast = compile_psc(psc)

        class FakeRegistry:
            pass

        results = asyncio.run(ex.execute(ast, FakeRegistry()))
        assert len(results) == 3
        for r in results:
            assert "[DENIED]" in r
