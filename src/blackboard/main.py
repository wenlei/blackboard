import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env if present (development convenience)
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from blackboard.agents.registry import AgentRegistry
from blackboard.api.routes import router as api_router
from blackboard.archive.archiver import Archiver
from blackboard.config.credentials import CredentialManager
from blackboard.config.loader import ConfigLoader
from blackboard.mq.memory import InMemoryMQ
from blackboard.mq.redis_streams import MQLayer
from blackboard.sandbox.sandbox import Sandbox
from blackboard.session.manager import SessionManager
from blackboard.tools.executor import ToolExecutor

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
CONFIG_DIR = PROJECT_ROOT / "config"

logger = logging.getLogger(__name__)

config_loader = ConfigLoader(config_dir=str(CONFIG_DIR))

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.cache_size = 0
templates.env.auto_reload = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    system_cfg = config_loader.load_system()
    redis_url = os.environ.get("REDIS_URL") or system_cfg.redis.url
    _redis_mq = MQLayer(
        redis_url=redis_url,
        max_connections=system_cfg.redis.max_connections,
    )
    try:
        await _redis_mq.connect()
        mq = _redis_mq
    except Exception as e:
        logger.warning("Redis unavailable (%s), using in-memory MQ", e)
        print(f"[WARN] Redis unavailable: {e}. Using in-memory MQ (single-process only).")
        mq = InMemoryMQ()
        await mq.connect()

    data_dir = os.environ.get("DATA_DIR", system_cfg.data.dir)
    if not os.path.exists(data_dir):
        data_dir = os.path.join("/tmp", "blackboard-sessions")
    data_dir_path = Path(data_dir)
    data_dir_path.mkdir(parents=True, exist_ok=True)

    tool_registry = config_loader.load_tool_registry()
    tool_executor = ToolExecutor(tool_registry, "/tmp/blackboard-sandbox")
    agent_registry = AgentRegistry()
    agent_config = config_loader.load_agent_registry()
    credential_mgr = None
    try:
        credential_mgr = CredentialManager(config_dir=str(CONFIG_DIR))
    except RuntimeError as e:
        logger.warning("CredentialManager unavailable (FERNET_KEY not set): %s", e)
        print(f"[WARN] CredentialManager unavailable: {e}. API key storage disabled.")

    session_mgr = SessionManager(
        mq, config_loader, agent_registry, data_dir=str(data_dir_path),
        credential_mgr=credential_mgr
    )
    archiver = Archiver(data_dir=str(data_dir_path))

    app.state.mq = mq
    app.state.config_loader = config_loader
    app.state.agent_config = agent_config
    app.state.tool_registry = tool_registry
    app.state.tool_executor = tool_executor
    app.state.agent_registry = agent_registry
    app.state.session_mgr = session_mgr
    app.state.archiver = archiver
    app.state.credential_mgr = credential_mgr
    app.state.data_dir = str(data_dir_path)

    # Restore sessions saved from previous runs
    restored = await session_mgr.restore_sessions()
    if restored:
        logger.info("Startup: restored %d session(s) from disk", restored)

    yield

    for sid in list(session_mgr._sessions.keys()):
        try:
            await session_mgr.close(sid)
        except Exception:
            logger.exception("Failed to close session %s during shutdown", sid)
    await mq.disconnect()


app = FastAPI(title="Blackboard", version="0.1.0", lifespan=lifespan)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(api_router)


@app.get("/health")
async def health(request: Request):
    redis_ok = await request.app.state.mq.health_check()
    tool_count = len(request.app.state.tool_registry.tools) if request.app.state.tool_registry else 0
    sessions = len(request.app.state.session_mgr._sessions)
    disk_usage_gb, _ = request.app.state.archiver.check_disk_usage()
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "tools_loaded": tool_count,
        "active_sessions": sessions,
        "disk_usage_gb": round(disk_usage_gb / (1024**3), 3),
    }


# Get the shared Jinja2 environment for direct rendering (avoids TemplateResponse cache bug in Python 3.14)
TEMPLATES_ENV = templates.env

# --- UI Pages ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    mgr = request.app.state.session_mgr
    sessions = {}
    for sid, ses in mgr._sessions.items():
        sessions[sid] = {
            "name": ses.get("name", sid),
            "status": ses.get("status", "unknown"),
            "agent_roles": ses.get("agent_roles", {}),
            "created": ses.get("created_at", ""),
        }
    reg = request.app.state.tool_registry
    template_path = TEMPLATE_DIR / "dashboard.html"
    if template_path.exists():
        tmpl = TEMPLATES_ENV.get_template("dashboard.html")
        try:
            agent_reg = request.app.state.config_loader.load_agent_registry()
            agent_count = len(agent_reg.agents)
        except Exception:
            agent_count = 0
        html = tmpl.render(request=request, sessions=sessions,
                           agent_count=agent_count,
                           tool_count=len(reg.tools) if reg else 0)
        return HTMLResponse(html)
    return HTMLResponse("<h1>Blackboard</h1><p>API is running. UI templates not yet installed.</p>")


@app.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    template_path = TEMPLATE_DIR / "session_create.html"
    if template_path.exists():
        tmpl = TEMPLATES_ENV.get_template("session_create.html")
        return HTMLResponse(tmpl.render(request=request))
    return HTMLResponse("<h1>Create Session</h1>")


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_chat(session_id: str, request: Request):
    template_path = TEMPLATE_DIR / "session_chat.html"
    if template_path.exists():
        tmpl = TEMPLATES_ENV.get_template("session_chat.html")
        return HTMLResponse(tmpl.render(request=request, session_id=session_id))
    return HTMLResponse(f"<h1>Session {session_id}</h1>")


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    template_path = TEMPLATE_DIR / "config.html"
    if template_path.exists():
        tmpl = TEMPLATES_ENV.get_template("config.html")
        return HTMLResponse(tmpl.render(request=request))
    return HTMLResponse("<h1>Config</h1><p>Config page not yet installed.</p>")
