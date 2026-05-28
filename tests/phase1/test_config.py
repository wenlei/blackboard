import pytest
import yaml
from pydantic import ValidationError

from blackboard.config.loader import (
    AgentRegistry,
    ConfigLoader,
    PermissionPresets,
    StrategyTemplates,
    SystemConfig,
)


class TestSystemConfig:
    def test_load_system_yaml(self, valid_system_yaml):
        loader = ConfigLoader(config_dir=valid_system_yaml)
        cfg = loader.load_system()
        assert isinstance(cfg, SystemConfig)
        assert cfg.redis.url == "redis://localhost:6379"
        assert cfg.redis.max_connections == 10
        assert cfg.data.dir == "/data/sessions"
        assert cfg.session.approval_timeout_seconds == 300
        assert cfg.session.max_retries == 3
        assert cfg.config_agent == ""
        assert cfg.logging.level == "INFO"

    def test_load_system_from_project_config(self, config_dir):
        loader = ConfigLoader(config_dir=config_dir)
        cfg = loader.load_system()
        assert isinstance(cfg, SystemConfig)
        assert cfg.redis.url == "redis://localhost:6379"

    def test_system_config_defaults(self):
        cfg = SystemConfig()
        assert cfg.redis.url == "redis://localhost:6379"
        assert cfg.redis.max_connections == 10
        assert cfg.data.dir == "/data/sessions"
        assert cfg.session.approval_timeout_seconds == 300
        assert cfg.config_agent == ""
        assert cfg.logging.level == "INFO"

    def test_invalid_yaml_type_rejected(self, temp_config_dir):
        bad_content = {
            "redis": {"url": "redis://localhost:6379", "max_connections": "not-an-int"},
        }
        path = temp_config_dir / "system.yaml"
        path.write_text(yaml.dump(bad_content))
        loader = ConfigLoader(config_dir=temp_config_dir)
        with pytest.raises((ValidationError, TypeError, ValueError)):
            loader.load_system()

    def test_invalid_yaml_syntax_rejected(self, temp_config_dir):
        path = temp_config_dir / "system.yaml"
        path.write_text("redis: [unclosed")
        loader = ConfigLoader(config_dir=temp_config_dir)
        with pytest.raises((yaml.YAMLError, ValidationError, TypeError, ValueError)):
            loader.load_system()

    def test_invalid_nested_type_rejected(self, temp_config_dir):
        bad_content = {
            "redis": {"url": "redis://localhost:6379"},
            "session": {"max_retries": "not-an-int"},
        }
        path = temp_config_dir / "system.yaml"
        path.write_text(yaml.dump(bad_content))
        loader = ConfigLoader(config_dir=temp_config_dir)
        with pytest.raises((ValidationError, TypeError, ValueError)):
            loader.load_system()

    def test_all_sub_configs_present(self, valid_system_yaml):
        loader = ConfigLoader(config_dir=valid_system_yaml)
        cfg = loader.load_system()
        assert cfg.redis.stream_maxlen == 10000
        assert cfg.data.warning_threshold_gb == 10
        assert cfg.data.remote_default.type == "local_nas"
        assert cfg.session.retry_backoff_base == 1
        assert cfg.config_agent == ""


class TestAgentRegistry:
    def test_load_agent_registry(self, valid_agent_registry_yaml):
        loader = ConfigLoader(config_dir=valid_agent_registry_yaml)
        reg = loader.load_agent_registry()
        assert isinstance(reg, AgentRegistry)
        assert "deepseek" in reg.agents
        assert "claude" in reg.agents
        assert "openai" in reg.agents

    def test_agent_entry_fields(self, valid_agent_registry_yaml):
        loader = ConfigLoader(config_dir=valid_agent_registry_yaml)
        reg = loader.load_agent_registry()
        ds = reg.agents["deepseek"]
        assert ds.provider == "deepseek"
        assert ds.api_key_env == "DEEPSEEK_API_KEY"
        assert ds.default_model == "deepseek-chat"
        assert len(ds.models) == 2
        assert "deepseek-r1" in ds.models

    def test_agent_registry_empty(self, tmp_path):
        empty_dir = tmp_path / "config"
        empty_dir.mkdir()
        loader = ConfigLoader(config_dir=str(empty_dir))
        reg = loader.load_agent_registry()
        assert reg.agents == {}

    def test_claude_has_multiple_models(self, valid_agent_registry_yaml):
        loader = ConfigLoader(config_dir=valid_agent_registry_yaml)
        reg = loader.load_agent_registry()
        assert "claude-opus-4-20250514" in reg.agents["claude"].models


class TestStrategyTemplates:
    def test_load_templates(self, valid_templates_yaml):
        loader = ConfigLoader(config_dir=valid_templates_yaml)
        tmpl = loader.load_strategy_templates()
        assert isinstance(tmpl, StrategyTemplates)
        assert len(tmpl.templates) == 4

    def test_template_ids(self, valid_templates_yaml):
        loader = ConfigLoader(config_dir=valid_templates_yaml)
        tmpl = loader.load_strategy_templates()
        ids = {t.id for t in tmpl.templates}
        assert ids == {"code_review", "write_code", "analyze", "general"}

    def test_template_match_keywords(self, valid_templates_yaml):
        loader = ConfigLoader(config_dir=valid_templates_yaml)
        tmpl = loader.load_strategy_templates()
        code_review = next(t for t in tmpl.templates if t.id == "code_review")
        assert "代码" in code_review.match_keywords
        assert "review" in code_review.match_keywords

    def test_template_steps_have_order(self, valid_templates_yaml):
        loader = ConfigLoader(config_dir=valid_templates_yaml)
        tmpl = loader.load_strategy_templates()
        write_code = next(t for t in tmpl.templates if t.id == "write_code")
        orders = [s.order for s in write_code.steps]
        assert orders == sorted(orders)

    def test_general_template_no_keywords(self, valid_templates_yaml):
        loader = ConfigLoader(config_dir=valid_templates_yaml)
        tmpl = loader.load_strategy_templates()
        general = next(t for t in tmpl.templates if t.id == "general")
        assert general.match_keywords == []

    def test_load_templates_from_project(self, config_dir):
        loader = ConfigLoader(config_dir=config_dir)
        tmpl = loader.load_strategy_templates()
        assert len(tmpl.templates) == 4


class TestPermissionPresets:
    def test_load_presets(self, valid_presets_yaml):
        loader = ConfigLoader(config_dir=valid_presets_yaml)
        p = loader.load_permission_presets()
        assert isinstance(p, PermissionPresets)
        assert "whitelist" in p.presets
        assert "approval_first" in p.presets
        assert "open" in p.presets
        assert p.approval_timeout_seconds == 300

    def test_whitelist_preset_defaults(self, valid_presets_yaml):
        loader = ConfigLoader(config_dir=valid_presets_yaml)
        p = loader.load_permission_presets()
        wl = p.presets["whitelist"]
        assert wl.default_operations.chat == "allowed"
        assert wl.default_operations.file_delete == "denied"
        assert wl.default_operations.execute_code == "require_approval"

    def test_approval_first_all_require(self, valid_presets_yaml):
        loader = ConfigLoader(config_dir=valid_presets_yaml)
        p = loader.load_permission_presets()
        af = p.presets["approval_first"]
        assert af.default_operations.chat == "require_approval"
        assert af.default_operations.analyze == "require_approval"

    def test_open_preset(self, valid_presets_yaml):
        loader = ConfigLoader(config_dir=valid_presets_yaml)
        p = loader.load_permission_presets()
        op = p.presets["open"]
        assert op.default_operations.chat == "allowed"
        assert op.default_operations.execute_code == "allowed"
        assert op.default_operations.file_delete == "denied"

    def test_load_presets_from_project(self, config_dir):
        loader = ConfigLoader(config_dir=config_dir)
        p = loader.load_permission_presets()
        assert len(p.presets) == 3
