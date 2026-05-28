import asyncio
import json
import logging
import os
import pathlib
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from blackboard.config.credentials import ModelInfo, mask_key
from blackboard.config.loader import AgentEntry, FallbackModelConfig, StrategyStep, StrategyTemplate, SystemConfig
from blackboard.config.models import AgentRegistryError, ApiType, MissingApiKeyError, ModelType

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    session_id: str
    session_name: str = ""
    agents: list[dict]
    permissions: dict | None = None


class MessageRequest(BaseModel):
    content: str


class AddAgentRequest(BaseModel):
    name: str
    provider: str
    role: str
    model: str | None = None
    system_prompt: str | None = None
    registry_key: str | None = None  # registry entry for credential/config lookup; defaults to name


class ArchiveRequest(BaseModel):
    remote_type: str = "local_nas"
    remote_path: str = "/mnt/nas/blackboard/"


class ConfigAgentRequest(BaseModel):
    name: str
    provider: str
    display_name: str
    api_key_env: str = ""
    base_url: str = ""
    models: list = []


class ConfigAgentUpdateRequest(BaseModel):
    provider: str | None = None
    display_name: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    models: list | None = None


class ConfigTemplateRequest(BaseModel):
    id: str | None = None   # auto-generated from name if omitted
    name: str
    match_keywords: list[str] = []
    steps: list[dict]


class ConfigTemplateUpdateRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    match_keywords: list[str] | None = None
    steps: list[dict] | None = None


class SetStrategyRequest(BaseModel):
    template_id: str | None = None
    role_mappings: dict[str, str] = {}  # {role: agent_name}
    psc: str | None = None  # raw PSC override


class SessionTemplateRequest(BaseModel):
    name: str
    steps: list[dict]   # [{"agent_role": str, "action": str}]
    match_keywords: list[str] = []


class SetKeyRequest(BaseModel):
    api_key: str
    base_url_override: str = ""


class SetDefaultModelRequest(BaseModel):
    model_id: str


class TestConnectionRequest(BaseModel):
    api_key: str | None = None
    base_url: str
    model: str | None = None
    api_type: str = "openai_compatible"


class SettingsPatchRequest(BaseModel):
    config_agent: str | None = None


def get_session_mgr(request: Request):
    return request.app.state.session_mgr


def get_credential_mgr(request: Request):
    mgr = request.app.state.credential_mgr
    if mgr is None:
        raise HTTPException(status_code=503, detail="Credential manager not available. Set FERNET_KEY in .env")
    return mgr


def get_config_loader(request: Request):
    return request.app.state.config_loader


def get_logger(request: Request, session_id: str):
    from blackboard.logger.session_logger import SessionLogger
    data_dir = request.app.state.data_dir
    return SessionLogger(session_id, data_dir)


# ── Per-session custom template helpers ──────────────────────────────────────

def _custom_templates_path(data_dir: str, session_id: str) -> pathlib.Path:
    return pathlib.Path(data_dir) / session_id / "custom_templates.json"


def _load_custom_templates(data_dir: str, session_id: str) -> list[dict]:
    path = _custom_templates_path(data_dir, session_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_custom_templates(data_dir: str, session_id: str, templates: list[dict]):
    path = _custom_templates_path(data_dir, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Session endpoints ---

@router.post("/sessions")
async def create_session(req: CreateSessionRequest, request: Request):
    mgr = get_session_mgr(request)
    try:
        config = await mgr.create(req.session_id, req.agents, req.permissions, req.session_name)
        sl = get_logger(request, req.session_id)
        sl.ensure_dir()
        sl.log_event("session_created", {"session_id": req.session_id, "agent_count": len(req.agents)})
        return config
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except MissingApiKeyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AgentRegistryError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    # Enrich agent_configs with live model info and soul content
    agent_configs = []
    for ac in ses.get("agent_configs", []):
        entry = dict(ac)
        try:
            live = mgr.agent_registry.get(ac["name"])
            entry["model"] = live.model  # always reflect resolved/hot-patched model
            # Read soul from file; fall back to live adapter's system_prompt
            soul_path = pathlib.Path(mgr.data_dir) / session_id / "agents" / ac["name"] / "soul.md"
            if soul_path.exists():
                entry["system_prompt"] = soul_path.read_text(encoding="utf-8")
            elif hasattr(live, "system_prompt") and live.system_prompt:
                entry["system_prompt"] = live.system_prompt
        except Exception:
            pass
        agent_configs.append(entry)
    return {
        "session_id": session_id,
        "name": ses.get("name", session_id),
        "status": ses["status"],
        "agent_roles": ses.get("agent_roles", {}),
        "agent_configs": agent_configs,
        "created_at": ses.get("created_at", ""),
        "default_agent": ses.get("default_agent"),
    }


@router.patch("/sessions/{session_id}/default-agent")
async def set_default_agent(session_id: str, body: dict, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    agent_name = body.get("agent_name", "").strip().lower()
    if not agent_name:
        raise HTTPException(status_code=400, detail="agent_name is required")
    ses = mgr._sessions[session_id]
    # Verify agent exists in this session
    if agent_name not in {n.lower() for n in ses.get("agent_roles", {}).values()}:
        raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' is not part of this session")
    ses["default_agent"] = agent_name
    host = ses.get("host")
    if host:
        host.default_agent = agent_name
    return {"default_agent": agent_name}


@router.post("/sessions/{session_id}/pause")
async def pause_session(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    try:
        await mgr.pause(session_id)
        sl = get_logger(request, session_id)
        sl.log_event("session_paused", {})
        return {"status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    try:
        await mgr.resume(session_id)
        return {"status": "active"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    try:
        await mgr.close(session_id)
        sl = get_logger(request, session_id)
        sl.log_event("session_closed", {})
        return {"status": "closed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, req: MessageRequest, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    if ses.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Session is closed")
    mq = request.app.state.mq
    await mq.publish(session_id, "inbox", {"type": "chat", "content": req.content}, target_channel="web_ui")
    sl = get_logger(request, session_id)
    sl.log_conversation("user", req.content)
    return {"status": "sent"}


@router.post("/sessions/{session_id}/cancel")
async def cancel_session_agents(session_id: str, request: Request):
    """Cancel the currently running agent call(s) without closing the session."""
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    host = ses.get("host")
    if host:
        host.cancel_tasks()
    return {"status": "cancelled"}


@router.post("/sessions/{session_id}/execute")
async def execute_session(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    if ses.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Session is closed")
    mq = request.app.state.mq
    await mq.publish(session_id, "inbox", {"type": "command", "content": "execute"}, target_channel="web_ui")
    return {"status": "executing"}


@router.get("/sessions/{session_id}/history")
async def session_history(session_id: str, request: Request):
    sl = get_logger(request, session_id)
    return {
        "conversation": sl.read_conversation(),
        "messages": sl.read_messages(),
        "events": sl.read_events(),
    }


@router.get("/sessions/{session_id}/logs")
async def session_logs_summary(session_id: str, request: Request):
    sl = get_logger(request, session_id)
    return sl.log_summary()


@router.get("/sessions/{session_id}/logs/agent_calls")
async def session_logs_agent_calls(session_id: str, request: Request, limit: int = 50, offset: int = 0):
    sl = get_logger(request, session_id)
    return {"entries": sl.read_agent_calls(limit, offset)}


@router.get("/sessions/{session_id}/logs/tool_calls")
async def session_logs_tool_calls(session_id: str, request: Request, limit: int = 50, offset: int = 0):
    sl = get_logger(request, session_id)
    return {"entries": sl.read_tool_calls(limit, offset)}


@router.get("/sessions/{session_id}/logs/warnings")
async def session_logs_warnings(session_id: str, request: Request):
    sl = get_logger(request, session_id)
    return {"entries": sl.read_warnings()}


@router.get("/sessions/{session_id}/logs/errors")
async def session_logs_errors(session_id: str, request: Request):
    sl = get_logger(request, session_id)
    return {"entries": sl.read_errors()}


@router.get("/logs")
async def system_logs_summary(request: Request):
    """Cross-session summary: total WARNING and ERROR counts across all sessions."""
    from blackboard.logger.session_logger import SystemLogger
    data_dir = request.app.state.data_dir
    return SystemLogger(data_dir).summary()


@router.get("/logs/warnings")
async def system_logs_warnings(request: Request, limit: int = 100, offset: int = 0):
    """All WARNING entries from every session, ordered by insertion time."""
    from blackboard.logger.session_logger import SystemLogger
    data_dir = request.app.state.data_dir
    return {"entries": SystemLogger(data_dir).read_warnings(limit, offset)}


@router.get("/logs/errors")
async def system_logs_errors(request: Request, limit: int = 100, offset: int = 0):
    """All ERROR entries from every session, ordered by insertion time."""
    from blackboard.logger.session_logger import SystemLogger
    data_dir = request.app.state.data_dir
    return {"entries": SystemLogger(data_dir).read_errors(limit, offset)}


@router.get("/sessions/{session_id}/strategy")
async def session_strategy(session_id: str, request: Request):
    sl = get_logger(request, session_id)
    psc = sl.read_strategy()
    if not psc:
        raise HTTPException(status_code=404, detail="No strategy found")
    return {"psc": psc}


@router.put("/sessions/{session_id}/strategy")
async def set_session_strategy(session_id: str, req: SetStrategyRequest, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    agent_roles: dict[str, str] = ses.get("agent_roles", {})

    if req.psc:
        psc = req.psc
    elif req.template_id:
        loader = get_config_loader(request)
        tmpls = loader.load_strategy_templates()
        tmpl = next((t for t in tmpls.templates if t.id == req.template_id), None)
        if not tmpl:
            # Fall back to session-scoped custom templates
            data_dir = request.app.state.data_dir
            raw = next((t for t in _load_custom_templates(data_dir, session_id) if t["id"] == req.template_id), None)
            if raw:
                tmpl = StrategyTemplate(
                    id=raw["id"], name=raw["name"],
                    match_keywords=raw.get("match_keywords", []),
                    steps=[StrategyStep(**s) for s in raw["steps"]],
                )
        if not tmpl:
            raise HTTPException(status_code=404, detail=f"Template '{req.template_id}' not found")
        from blackboard.host.strategy import StrategyGenerator
        gen = StrategyGenerator(tmpls)
        # Build effective agent_roles: merge session roles with caller-provided mappings
        effective_roles = dict(agent_roles)
        effective_roles.update(req.role_mappings)
        psc = gen._build_psc_from_template(tmpl, effective_roles)
    else:
        raise HTTPException(status_code=400, detail="Either template_id or psc is required")

    sl = get_logger(request, session_id)
    sl.write_strategy(psc)
    mq = request.app.state.mq
    await mq.publish(session_id, "outbox",
        {"type": "strategy_ready", "psc": psc, "message": "策略已更新"},
        target_channel="web_ui")
    return {"psc": psc}


# --- Session-scoped custom template endpoints ---

@router.get("/sessions/{session_id}/templates")
async def get_session_templates(session_id: str, request: Request):
    """Return system templates + session-scoped custom templates, each tagged with source."""
    loader = get_config_loader(request)
    data_dir = request.app.state.data_dir
    system = loader.load_strategy_templates()
    custom = _load_custom_templates(data_dir, session_id)
    result = [
        {**t.model_dump(), "source": "system"}
        for t in system.templates
    ] + [
        {**t, "source": "custom"}
        for t in custom
    ]
    return {"templates": result}


@router.post("/sessions/{session_id}/templates")
async def create_session_template(session_id: str, req: SessionTemplateRequest, request: Request):
    """Create a new session-scoped custom template."""
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    import uuid as _uuid
    data_dir = request.app.state.data_dir
    custom = _load_custom_templates(data_dir, session_id)
    steps = [
        {"order": i + 1, "agent_role": s.get("agent_role", "").strip(), "action": s.get("action", "").strip()}
        for i, s in enumerate(req.steps)
        if s.get("agent_role", "").strip() and s.get("action", "").strip()
    ]
    if not steps:
        raise HTTPException(status_code=400, detail="At least one valid step (agent_role + action) is required")
    tmpl: dict = {
        "id": f"custom_{_uuid.uuid4().hex[:8]}",
        "name": req.name.strip() or "Custom Template",
        "match_keywords": req.match_keywords,
        "steps": steps,
    }
    custom.append(tmpl)
    _save_custom_templates(data_dir, session_id, custom)
    return {**tmpl, "source": "custom"}


@router.delete("/sessions/{session_id}/templates/{template_id}")
async def delete_session_template(session_id: str, template_id: str, request: Request):
    """Delete a session-scoped custom template (system templates cannot be deleted here)."""
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    data_dir = request.app.state.data_dir
    custom = _load_custom_templates(data_dir, session_id)
    filtered = [t for t in custom if t["id"] != template_id]
    if len(filtered) == len(custom):
        raise HTTPException(status_code=404, detail=f"Custom template '{template_id}' not found (system templates cannot be deleted here)")
    _save_custom_templates(data_dir, session_id, filtered)
    return {"status": "removed", "id": template_id}


# --- Agent endpoints (within session) ---

@router.post("/sessions/{session_id}/agents")
async def add_session_agent(session_id: str, req: AddAgentRequest, request: Request):
    mgr = get_session_mgr(request)
    try:
        await mgr.add_agent(session_id, req.name, req.provider, req.role, req.model, req.system_prompt, req.registry_key)
        mgr._save_config(session_id)
        sl = get_logger(request, session_id)
        sl.log_event("agent_added", {"name": req.name, "role": req.role})
        return {"status": "added"}
    except MissingApiKeyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/sessions/{session_id}/agents/{agent_name}")
async def remove_session_agent(session_id: str, agent_name: str, request: Request):
    mgr = get_session_mgr(request)
    try:
        await mgr.remove_agent(session_id, agent_name)
        sl = get_logger(request, session_id)
        sl.log_event("agent_removed", {"name": agent_name})
        return {"status": "removed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/sessions/{session_id}/agents/{agent_name}")
async def update_session_agent(session_id: str, agent_name: str, update: dict, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ses = mgr._sessions[session_id]
    for ag in ses.get("agent_configs", []):
        if ag["name"] == agent_name:
            if "role" in update:
                old_role = ag.get("role", "")
                if old_role in ses.get("agent_roles", {}):
                    del ses["agent_roles"][old_role]
                ag["role"] = update["role"]
                ses["agent_roles"][update["role"]] = agent_name
            if "model" in update:
                ag["model"] = update["model"]
            if "provider" in update:
                ag["provider"] = update["provider"]
            break
    # Hot-patch the live agent instance so the change takes effect immediately
    try:
        live_agent = mgr.agent_registry.get(agent_name)
        if "model" in update and update["model"]:
            live_agent.model = update["model"]
        if "system_prompt" in update and hasattr(live_agent, "system_prompt"):
            new_soul = update["system_prompt"] or None
            live_agent.system_prompt = new_soul
            # Persist soul to agents/{name}/soul.md
            soul_path = pathlib.Path(mgr.data_dir) / session_id / "agents" / agent_name / "soul.md"
            if new_soul:
                soul_path.parent.mkdir(parents=True, exist_ok=True)
                soul_path.write_text(new_soul, encoding="utf-8")
            elif soul_path.exists():
                soul_path.unlink()
    except Exception:
        pass
    # Persist to disk
    mgr._save_config(session_id)
    sl = get_logger(request, session_id)
    sl.log_event("agent_updated", {"name": agent_name, "update": update})
    return {"status": "updated", "changes": update}


# --- Permission endpoints ---

@router.patch("/sessions/{session_id}/permissions")
async def update_permissions(session_id: str, update: dict, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    guard = mgr._sessions[session_id].get("guard")
    if guard:
        if "mode" in update:
            from blackboard.config.models import PermissionMode
            guard.update_mode(PermissionMode(update["mode"]))
        if "operations" in update:
            guard.update_operations(update["operations"])
    return {"status": "updated"}


# --- Archive endpoints ---

@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: str, req: ArchiveRequest, request: Request):
    import shutil
    import tempfile
    from pathlib import Path

    data_dir = request.app.state.data_dir
    ses_dir = Path(data_dir) / session_id
    if not ses_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    archive_name = f"{session_id}.tar.gz"
    archive_local = Path(tempfile.gettempdir()) / archive_name
    shutil.make_archive(str(archive_local).replace(".tar.gz", ""), "gztar", str(ses_dir))

    sl = get_logger(request, session_id)
    sl.log_event("archived", {"remote_type": req.remote_type, "remote_path": req.remote_path})

    for f in ses_dir.iterdir():
        if f.name not in ("config.json", "strategy.psc"):
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()

    return {"status": "archived", "archive": str(archive_local)}


@router.get("/sessions/{session_id}/archive")
async def get_archive(session_id: str, request: Request):
    import tempfile
    from pathlib import Path

    archive_path = Path(tempfile.gettempdir()) / f"{session_id}.tar.gz"
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found locally")
    return {"status": "ready", "path": str(archive_path)}


# --- Config endpoints ---

@router.get("/config/agents")
async def config_agents(request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    return reg.model_dump()


@router.post("/config/agents")
async def config_add_agent(req: ConfigAgentRequest, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    existed = req.name in reg.agents
    reg.agents[req.name] = AgentEntry(
        provider=req.provider,
        display_name=req.display_name,
        api_key_env=req.api_key_env,
        base_url=req.base_url,
        default_model=req.models[0] if req.models else "",
        models=req.models,
    )
    loader.save_agent_registry(reg)
    return {"status": "updated" if existed else "added", "name": req.name}


@router.delete("/config/agents/{name}")
async def config_remove_agent(name: str, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    if name not in reg.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    del reg.agents[name]
    loader.save_agent_registry(reg)
    # Each instance owns its credentials independently; always delete by instance name
    cred_deleted = False
    cred_mgr = getattr(request.app.state, "credential_mgr", None)
    if cred_mgr:
        cred_mgr.delete(name)
        cred_deleted = True
    return {"status": "removed", "name": name, "credential_deleted": cred_deleted}


@router.patch("/config/agents/{name}")
async def config_update_agent(name: str, req: ConfigAgentUpdateRequest, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    if name not in reg.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    entry = reg.agents[name]
    if req.provider is not None:
        entry.provider = req.provider
    if req.display_name is not None:
        entry.display_name = req.display_name
    if req.api_key_env is not None:
        entry.api_key_env = req.api_key_env
    if req.base_url is not None:
        entry.base_url = req.base_url
    if req.models is not None:
        entry.models = req.models
        if entry.models:
            entry.default_model = entry.models[0]
    loader.save_agent_registry(reg)
    return {"status": "updated", "name": name, "agent": entry.model_dump()}


@router.get("/config/templates")
async def config_templates(request: Request):
    loader = get_config_loader(request)
    tmpl = loader.load_strategy_templates()
    return tmpl.model_dump()


@router.post("/config/templates")
async def config_add_template(req: ConfigTemplateRequest, request: Request):
    import re as _re, uuid as _uuid
    loader = get_config_loader(request)
    tmpl = loader.load_strategy_templates()
    # Auto-generate id from name if not supplied
    template_id = (req.id or "").strip()
    if not template_id:
        base = _re.sub(r"[^\w]+", "_", req.name.strip().lower()).strip("_") or "tmpl"
        template_id = f"{base}_{_uuid.uuid4().hex[:6]}"
    for t in tmpl.templates:
        if t.id == template_id:
            raise HTTPException(status_code=409, detail=f"Template '{template_id}' already exists")
    steps = [StrategyStep(**s) for s in req.steps]
    tmpl.templates.append(StrategyTemplate(id=template_id, name=req.name, match_keywords=req.match_keywords, steps=steps))
    loader.save_strategy_templates(tmpl)
    return {"status": "added", "id": template_id, "source": "system"}


@router.patch("/config/templates/{template_id}")
async def config_update_template(template_id: str, req: ConfigTemplateUpdateRequest, request: Request):
    loader = get_config_loader(request)
    tmpl = loader.load_strategy_templates()
    for i, t in enumerate(tmpl.templates):
        if t.id == template_id:
            updated = t.model_dump()
            if req.id is not None:
                updated["id"] = req.id
            if req.name is not None:
                updated["name"] = req.name
            if req.match_keywords is not None:
                updated["match_keywords"] = req.match_keywords
            if req.steps is not None:
                updated["steps"] = [StrategyStep(**s) for s in req.steps]
            tmpl.templates[i] = StrategyTemplate(**updated)
            loader.save_strategy_templates(tmpl)
            return {"status": "updated", "id": template_id}
    raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")


@router.delete("/config/templates/{template_id}")
async def config_delete_template(template_id: str, request: Request):
    loader = get_config_loader(request)
    tmpl = loader.load_strategy_templates()
    tmpl.templates = [t for t in tmpl.templates if t.id != template_id]
    loader.save_strategy_templates(tmpl)
    return {"status": "removed", "id": template_id}


@router.get("/config/permissions/presets")
async def config_permissions(request: Request):
    loader = get_config_loader(request)
    presets = loader.load_permission_presets()
    return presets.model_dump()


@router.get("/config/tools")
async def config_tools(request: Request):
    try:
        tool_registry = request.app.state.tool_registry
        if tool_registry:
            return tool_registry.model_dump()
    except AttributeError:
        logger.warning("tool_registry not found in app.state, loading from config")
    loader = get_config_loader(request)
    try:
        reg = loader.load_tool_registry()
        return reg.model_dump()
    except Exception as e:
        logger.error("Failed to load tool registry: %s", e)
        return {"tools": {}}


# --- Providers + Catalog (models.dev as single source of truth) ---

def _build_providers() -> dict:
    dev_data = _load_local_catalog()
    providers: dict[str, dict] = {
        "ollama": {
            "display_name": "Ollama (Local)",
            "base_url": "http://localhost:11434/v1",
            "auth_type": "none",
            "protected": False,
        }
    }
    for slug, entry in dev_data.items():
        providers[slug] = {
            "display_name": entry.get("name", slug),
            "base_url": _dev_base_url(slug, dev_data),
            "auth_type": "none" if slug == "ollama" else "bearer",
            "protected": False,
        }
    logger.info("Providers built: %d total (local catalog)", len(providers))
    return {"providers": providers}


@router.get("/config/providers")
def config_providers(request: Request):
    return _build_providers()


# --- Model Settings endpoints ---

_LOCAL_CATALOG: dict | None = None
_LOCAL_CATALOG_PATH = (
    pathlib.Path(__file__).parents[3] / "config" / "agents" / "models-dev-api-endpoints-full.json"
)


def _load_local_catalog() -> dict:
    """Load and cache the bundled provider catalog from models-dev-api-endpoints-full.json.

    Returns a flat {slug: entry} dict where each entry contains api_endpoint, name, models, etc.
    Falls back to an empty dict if the file is missing.
    """
    global _LOCAL_CATALOG
    if _LOCAL_CATALOG is not None:
        return _LOCAL_CATALOG
    try:
        with open(_LOCAL_CATALOG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        _LOCAL_CATALOG = raw.get("providers", {})
        logger.info("Local provider catalog loaded: %d providers", len(_LOCAL_CATALOG))
    except Exception as e:
        logger.warning("Local provider catalog load failed: %s", e)
        _LOCAL_CATALOG = {}
    return _LOCAL_CATALOG


def _dev_base_url(slug: str, dev_data: dict) -> str:
    """Return the direct API base URL for a provider from the local catalog."""
    return (dev_data.get(slug, {}).get("api_endpoint") or "").rstrip("/")


def _repair_truncated_json(s: str) -> str:
    """Best-effort repair of JSON that was truncated mid-stream by a token limit.

    Handles the three most common truncation patterns:
    - Unterminated string literal  (close with `"`)
    - Trailing comma before EOF    (strip it)
    - Unclosed `{` / `[`          (append `}` / `]`)
    """
    import re as _re
    s = s.rstrip()
    # Walk char-by-char to detect whether we're inside an open string
    in_string = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and in_string:
            i += 2  # skip escaped character
            continue
        if ch == '"':
            in_string = not in_string
        i += 1
    if in_string:
        s += '"'
    # Strip trailing comma that would be left dangling
    s = _re.sub(r",\s*$", "", s.rstrip())
    # Close any unclosed object/array braces
    s += "}" * max(0, s.count("{") - s.count("}"))
    s += "]" * max(0, s.count("[") - s.count("]"))
    return s


async def _execute_probe_url(candidate_url: str) -> dict:
    """HTTP probe used by the config agent tool-calling loop.

    Sends GET {url}/models and returns reachability info.
    HTTP 401/403 counts as reachable — it means the server exists but requires auth.
    """
    import httpx as _httpx
    probe_endpoint = candidate_url.rstrip("/") + "/models"
    try:
        async with _httpx.AsyncClient(timeout=8) as c:
            r = await c.get(probe_endpoint)
        reachable = r.status_code in (200, 401, 403, 404, 405, 422)
        return {
            "url": candidate_url,
            "reachable": reachable,
            "status_code": r.status_code,
            "note": "401/403 = server exists (auth required). 200 = open endpoint.",
        }
    except _httpx.ConnectError:
        return {"url": candidate_url, "reachable": False, "error": "connection refused"}
    except _httpx.TimeoutException:
        return {"url": candidate_url, "reachable": False, "error": "timed out"}
    except Exception as exc:
        return {"url": candidate_url, "reachable": False, "error": str(exc)}


def _models_dev_to_catalog(provider_entry: dict) -> list[dict]:
    """Convert a local catalog provider entry into our catalog format."""
    result = []
    for m in provider_entry.get("models", {}).values():
        mid = m.get("id", "")
        if not mid:
            continue
        inputs = (m.get("modalities") or {}).get("input", [])
        model_type = "vision" if "image" in inputs else "chat"
        caps = m.get("capabilities") or {}
        entry: dict = {
            "model_id": mid,
            "display_name": m.get("name", mid),
            "model_type": model_type,
            "context_window": (m.get("limit") or {}).get("context"),
        }
        if caps.get("tool_call") is not None:
            entry["supports_tools"] = caps["tool_call"]
        if caps.get("reasoning"):
            entry["reasoning"] = True
        result.append(entry)
    return result


@router.get("/config/providers/{slug}/catalog")
def config_provider_catalog(slug: str):
    """Return model catalog for a provider, sourced from local catalog."""
    dev_data = _load_local_catalog()
    entry = dev_data.get(slug)
    if entry and entry.get("models"):
        models = _models_dev_to_catalog(entry)
        logger.info("Catalog: %d models for %s (local catalog)", len(models), slug)
        return {"models": models, "source": "local_catalog"}
    logger.info("Catalog: provider %s not in local catalog", slug)
    return {"models": [], "source": "none"}


def _model_type_from_architecture(arch: dict) -> str:
    modality = arch.get("modality", "")
    if modality == "text+image->text":
        return "vision"
    return "chat"


def _model_type_heuristic(model_id: str) -> ModelType:
    lower = model_id.lower()
    if any(k in lower for k in ("embed", "text-embedding")):
        return ModelType.EMBEDDING
    if any(k in lower for k in ("vision", "image", "vl-")):
        return ModelType.VISION
    if any(k in lower for k in ("reasoner", "r1", "o1", "o3", "o4", "thinking")):
        return ModelType.REASONING
    return ModelType.CHAT


async def _discover_models(
    base_url: str,
    api_key: str | None,
    api_type: ApiType,
    provider_id: str,
) -> list[ModelInfo]:
    import httpx

    if not api_key:
        logger.info("No API key for %s, skipping model discovery", provider_id)
        return []

    endpoint = base_url.rstrip("/") + ("/api/tags" if api_type == ApiType.OLLAMA else "/models")
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if api_type == ApiType.OLLAMA:
                    return [
                        ModelInfo(model_id=m["name"], display_name=m.get("name", m["name"]))
                        for m in data.get("models", [])
                    ]
                raw_models = data.get("data", data if isinstance(data, list) else [])
                return [ModelInfo(model_id=m["id"], display_name=m.get("name", m["id"])) for m in raw_models if "id" in m]

            logger.warning("Provider %s /models returned HTTP %s", provider_id, resp.status_code)
    except httpx.TimeoutException:
        logger.error("Provider %s /models timeout", provider_id)
    except Exception as e:
        logger.error("Provider %s /models error: %s", provider_id, e)

    return []



def _enrich_from_models_dev(models: list[ModelInfo], provider_id: str) -> list[ModelInfo]:
    """Enrich model metadata from the bundled models.dev catalog (no network call required)."""
    catalog = _load_local_catalog()
    provider_models: dict = catalog.get(provider_id, {}).get("models", {})

    for m in models:
        entry = provider_models.get(m.model_id)
        if entry:
            if not m.display_name:
                m.display_name = entry.get("name", m.model_id)
            limit = entry.get("limit") or {}
            if limit.get("context"):
                m.context_window = limit["context"]
            if limit.get("output"):
                m.max_output_tokens = limit["output"]
            caps = entry.get("capabilities") or {}
            if caps.get("tool_call") is not None:
                m.supports_tools = bool(caps["tool_call"])
            modalities = entry.get("modalities") or {}
            inputs = modalities.get("input", [])
            if "image" in inputs:
                m.supports_vision = True
                if m.model_type == ModelType.UNKNOWN:
                    m.model_type = ModelType.VISION
        if m.model_type == ModelType.UNKNOWN:
            m.model_type = _model_type_heuristic(m.model_id)
    return models


@router.get("/config/status")
async def config_status(request: Request):
    mgr = request.app.state.credential_mgr
    if mgr is None:
        return {"status": "not_configured", "ready_providers": []}
    return mgr.get_overall_status()


@router.get("/config/credentials")
async def config_credentials(request: Request):
    mgr = get_credential_mgr(request)
    return {"credentials": mgr.list_credentials()}


@router.delete("/config/credentials/{provider_id}")
async def config_delete_credential(provider_id: str, request: Request):
    mgr = get_credential_mgr(request)
    mgr.delete(provider_id)
    return {"status": "deleted", "provider_id": provider_id}


@router.get("/config/settings")
async def config_settings_get(request: Request):
    loader = get_config_loader(request)
    cfg = loader.load_system()
    return {"config_agent": cfg.config_agent}


@router.patch("/config/settings")
async def config_settings_patch(req: SettingsPatchRequest, request: Request):
    loader = get_config_loader(request)
    cfg = loader.load_system()
    if req.config_agent is not None:
        cfg.config_agent = req.config_agent
    loader.save_system_config(cfg)
    return {"config_agent": cfg.config_agent}


@router.post("/config/providers/{slug}/ask-config")
async def config_ask_config_agent(slug: str, request: Request):
    """Ask the designated Config Agent to suggest base_url and notes for a provider.
    Calls ChatCompletionsAdapter directly — no session required."""
    import httpx

    loader = get_config_loader(request)
    cfg = loader.load_system()
    if not cfg.config_agent:
        raise HTTPException(status_code=404, detail="No config_agent configured. Set one in System Settings.")

    cred_mgr = getattr(request.app.state, "credential_mgr", None)
    if not cred_mgr:
        raise HTTPException(status_code=503, detail="Credential manager not available (FERNET_KEY not set?)")

    api_key = cred_mgr.get_api_key(cfg.config_agent)
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=f"Config agent '{cfg.config_agent}' has no API key saved. "
                   f"Edit the agent in Agent Registry, enter your API key, and click Save."
        )

    base_url_override = cred_mgr.get_base_url_override(cfg.config_agent)

    reg = loader.load_agent_registry()
    agent_entry = reg.agents.get(cfg.config_agent)
    if not agent_entry:
        raise HTTPException(status_code=404, detail=f"Config agent '{cfg.config_agent}' not found in registry.")

    dev_data = _load_local_catalog()
    base_url = (base_url_override or agent_entry.base_url or "").rstrip("/")
    if not base_url:
        base_url = _dev_base_url(agent_entry.provider, dev_data)
    if not base_url:
        raise HTTPException(
            status_code=422,
            detail=f"Config agent '{cfg.config_agent}' has no base URL. "
                   f"Edit the agent and fill in the Base URL field."
        )

    model = cred_mgr.get_default_model(cfg.config_agent) or agent_entry.default_model
    if not model:
        raise HTTPException(
            status_code=422,
            detail=f"Config agent '{cfg.config_agent}' has no default model. "
                   f"Select a model in the Agent Registry and save."
        )

    known_url = _dev_base_url(slug, dev_data)
    catalog_entry = dev_data.get(slug, {})

    # -----------------------------------------------------------------------
    # Tool definition: probe_url
    # The LLM uses this to test candidate base URLs before committing to one.
    # -----------------------------------------------------------------------
    probe_tool = {
        "type": "function",
        "function": {
            "name": "probe_url",
            "description": (
                "Test whether an API base URL is reachable. "
                "Sends a GET request to {url}/models. "
                "HTTP 200/401/403 all mean the server exists — 401 just means auth is required. "
                "A connection error or timeout means the URL is wrong."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The base URL to test, e.g. https://api.deepseek.com/v1",
                    }
                },
                "required": ["url"],
            },
        },
    }

    # Build a structured context block from the local catalog so the LLM has
    # all known facts about the provider before it starts probing.
    ctx_lines = [f"Provider ID : {slug}"]
    if known_url:
        ctx_lines.append(f"Known endpoint (catalog): {known_url}")
    if catalog_entry.get("endpoint_type"):
        ctx_lines.append(f"Endpoint type: {catalog_entry['endpoint_type']}")
    if catalog_entry.get("env"):
        ctx_lines.append(f"API key env var(s): {', '.join(catalog_entry['env'])}")
    if catalog_entry.get("doc"):
        ctx_lines.append(f"Official docs: {catalog_entry['doc']}")
    model_ids = list((catalog_entry.get("models") or {}).keys())
    if model_ids:
        ctx_lines.append(f"Known models ({len(model_ids)}): {', '.join(model_ids[:8])}"
                         + (" …" if len(model_ids) > 8 else ""))

    provider_context = "\n".join(ctx_lines)

    system_prompt = (
        f"You are a developer assistant helping configure API access for an LLM proxy.\n"
        f"Your task: confirm the correct OpenAI-compatible base URL for the provider below "
        f"and return it as JSON.\n\n"
        f"## Known provider information\n{provider_context}\n\n"
        f"Use the probe_url tool to verify the endpoint if you are uncertain. "
        f"HTTP 401/403/200 all confirm the server exists.\n\n"
        f"Reply with ONLY this JSON object (no markdown, no explanation):\n"
        f'{{"base_url": "...", "openai_compatible": true, "auth_header": "Authorization", "notes": "..."}}'
    )

    messages: list[dict] = [{"role": "user", "content": system_prompt}]
    llm_headers: dict[str, str] = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    llm_endpoint = f"{base_url}/chat/completions"
    import re as _re

    def _extract_result(raw: str) -> dict | None:
        """Parse and repair the final JSON from the LLM's text reply."""
        m = _re.search(r'\{.*\}', raw, _re.DOTALL) or _re.search(r'\{.*', raw, _re.DOTALL)
        if not m:
            return None
        c = m.group(0)
        for pat, rep in [(r'\bTrue\b', 'true'), (r'\bFalse\b', 'false'),
                         (r'\bNone\b', 'null'), (r',\s*([}\]])', r'\1')]:
            c = _re.sub(pat, rep, c)
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            c2 = _repair_truncated_json(c)
            c2 = _re.sub(r',\s*([}\]])', r'\1', c2)
            try:
                return json.loads(c2)
            except json.JSONDecodeError:
                return None

    try:
        # Multi-turn loop: LLM may call probe_url one or more times before answering
        _json_only = False  # True on the turn where we ask for JSON-only output
        for turn in range(6):
            if _json_only:
                # JSON-only turn: no tools needed
                payload: dict = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                }
            else:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                    "tools": [probe_tool],
                    "tool_choice": "auto",
                }
            async with httpx.AsyncClient(timeout=30) as llm_client:
                resp = await llm_client.post(llm_endpoint, headers=llm_headers, json=payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=502,
                    detail=f"Config agent returned HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                body = resp.json()
            except Exception:
                raise HTTPException(status_code=502,
                    detail=f"Config agent returned non-JSON body. Raw: {resp.text[:300]!r}")

            choice = (body.get("choices") or [{}])[0]
            finish = choice.get("finish_reason", "")
            msg = choice.get("message", {})
            logger.debug("ask-config turn %d finish=%r", turn, finish)

            # ---- LLM wants to call probe_url ----
            if finish == "tool_calls" or msg.get("tool_calls"):
                messages.append(msg)  # keep assistant message with tool_calls
                tool_calls = msg.get("tool_calls") or []
                for tc in tool_calls:
                    fn_args = tc.get("function", {}).get("arguments", "{}")
                    try:
                        args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        args = {}
                    probe_result = await _execute_probe_url(args.get("url", ""))
                    logger.info("probe_url %s → %s", args.get("url"), probe_result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(probe_result),
                    })
                continue  # send probe results back to LLM

            # ---- LLM gave a text reply ----
            raw = msg.get("content") or ""
            if isinstance(raw, list):
                raw = " ".join(b.get("text", "") for b in raw if b.get("type") == "text")
            if not raw and body.get("content"):
                blocks = body["content"]
                raw = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")

            if not raw:
                raise HTTPException(status_code=502, detail="Config agent returned empty content.")

            result = _extract_result(raw)
            if result is None:
                if _json_only:
                    raise HTTPException(status_code=502,
                        detail=f"Config agent returned no parseable JSON. Response: {raw[:200]}")
                # LLM gave prose but no JSON — push back once to get just the JSON
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        'Output ONLY the JSON object, no explanations:\n'
                        '{"base_url": "...", "openai_compatible": true, '
                        '"auth_header": "Authorization", "notes": "..."}'
                    ),
                })
                _json_only = True
                continue  # next turn will get the JSON-only reply

            return {
                "base_url": result.get("base_url", ""),
                "openai_compatible": result.get("openai_compatible", True),
                "auth_header": result.get("auth_header", "Authorization"),
                "notes": result.get("notes") or "",
                "agent": cfg.config_agent,
            }

        raise HTTPException(status_code=502, detail="Config agent did not return a result after max tool-call rounds.")

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Config agent returned invalid JSON: {e}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Config agent request timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/config/test-connection")
async def config_test_connection_inline(req: TestConnectionRequest):
    """Verify credentials by calling the provider's core endpoint.
    Ollama: GET /api/tags. Others: POST /chat/completions with max_tokens=1."""
    import httpx
    base_url = req.base_url.rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    is_ollama = req.api_type == ApiType.OLLAMA or "11434" in base_url

    if is_ollama:
        endpoint = base_url + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(endpoint)
            if resp.status_code == 200:
                return {"ok": True, "message": "Ollama is running", "endpoint": endpoint}
            return {"ok": False, "message": f"Ollama returned HTTP {resp.status_code}", "endpoint": endpoint}
        except httpx.TimeoutException:
            return {"ok": False, "message": "Connection timed out", "endpoint": endpoint}
        except Exception as e:
            return {"ok": False, "message": str(e), "endpoint": endpoint}

    # OpenAI-compatible: POST /chat/completions with max_tokens=1
    # This is the only endpoint that ALL providers must implement — more reliable than GET /models.
    model = req.model or "gpt-3.5-turbo"
    endpoint = base_url + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "."}],
        "max_tokens": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
        if resp.status_code == 200:
            return {"ok": True, "message": "Connection successful", "endpoint": endpoint}
        if resp.status_code in (401, 403):
            return {"ok": False, "message": f"API key rejected (HTTP {resp.status_code})", "endpoint": endpoint}
        if resp.status_code == 404:
            return {"ok": False, "message": f"Endpoint not found — check base URL (HTTP 404)", "endpoint": endpoint}
        # Some providers return 400 for an unknown model but that still proves auth works
        if resp.status_code == 400:
            try:
                body = resp.json()
                err = (body.get("error") or {}).get("message", "")
                if any(k in err.lower() for k in ("model", "does not exist", "not found", "invalid")):
                    return {"ok": True, "message": f"API key valid (model '{model}' not available on this provider — select from catalog)", "endpoint": endpoint}
            except Exception:
                pass
        return {"ok": False, "message": f"Unexpected response: HTTP {resp.status_code}", "endpoint": endpoint}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Connection timed out", "endpoint": endpoint}
    except Exception as e:
        return {"ok": False, "message": str(e), "endpoint": endpoint}


def _parse_models_response(data: dict, is_ollama: bool) -> list[dict]:
    """Parse a /models or /api/tags response into a unified model list."""
    if is_ollama:
        return [{"model_id": m["name"], "display_name": m.get("name", m["name"]), "model_type": "chat"}
                for m in data.get("models", []) if "name" in m]
    raw = data.get("data", data if isinstance(data, list) else [])
    return [{"model_id": m["id"], "display_name": m.get("name", m["id"]), "model_type": "chat"}
            for m in (raw if isinstance(raw, list) else []) if "id" in m]


@router.post("/config/agents/{name}/set-key")
async def config_set_key(name: str, req: SetKeyRequest, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    logger.info("set-key called for name=%s, registry_keys=%s", name, list(reg.agents.keys()))
    if name not in reg.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found. Available: {list(reg.agents.keys())}")
    cred_mgr = get_credential_mgr(request)
    # Credentials are keyed strictly by instance name (ADR-013).
    # No provider-level alias — each instance owns its own key independently.
    cred_mgr.save_api_key(name, req.api_key, base_url_override=req.base_url_override)
    return {"status": "saved", "name": name}


@router.post("/config/agents/{name}/test")
async def config_test_connection(name: str, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    if name not in reg.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    entry = reg.agents[name]

    cred_mgr = request.app.state.credential_mgr
    api_key = cred_mgr.get_api_key(name) if cred_mgr else None
    base_url = ((cred_mgr.get_base_url_override(name) if cred_mgr else None) or entry.base_url or "").rstrip("/")
    if not base_url:
        dev_data = _load_local_catalog()
        base_url = _dev_base_url(entry.provider, dev_data)
    if not base_url:
        return {"ok": False, "message": "No base URL configured for this agent"}

    # Reuse the same inline test logic
    model = (cred_mgr.get_default_model(name) if cred_mgr else None) or entry.default_model or "gpt-3.5-turbo"
    inline_req = TestConnectionRequest(
        api_key=api_key, base_url=base_url, model=model,
        api_type=entry.api_type.value if hasattr(entry.api_type, "value") else str(entry.api_type),
    )
    return await config_test_connection_inline(inline_req)


@router.post("/config/agents/{name}/sync-models")
async def config_sync_models(name: str, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    if name not in reg.agents:
        # Bare provider slug: Add mode model preview uses GET /config/providers/{slug}/catalog instead
        return []

    cred_mgr = request.app.state.credential_mgr

    entry = reg.agents[name]
    provider_id = entry.provider
    api_key = cred_mgr.get_api_key(name) if cred_mgr else None
    base_url = (cred_mgr.get_base_url_override(name) if cred_mgr else None) or entry.base_url
    if not base_url:
        dev_data = _load_local_catalog()
        base_url = _dev_base_url(provider_id, dev_data) or f"https://api.{provider_id}.com/v1"
    api_type = entry.api_type

    models = await _discover_models(base_url, api_key, api_type, provider_id)
    for m in models:
        m.provider_id = provider_id

    models = _enrich_from_models_dev(models, provider_id)

    if cred_mgr:
        cred_mgr.save_model_list(name, models)

    return [m.model_dump() for m in models]


@router.post("/config/agents/{name}/default-model")
async def config_set_default_model(name: str, req: SetDefaultModelRequest, request: Request):
    loader = get_config_loader(request)
    reg = loader.load_agent_registry()
    if name not in reg.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    entry = reg.agents[name]

    cred_mgr = get_credential_mgr(request)
    existing = cred_mgr.get_model_list(name)
    cred_mgr.save_model_list(name, existing, default_model=req.model_id)
    return {"status": "saved", "name": name, "default_model": req.model_id}


# --- SSE endpoints ---

async def _event_stream(request: Request):
    mq = request.app.state.mq
    last_id = "$"
    while True:
        if await request.is_disconnected():
            break
        try:
            msgs = await mq.read_from("system", "events", last_id, count=10, block_ms=5000)
            for msg in msgs:
                last_id = msg["id"]
                yield f"data: {json.dumps(msg['data'])}\n\n"
        except Exception as e:
            logger.debug("SSE event stream error (continuing): %s", e)
        await asyncio.sleep(0.5)


async def _session_event_stream(session_id: str, request: Request):
    mq = request.app.state.mq
    # Support Last-Event-ID for reconnects; otherwise replay all outbox messages from start
    resume_id = request.headers.get("last-event-id", "0")
    last_id = resume_id
    while True:
        if await request.is_disconnected():
            break
        try:
            msgs = await mq.read_from(session_id, "outbox", last_id, count=20, block_ms=5000)
            for msg in msgs:
                last_id = msg["id"]
                yield f"id: {msg['id']}\ndata: {json.dumps(msg['data'])}\n\n"
        except Exception as e:
            logger.debug("SSE session stream error for %s (continuing): %s", session_id, e)
        await asyncio.sleep(0.3)


@router.get("/events/stream")
async def events_stream(request: Request):
    return StreamingResponse(_event_stream(request), media_type="text/event-stream")


@router.get("/sessions/{session_id}/events/stream")
async def session_events_stream(session_id: str, request: Request):
    mgr = get_session_mgr(request)
    if session_id not in mgr._sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return StreamingResponse(_session_event_stream(session_id, request), media_type="text/event-stream")
