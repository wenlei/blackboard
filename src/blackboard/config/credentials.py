import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import BaseModel

from blackboard.config.models import InitStatusEnum, ModelType


class ModelInfo(BaseModel):
    model_id: str
    display_name: str = ""
    provider_id: str = ""
    model_type: ModelType = ModelType.UNKNOWN
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None


def mask_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


class CredentialManager:

    def __init__(self, config_dir: str):
        self._file = Path(config_dir) / "agents" / "credentials.enc"
        self._key = os.getenv("FERNET_KEY", "")
        if not self._key:
            raise RuntimeError(
                "FERNET_KEY not set. Generate one: "
                "python -c \"from cryptography.fernet import Fernet; "
                'print(Fernet.generate_key().decode())"'
            )
        self._fernet = Fernet(self._key.encode())
        self._state: dict = {"credentials": {}, "model_lists": {}}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if self._file.exists():
            encrypted = self._file.read_bytes()
            self._state = json.loads(self._fernet.decrypt(encrypted))
        self._loaded = True

    def _save(self):
        encrypted = self._fernet.encrypt(
            json.dumps(self._state, ensure_ascii=False).encode()
        )
        tmp = self._file.with_suffix(".tmp")
        tmp.write_bytes(encrypted)
        os.replace(tmp, self._file)

    def get_api_key(self, provider_id: str) -> str | None:
        self._ensure_loaded()
        return self._state["credentials"].get(provider_id, {}).get("api_key")

    def get_base_url_override(self, provider_id: str) -> str:
        self._ensure_loaded()
        return self._state["credentials"].get(provider_id, {}).get("base_url_override", "")

    def save_api_key(self, provider_id: str, api_key: str, base_url_override: str = ""):
        self._ensure_loaded()
        self._state["credentials"][provider_id] = {
            "api_key": api_key,
            "base_url_override": base_url_override,
        }
        self._save()

    def delete(self, provider_id: str):
        self._ensure_loaded()
        self._state["credentials"].pop(provider_id, None)
        self._state["model_lists"].pop(provider_id, None)
        self._save()

    def list_credentials(self) -> dict:
        self._ensure_loaded()
        return {
            pid: {
                "provider_id": pid,
                "base_url_override": cred.get("base_url_override", ""),
                "api_key": mask_key(cred.get("api_key", "")),
                "status": self.get_status(pid),
                "default_model": self.get_default_model(pid),
                "models": [m.model_dump() for m in self.get_model_list(pid)],
                "synced_at": self._state["model_lists"].get(pid, {}).get("synced_at", ""),
            }
            for pid, cred in self._state["credentials"].items()
        }

    def get_model_list(self, provider_id: str) -> list[ModelInfo]:
        self._ensure_loaded()
        raw = self._state["model_lists"].get(provider_id, {})
        return [ModelInfo(**m) for m in raw.get("models", [])]

    def get_default_model(self, provider_id: str) -> str | None:
        self._ensure_loaded()
        raw = self._state["model_lists"].get(provider_id, {})
        return raw.get("default_model")

    def save_model_list(
        self, provider_id: str, models: list[ModelInfo], default_model: str | None = None
    ):
        self._ensure_loaded()
        if default_model is None and models:
            default_model = models[0].model_id
        self._state["model_lists"][provider_id] = {
            "models": [m.model_dump() for m in models],
            "default_model": default_model,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def get_status(self, provider_id: str) -> InitStatusEnum:
        self._ensure_loaded()
        models_data = self._state["model_lists"].get(provider_id, {})
        has_key = bool(self._state["credentials"].get(provider_id, {}).get("api_key"))
        has_models = bool(models_data.get("models"))
        has_default = bool(models_data.get("default_model"))
        if has_key and has_default and has_models:
            return InitStatusEnum.READY
        if has_key and has_models:
            return InitStatusEnum.MODELS_SYNCED
        if has_key:
            return InitStatusEnum.KEY_SAVED
        return InitStatusEnum.NOT_CONFIGURED

    def get_overall_status(self) -> dict:
        self._ensure_loaded()
        ready = []
        worst = InitStatusEnum.NOT_CONFIGURED
        priority = [InitStatusEnum.NOT_CONFIGURED, InitStatusEnum.KEY_SAVED, InitStatusEnum.MODELS_SYNCED, InitStatusEnum.READY]
        for pid in self._state["credentials"]:
            s = self.get_status(pid)
            if s == InitStatusEnum.READY:
                ready.append(pid)
            if priority.index(s) > priority.index(worst):
                worst = s
        if ready:
            return {"status": InitStatusEnum.READY.value, "ready_providers": ready}
        return {"status": worst.value, "ready_providers": []}
