import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from blackboard.config.models import ApiType
from blackboard.tools.models import ToolDefinition, ToolRegistry


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379"
    max_connections: int = 10
    stream_maxlen: int = 10000


class RemoteDefault(BaseModel):
    type: str = "local_nas"
    path: str = "/mnt/nas/blackboard/"


class DataConfig(BaseModel):
    dir: str = "/data/sessions"
    warning_threshold_gb: int = 10
    remote_default: RemoteDefault = RemoteDefault()


class SessionConfig(BaseModel):
    approval_timeout_seconds: int = 300
    max_retries: int = 3
    retry_backoff_base: int = 1


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class SystemConfig(BaseModel):
    redis: RedisConfig = RedisConfig()
    data: DataConfig = DataConfig()
    session: SessionConfig = SessionConfig()
    logging: LoggingConfig = LoggingConfig()
    config_agent: str = ""


class AgentEntry(BaseModel):
    provider: str
    display_name: str
    api_key_env: str = ""
    base_url: str = ""
    default_model: str = ""
    models: list = []
    api_type: ApiType = ApiType.OPENAI_COMPATIBLE
    models_path: str = "/models"
    auth_type: str = "bearer"
    default_template: str = ""  # template name in config/agent_templates/ (without .md)


class AgentRegistry(BaseModel):
    agents: dict[str, AgentEntry]


class ProviderPreset(BaseModel):
    display_name: str
    base_url: str = ""
    auth_type: str = "bearer"
    protected: bool = False


class ProviderPresets(BaseModel):
    presets: dict[str, ProviderPreset]


class FallbackModelEntry(BaseModel):
    model_id: str
    display_name: str


class FallbackModelConfig(BaseModel):
    pinned_model_ids: list[str] = []
    fallbacks: dict[str, list[FallbackModelEntry]] = {}


class StrategyStep(BaseModel):
    order: int
    agent_role: str
    action: str


class StrategyTemplate(BaseModel):
    id: str
    name: str
    match_keywords: list[str]
    steps: list[StrategyStep]


class StrategyTemplates(BaseModel):
    templates: list[StrategyTemplate]


class OperationPermissions(BaseModel):
    chat: str = "allowed"
    analyze: str = "allowed"
    search: str = "allowed"
    execute_code: str = "require_approval"
    http_request: str = "require_approval"
    file_read: str = "allowed"
    file_write: str = "require_approval"
    file_delete: str = "denied"


class PermissionPreset(BaseModel):
    description: str = ""
    default_operations: OperationPermissions = OperationPermissions()


class PermissionPresets(BaseModel):
    presets: dict[str, PermissionPreset]
    approval_timeout_seconds: int = 300


class ConfigLoader:
    def __init__(self, config_dir: str | Path = "config"):
        self.config_dir = Path(config_dir)

    def _load_yaml(self, path: str) -> dict[str, Any]:
        with open(self.config_dir / path) as f:
            return yaml.safe_load(f)

    def load_system(self) -> SystemConfig:
        data = self._load_yaml("system.yaml")
        return SystemConfig(**data)

    def load_agent_registry(self) -> AgentRegistry:
        try:
            data = self._load_yaml("agents/registry.yaml")
            if data is None:
                return AgentRegistry(agents={})
            return AgentRegistry(**data)
        except FileNotFoundError:
            return AgentRegistry(agents={})

    def load_provider_presets(self) -> ProviderPresets:
        try:
            data = self._load_yaml("agents/provider_presets.yaml")
            if data is None:
                return ProviderPresets(presets={})
            return ProviderPresets(**data)
        except FileNotFoundError:
            return ProviderPresets(presets={})

    def load_fallback_models(self) -> FallbackModelConfig:
        try:
            data = self._load_yaml("agents/fallback_models.yaml")
            if data is None:
                return FallbackModelConfig()
            return FallbackModelConfig(**data)
        except FileNotFoundError:
            return FallbackModelConfig()

    def load_strategy_templates(self) -> StrategyTemplates:
        try:
            data = self._load_yaml("strategy_templates/templates.yaml")
            return StrategyTemplates(**data)
        except FileNotFoundError:
            return StrategyTemplates(templates=[])

    def load_permission_presets(self) -> PermissionPresets:
        try:
            data = self._load_yaml("permissions/presets.yaml")
            return PermissionPresets(**data)
        except FileNotFoundError:
            return PermissionPresets(presets={})

    def load_tool_registry(self) -> ToolRegistry:
        data = self._load_yaml("tools/registry.yaml")
        tools = {}
        for tool_id, tool_data in data["tools"].items():
            tool_data["name"] = tool_data.get("name", tool_id)
            tools[tool_id] = ToolDefinition(**tool_data)
        return ToolRegistry(**{"tools": tools})

    def _save_yaml(self, path: str, data: dict[str, Any]):
        # Pydantic model_dump() returns enum instances; normalise to plain Python
        # types via JSON round-trip so yaml.safe_dump never sees custom objects.
        safe_data = json.loads(json.dumps(data, default=str))
        full_path = self.config_dir / path
        tmp = full_path.with_suffix(".yaml.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                yaml.safe_dump(safe_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            os.replace(tmp, full_path)  # atomic rename — original file untouched on failure
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    def save_system_config(self, cfg: SystemConfig):
        self._save_yaml("system.yaml", cfg.model_dump())

    def save_agent_registry(self, registry: AgentRegistry):
        data = {"agents": {}}
        for name, entry in registry.agents.items():
            data["agents"][name] = entry.model_dump()
        self._save_yaml("agents/registry.yaml", data)

    def save_strategy_templates(self, templates: StrategyTemplates):
        data = {"templates": [t.model_dump() for t in templates.templates]}
        self._save_yaml("strategy_templates/templates.yaml", data)

    def save_permission_presets(self, presets: PermissionPresets):
        data = presets.model_dump()
        self._save_yaml("permissions/presets.yaml", data)
