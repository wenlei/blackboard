import tempfile

import pytest

from blackboard.host.compiler import compile_psc, NodeType
from blackboard.config.loader import ConfigLoader
from blackboard.host.strategy import StrategyGenerator


SAMPLE_PSC = """WORKFLOW: 代码审查
  ARCHITECT: 分析代码结构
  PROGRAMMER: 编写代码
  REVIEWER: 审查代码质量
    IF 通过:
      → RETURN
    ELSE:
      PROGRAMMER: 修改代码
      REVIEWER: 重新审查"""


class TestCompiler:
    def test_compile_agent_nodes(self):
        psc = "WORKFLOW: Test\n  PROGRAMMER: 写代码"
        ast = compile_psc(psc)
        assert ast.node_type == NodeType.AGENT
        assert ast.agent == "PROGRAMMER"
        assert ast.action == "写代码"

    def test_compile_multi_agent(self):
        psc = "WORKFLOW: Test\n  ARCHITECT: 设计\n  PROGRAMMER: 实现"
        ast = compile_psc(psc)
        assert ast.node_type == NodeType.AGENT
        assert ast.next_node.node_type == NodeType.AGENT
        assert ast.next_node.agent == "PROGRAMMER"

    def test_compile_branch(self):
        ast = compile_psc(SAMPLE_PSC)
        assert ast.node_type == NodeType.AGENT  # ARCHITECT
        branch = ast.next_node.next_node.next_node  # ARCH→PROG→REVIEWER→BRANCH
        assert branch.node_type == NodeType.BRANCH
        assert branch.condition == "通过"
        assert branch.next_true.node_type == NodeType.RETURN
        assert branch.next_false.node_type == NodeType.AGENT

    def test_compile_return(self):
        psc = "WORKFLOW: T\n  AGENT: do\n  → RETURN"
        ast = compile_psc(psc)
        assert ast.node_type == NodeType.AGENT
        assert ast.next_node.node_type == NodeType.RETURN

    def test_compile_ignores_workflow_line(self):
        psc = "WORKFLOW: MyFlow\n  AGENT: action"
        ast = compile_psc(psc)
        assert ast.action == "action"


class TestStrategyGenerator:
    @pytest.fixture
    def generator(self):
        loader = ConfigLoader("config")
        templates = loader.load_strategy_templates()
        return StrategyGenerator(templates)

    def test_match_code_review(self, generator):
        result = generator.generate(
            "帮我审查一下这段代码", {"架构师": "dp", "程序员": "cl", "审查者": "op"}
        )
        assert "WORKFLOW" in result

    def test_match_write_code(self, generator):
        result = generator.generate(
            "写一个排序函数", {"架构师": "dp", "程序员": "cl", "审查者": "op"}
        )
        assert "协作编码" in result

    def test_match_analyze(self, generator):
        result = generator.generate(
            "分析一下为什么这段代码慢", {"架构师": "dp", "审查者": "op"}
        )
        assert "分析讨论" in result

    def test_general_fallback(self, generator):
        result = generator.generate(
            "今天天气怎么样", {"助手": "dp"}
        )
        assert "WORKFLOW" in result
