import os
from pathlib import Path

import pytest
import yaml


def _redis_available() -> bool:
    try:
        import redis.asyncio as redis

        async def _ping():
            client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
            try:
                await client.ping()
                return True
            except Exception:
                return False
            finally:
                await client.aclose()

        import asyncio

        return asyncio.run(_ping())
    except Exception:
        return False


redis_available = _redis_available()
requires_redis = pytest.mark.skipif(
    not redis_available or not os.environ.get("WITH_REDIS"), reason="Redis not available"
)


@pytest.fixture(scope="session")
def project_root():
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def config_dir(project_root):
    return project_root / "config"


@pytest.fixture(scope="session")
def fixtures_dir(project_root):
    return project_root / "dev" / "test-sample" / "fixtures"


@pytest.fixture(scope="session")
def fixtures_data(fixtures_dir):
    data = {}
    for name in ["session_config.json", "permissions_config.json", "strategy_template.json"]:
        path = fixtures_dir / name
        if path.exists():
            import json

            data[name] = json.loads(path.read_text())
    return data


@pytest.fixture
def temp_config_dir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def valid_system_yaml(temp_config_dir):
    content = {
        "redis": {"url": "redis://localhost:6379", "max_connections": 10, "stream_maxlen": 10000},
        "data": {
            "dir": "/data/sessions",
            "warning_threshold_gb": 10,
            "remote_default": {"type": "local_nas", "path": "/mnt/nas/blackboard/"},
        },
        "session": {"approval_timeout_seconds": 300, "max_retries": 3, "retry_backoff_base": 1},
        "logging": {"level": "INFO", "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        "config_agent": "",
    }
    path = temp_config_dir / "system.yaml"
    path.write_text(yaml.dump(content))
    return temp_config_dir


@pytest.fixture
def valid_agent_registry_yaml(temp_config_dir):
    content = {
        "agents": {
            "deepseek": {
                "provider": "deepseek",
                "display_name": "DeepSeek",
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url": "https://api.deepseek.com/v1",
                "default_model": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-r1"],
            },
            "claude": {
                "provider": "anthropic",
                "display_name": "Claude",
                "api_key_env": "ANTHROPIC_API_KEY",
                "base_url": "https://api.anthropic.com/v1",
                "default_model": "claude-sonnet-4-20250514",
                "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
            },
            "openai": {
                "provider": "openai",
                "display_name": "OpenAI",
                "api_key_env": "OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-4o",
                "models": ["gpt-4o", "gpt-4o-mini"],
            },
        }
    }
    agents_dir = temp_config_dir / "agents"
    agents_dir.mkdir(exist_ok=True)
    path = agents_dir / "registry.yaml"
    path.write_text(yaml.dump(content))
    return temp_config_dir


@pytest.fixture
def valid_templates_yaml(temp_config_dir):
    content = {
        "templates": [
            {
                "id": "code_review",
                "name": "代码审查",
                "match_keywords": ["代码", "审查", "review"],
                "steps": [
                    {"order": 1, "agent_role": "architect", "action": "分析代码结构"},
                    {"order": 2, "agent_role": "reviewer", "action": "审查代码风格"},
                    {"order": 3, "agent_role": "programmer", "action": "提出修改建议"},
                ],
            },
            {
                "id": "write_code",
                "name": "协作编码",
                "match_keywords": ["写", "实现", "开发"],
                "steps": [
                    {"order": 1, "agent_role": "architect", "action": "设计方案"},
                    {"order": 2, "agent_role": "programmer", "action": "编写代码"},
                ],
            },
            {
                "id": "analyze",
                "name": "分析讨论",
                "match_keywords": ["分析", "解释"],
                "steps": [
                    {"order": 1, "agent_role": "architect", "action": "高层分析"},
                    {"order": 2, "agent_role": "reviewer", "action": "补充细节"},
                ],
            },
            {
                "id": "general",
                "name": "通用问答",
                "match_keywords": [],
                "steps": [{"order": 1, "agent_role": "auto", "action": "自动决策"}],
            },
        ]
    }
    tmpl_dir = temp_config_dir / "strategy_templates"
    tmpl_dir.mkdir(exist_ok=True)
    path = tmpl_dir / "templates.yaml"
    path.write_text(yaml.dump(content))
    return temp_config_dir


@pytest.fixture
def valid_presets_yaml(temp_config_dir):
    content = {
        "presets": {
            "whitelist": {
                "description": "仅声明的操作可用",
                "default_operations": {
                    "chat": "allowed",
                    "analyze": "allowed",
                    "search": "allowed",
                    "execute_code": "require_approval",
                    "http_request": "require_approval",
                    "file_read": "allowed",
                    "file_write": "require_approval",
                    "file_delete": "denied",
                },
            },
            "approval_first": {
                "description": "所有操作需先确认",
                "default_operations": {
                    "chat": "require_approval",
                    "analyze": "require_approval",
                    "search": "require_approval",
                    "execute_code": "require_approval",
                    "http_request": "require_approval",
                    "file_read": "require_approval",
                    "file_write": "require_approval",
                    "file_delete": "require_approval",
                },
            },
            "open": {
                "description": "全部开放",
                "default_operations": {
                    "chat": "allowed",
                    "analyze": "allowed",
                    "search": "allowed",
                    "execute_code": "allowed",
                    "http_request": "allowed",
                    "file_read": "allowed",
                    "file_write": "allowed",
                    "file_delete": "denied",
                },
            },
        },
        "approval_timeout_seconds": 300,
    }
    perm_dir = temp_config_dir / "permissions"
    perm_dir.mkdir(exist_ok=True)
    path = perm_dir / "presets.yaml"
    path.write_text(yaml.dump(content))
    return temp_config_dir


@pytest.fixture
def valid_tools_yaml(temp_config_dir):
    content = {
        "tools": {
            "read_file": {
                "name": "读取文件",
                "description": "读取指定路径的文件内容",
                "operation_type": "file_read",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径", "required": True}
                ],
                "handler": "filesystem.read",
            },
            "write_file": {
                "name": "写入文件",
                "description": "将内容写入指定路径的文件",
                "operation_type": "file_write",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径", "required": True},
                    {
                        "name": "content",
                        "type": "string",
                        "description": "要写入的内容",
                        "required": True,
                    },
                ],
                "handler": "filesystem.write",
            },
            "execute_python": {
                "name": "执行 Python 代码",
                "description": "在沙箱环境中执行 Python 代码",
                "operation_type": "execute_code",
                "parameters": [
                    {
                        "name": "code",
                        "type": "string",
                        "description": "Python 代码",
                        "required": True,
                    }
                ],
                "handler": "sandbox.python",
            },
            "execute_shell": {
                "name": "执行 Shell 命令",
                "description": "在沙箱中执行 Shell 命令",
                "operation_type": "execute_code",
                "parameters": [
                    {
                        "name": "command",
                        "type": "string",
                        "description": "Shell 命令",
                        "required": True,
                    }
                ],
                "handler": "sandbox.shell",
            },
            "http_get": {
                "name": "HTTP GET 请求",
                "description": "发起 HTTP GET 请求",
                "operation_type": "http_request",
                "parameters": [
                    {"name": "url", "type": "string", "description": "请求 URL", "required": True}
                ],
                "handler": "network.http_get",
            },
            "http_post": {
                "name": "HTTP POST 请求",
                "description": "发起 HTTP POST 请求",
                "operation_type": "http_request",
                "parameters": [
                    {"name": "url", "type": "string", "description": "请求 URL", "required": True},
                    {"name": "body", "type": "object", "description": "请求体", "required": False},
                ],
                "handler": "network.http_post",
            },
            "web_search": {
                "name": "网络搜索",
                "description": "通过搜索引擎检索信息",
                "operation_type": "search",
                "parameters": [
                    {
                        "name": "query",
                        "type": "string",
                        "description": "搜索关键词",
                        "required": True,
                    }
                ],
                "handler": "search.web",
            },
        }
    }
    tools_dir = temp_config_dir / "tools"
    tools_dir.mkdir(exist_ok=True)
    path = tools_dir / "registry.yaml"
    path.write_text(yaml.dump(content))
    return temp_config_dir
