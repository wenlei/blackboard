import pytest
import os
import tempfile

from blackboard.config.loader import ConfigLoader, FallbackModelConfig


@pytest.fixture
def config_dir():
    return "config"


@pytest.fixture
def loader(config_dir):
    return ConfigLoader(config_dir)


class TestSystemConfig:
    def test_load_system(self, loader):
        cfg = loader.load_system()
        assert cfg.redis.url == "redis://localhost:6379"
        assert cfg.data.dir == "/data/sessions"
        assert cfg.session.approval_timeout_seconds == 300

    def test_load_agent_registry_empty(self, tmp_path):
        empty_dir = tmp_path / "config"
        empty_dir.mkdir()
        loader = ConfigLoader(config_dir=str(empty_dir))
        reg = loader.load_agent_registry()
        assert reg.agents == {}

    def test_load_strategy_templates(self, loader):
        tmpl = loader.load_strategy_templates()
        assert len(tmpl.templates) == 4
        ids = [t.id for t in tmpl.templates]
        assert "code_review" in ids
        assert "general" in ids

    def test_load_permission_presets(self, loader):
        presets = loader.load_permission_presets()
        assert "whitelist" in presets.presets
        wh = presets.presets["whitelist"]
        assert wh.default_operations.chat == "allowed"
        assert wh.default_operations.execute_code == "require_approval"
        assert wh.default_operations.file_delete == "denied"

    def test_load_tool_registry(self, loader):
        reg = loader.load_tool_registry()
        assert len(reg.tools) == 7
        assert "read_file" in reg.tools
        tool = reg.tools["read_file"]
        assert tool.operation_type == "file_read"
        assert tool.handler == "filesystem.read"

    def test_tool_filter_by_operation(self, loader):
        reg = loader.load_tool_registry()
        exec_tools = reg.list_by_operation("execute_code")
        assert len(exec_tools) == 2
        names = [t.name for t in exec_tools]
        assert "执行 Python 代码" in names
        assert "执行 Shell 命令" in names

    def test_missing_yaml_rejected(self):
        with pytest.raises(FileNotFoundError):
            loader = ConfigLoader("/nonexistent")
            loader.load_system()


class TestProviderPresets:
    def test_missing_file_returns_empty(self, tmp_path):
        empty_dir = tmp_path / "config" / "agents"
        empty_dir.mkdir(parents=True)
        loader = ConfigLoader(config_dir=str(tmp_path / "config"))
        presets = loader.load_provider_presets()
        assert presets.presets == {}


class TestFallbackModels:
    def test_missing_file_returns_empty(self, tmp_path):
        empty_dir = tmp_path / "config" / "agents"
        empty_dir.mkdir(parents=True)
        loader = ConfigLoader(config_dir=str(tmp_path / "config"))
        cfg = loader.load_fallback_models()
        assert cfg.fallbacks == {}
        assert cfg.pinned_model_ids == []
