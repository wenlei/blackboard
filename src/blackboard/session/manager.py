import asyncio
import json
import logging
import os
from pathlib import Path

from blackboard.agents.registry import AgentRegistry
from blackboard.config.loader import ConfigLoader
from blackboard.config.models import PermissionMode
from blackboard.guard.guard import SessionGuard
from blackboard.host.host import Host
from blackboard.host.strategy import StrategyGenerator
from blackboard.logger.session_logger import SessionLogger
from blackboard.mq.redis_streams import MQLayer

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, mq: MQLayer, config_loader: ConfigLoader, agent_registry: AgentRegistry, data_dir: str = "/data/sessions", credential_mgr=None):
        self.mq = mq
        self.config_loader = config_loader
        self.agent_registry = agent_registry
        self.credential_mgr = credential_mgr
        self.data_dir = Path(data_dir)
        self._sessions: dict[str, dict] = {}

    def _get_api_key(self, agent_name: str, provider: str | None = None) -> str | None:
        """Look up API key strictly by agent instance name (ADR-013).

        No provider-level fallback — each instance owns its own credential independently.

        Returns None if no credential manager is configured (test / dev mode).
        Raises MissingApiKeyError if a credential manager is present but no key is found.
        """
        from blackboard.config.models import MissingApiKeyError
        if not self.credential_mgr:
            return None
        key = self.credential_mgr.get_api_key(agent_name)
        if key:
            return key
        raise MissingApiKeyError(
            f"Agent '{agent_name}' (provider: {provider}) has no API key configured. "
            "Add it in Config → Model Settings → Set Key."
        )

    def _get_base_url(self, agent_name: str, default_base_url: str) -> str:
        """Look up base URL override strictly by agent instance name (ADR-013)."""
        if self.credential_mgr:
            override = self.credential_mgr.get_base_url_override(agent_name)
            if override:
                return override
        return default_base_url

    def _get_model(self, agent_name: str, requested: str | None, default_model: str) -> str:
        """Resolve model strictly by agent instance name (ADR-013)."""
        if requested:
            return requested
        if self.credential_mgr:
            saved = self.credential_mgr.get_default_model(agent_name)
            if saved:
                return saved
        return default_model

    async def create(
        self,
        session_id: str,
        agents: list[dict],
        permissions: dict | None = None,
        session_name: str = "",
    ) -> dict:
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        from datetime import datetime, timezone

        presets = self.config_loader.load_permission_presets()
        perm_config = permissions or {}
        mode = PermissionMode(perm_config.get("mode", "whitelist"))
        fallback_preset = presets.presets.get("whitelist")
        if fallback_preset:
            ops = perm_config.get("operations") or fallback_preset.default_operations.model_dump()
        else:
            ops = perm_config.get("operations") or {}

        session_dir = self.data_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        agent_configs = []
        agent_roles: dict[str, str] = {}
        agent_registry_yaml = self.config_loader.load_agent_registry()
        for ag in agents:
            agent_name = ag["name"]
            # registry_key: which registry entry to use for credential/config lookup.
            # Defaults to agent_name for backward-compat (API callers that omit it).
            registry_key = ag.get("registry_key") or agent_name
            role = ag.get("role", agent_name)
            provider = ag["provider"]
            model = ag.get("model")

            # Credentials and config are keyed by registry_key (ADR-013).
            provider_cfg = agent_registry_yaml.agents.get(registry_key)
            base_url = None
            resolved_model = model
            if provider_cfg:
                api_key = self._get_api_key(registry_key, provider)
                base_url = self._get_base_url(registry_key, provider_cfg.base_url or "")
                resolved_model = self._get_model(registry_key, model, provider_cfg.default_model)
            else:
                # Registry key not found — attempt direct lookup (legacy / custom agents)
                api_key = self._get_api_key(registry_key, provider)
                base_url = self._get_base_url(registry_key, "")
                resolved_model = self._get_model(registry_key, model, "")

            # Soul resolution (3-tier), keyed by session-level agent_name (ADR-016/017):
            # 1. Caller-supplied system_prompt → write to session soul.md
            # 2. Existing session soul.md (restored session or previous write)
            # 3. Default template from registry entry: default_template → config/agent_templates/{template}.md
            soul_path = session_dir / "agents" / agent_name / "soul.md"
            system_prompt = ag.get("system_prompt") or None
            if system_prompt:
                soul_path.parent.mkdir(parents=True, exist_ok=True)
                soul_path.write_text(system_prompt, encoding="utf-8")
            elif soul_path.exists():
                system_prompt = soul_path.read_text(encoding="utf-8")
            else:
                template_name = (provider_cfg.default_template if provider_cfg else "")
                if template_name:
                    tmpl_path = self.config_loader.config_dir / "agent_templates" / f"{template_name}.md"
                    if tmpl_path.exists():
                        system_prompt = tmpl_path.read_text(encoding="utf-8")
            self.agent_registry.create(agent_name, provider, resolved_model, api_key=api_key, base_url=base_url, system_prompt=system_prompt)
            agent_roles[role] = agent_name
            agent_configs.append({
                "name": agent_name,
                "registry_key": registry_key,
                "provider": provider,
                "role": role,
                "model": resolved_model,
            })

        await self.mq.init_session_streams(session_id)

        # First agent in list becomes the default 主持人
        default_agent = agent_configs[0]["name"] if agent_configs else None

        guard = SessionGuard(mode=mode, operations=ops)
        templates = self.config_loader.load_strategy_templates()
        strategy_gen = StrategyGenerator(templates)
        session_logger = SessionLogger(session_id, str(self.data_dir))
        host = Host(session_id, self.mq, guard, self.agent_registry, strategy_gen, str(self.data_dir), default_agent=default_agent, session_logger=session_logger)

        config_data = {"session_id": session_id, "session_name": session_name, "agents": agent_configs, "permissions": {"mode": mode.value, "operations": ops}}
        try:
            (session_dir / "config.json").write_text(json.dumps(config_data, ensure_ascii=False, indent=2))
        except OSError as e:
            await self.mq.destroy_session_streams(session_id)
            raise RuntimeError(f"Failed to write session config for {session_id}: {e}") from e

        self._sessions[session_id] = {
            "host": host,
            "guard": guard,
            "agent_roles": agent_roles,
            "agent_configs": agent_configs,
            "name": session_name or session_id,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "default_agent": default_agent,
            "permissions_snapshot": {"mode": mode.value, "operations": ops},
        }

        def _on_host_done(task: asyncio.Task):
            if task.cancelled():
                logger.info("Host task for session %s was cancelled", session_id)
            elif task.exception():
                logger.exception("Host task for session %s crashed", session_id, exc_info=task.exception())

        host_task = asyncio.create_task(host.run(agent_roles))
        host_task.add_done_callback(_on_host_done)
        logger.info("Session %s created with %d agents", session_id, len(agent_configs))
        return config_data

    async def restore_sessions(self) -> int:
        """Scan data_dir for saved config.json files and restore each session.

        Called once during application startup so sessions survive container restarts.
        Returns the number of sessions successfully restored.
        """
        restored = 0
        if not self.data_dir.exists():
            return 0

        for config_path in sorted(self.data_dir.glob("*/config.json")):
            try:
                raw = config_path.read_text(encoding="utf-8")
                cfg = json.loads(raw)
            except Exception as e:
                logger.warning("Skipping malformed session config %s: %s", config_path, e)
                continue

            session_id = cfg.get("session_id")
            if not session_id:
                continue
            if session_id in self._sessions:
                continue  # already active (shouldn't happen on cold start)

            agents = cfg.get("agents", [])
            permissions = cfg.get("permissions")
            session_name = cfg.get("session_name", session_id)

            try:
                # Discard stale pending inbox messages before starting the new host,
                # so messages from the previous process aren't re-dispatched.
                await self.mq.ack_all_pending(session_id, "inbox", "inbox")
                await self.create(session_id, agents, permissions, session_name)
                restored += 1
                logger.info("Restored session %s (%d agents)", session_id, len(agents))
            except Exception as e:
                logger.warning("Failed to restore session %s: %s", session_id, e)

        if restored:
            logger.info("Session restore complete: %d session(s) reactivated", restored)
        return restored

    async def pause(self, session_id: str):
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id]["status"] = "paused"
        host = self._sessions[session_id].get("host")
        if host:
            host.pause()
        logger.info("Session %s paused", session_id)

    async def resume(self, session_id: str):
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id]["status"] = "active"
        host = self._sessions[session_id].get("host")
        if host:
            host.resume()
        logger.info("Session %s resumed", session_id)

    async def close(self, session_id: str):
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        host = self._sessions[session_id].get("host")
        if host:
            host.stop()
        self._sessions[session_id]["status"] = "closed"
        await self.mq.destroy_session_streams(session_id)
        del self._sessions[session_id]
        logger.info("Session %s closed", session_id)

    def _save_config(self, session_id: str) -> None:
        """Persist the current in-memory session config back to config.json on disk."""
        ses = self._sessions.get(session_id)
        if not ses:
            return
        session_dir = self.data_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "session_id": session_id,
            "session_name": ses.get("name", session_id),
            "agents": ses.get("agent_configs", []),
            "permissions": ses.get("permissions_snapshot", {}),
        }
        try:
            (session_dir / "config.json").write_text(json.dumps(config_data, ensure_ascii=False, indent=2))
        except OSError as e:
            logger.warning("Failed to persist config for session %s: %s", session_id, e)

    async def add_agent(self, session_id: str, agent_name: str, provider: str, role: str, model: str | None = None, system_prompt: str | None = None, registry_key: str | None = None):
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")

        # registry_key: which registry entry to use for credential/config lookup.
        # Defaults to agent_name for backward-compat.
        rkey = registry_key or agent_name

        agent_registry_yaml = self.config_loader.load_agent_registry()
        provider_cfg = agent_registry_yaml.agents.get(rkey)
        base_url = None
        resolved_model = model
        if provider_cfg:
            api_key = self._get_api_key(rkey, provider)
            base_url = self._get_base_url(rkey, provider_cfg.base_url or "")
            resolved_model = self._get_model(rkey, model, provider_cfg.default_model)
        else:
            api_key = self._get_api_key(rkey, provider)
            base_url = self._get_base_url(rkey, "")
            resolved_model = self._get_model(rkey, model, "")

        # Soul resolution (3-tier), keyed by session-level agent_name (ADR-016/017):
        # 1. Caller-supplied system_prompt → write to session soul.md
        # 2. Existing session soul.md
        # 3. Default template from registry entry
        soul_path = self.data_dir / session_id / "agents" / agent_name / "soul.md"
        if system_prompt:
            soul_path.parent.mkdir(parents=True, exist_ok=True)
            soul_path.write_text(system_prompt, encoding="utf-8")
        elif soul_path.exists():
            system_prompt = soul_path.read_text(encoding="utf-8")
        else:
            template_name = (provider_cfg.default_template if provider_cfg else "")
            if template_name:
                tmpl_path = self.config_loader.config_dir / "agent_templates" / f"{template_name}.md"
                if tmpl_path.exists():
                    system_prompt = tmpl_path.read_text(encoding="utf-8")
        self.agent_registry.create(agent_name, provider, resolved_model, api_key=api_key, base_url=base_url, system_prompt=system_prompt)
        self._sessions[session_id]["agent_roles"][role] = agent_name
        self._sessions[session_id]["agent_configs"].append(
            {"name": agent_name, "registry_key": rkey, "provider": provider, "role": role, "model": resolved_model}
        )
        # If no default agent yet, this first addition becomes the 主持人
        if not self._sessions[session_id].get("default_agent"):
            self._sessions[session_id]["default_agent"] = agent_name
            host = self._sessions[session_id].get("host")
            if host:
                host.default_agent = agent_name
        logger.info("Agent %s (registry: %s, role: %s) added to session %s", agent_name, rkey, role, session_id)

    async def remove_agent(self, session_id: str, agent_name: str):
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self.agent_registry.remove(agent_name)
        ses = self._sessions[session_id]
        roles = ses["agent_roles"]
        for role, name in list(roles.items()):
            if name == agent_name:
                del roles[role]
        ses["agent_configs"] = [a for a in ses.get("agent_configs", []) if a["name"] != agent_name]
        logger.info("Agent %s removed from session %s", agent_name, session_id)
