import os
import tempfile
from pathlib import Path

import pytest

from blackboard.config.credentials import CredentialManager, ModelInfo, mask_key
from blackboard.config.models import InitStatusEnum, ModelType


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def cred_mgr(temp_dir):
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
    mgr = CredentialManager(config_dir=temp_dir)
    return mgr


from cryptography.fernet import Fernet


class TestMaskKey:
    def test_short_key(self):
        assert mask_key("abc") == "****"

    def test_long_key(self):
        assert mask_key("sk-1234567890abcdef") == "sk-1***********cdef"


class TestCredentialManager:
    def test_init_without_key_raises(self, temp_dir):
        old = os.environ.pop("FERNET_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="FERNET_KEY not set"):
                CredentialManager(config_dir=temp_dir)
        finally:
            if old:
                os.environ["FERNET_KEY"] = old

    def test_save_and_get_api_key(self, cred_mgr):
        cred_mgr.save_api_key("deepseek", "sk-test123", "https://custom.example.com")
        assert cred_mgr.get_api_key("deepseek") == "sk-test123"
        assert cred_mgr.get_base_url_override("deepseek") == "https://custom.example.com"

    def test_get_missing_key(self, cred_mgr):
        assert cred_mgr.get_api_key("nonexistent") is None

    def test_delete(self, cred_mgr):
        cred_mgr.save_api_key("openai", "sk-openai")
        cred_mgr.save_model_list("openai", [ModelInfo(model_id="gpt-4o")])
        cred_mgr.delete("openai")
        assert cred_mgr.get_api_key("openai") is None
        assert cred_mgr.get_model_list("openai") == []

    def test_list_credentials(self, cred_mgr):
        cred_mgr.save_api_key("deepseek", "sk-deepseek")
        cred_mgr.save_model_list("deepseek", [ModelInfo(model_id="deepseek-chat")])
        result = cred_mgr.list_credentials()
        assert "deepseek" in result
        assert result["deepseek"]["api_key"] == mask_key("sk-deepseek")
        assert result["deepseek"]["status"] == InitStatusEnum.READY.value

    def test_model_list(self, cred_mgr):
        models = [
            ModelInfo(
                model_id="gpt-4o",
                display_name="GPT-4o",
                model_type=ModelType.CHAT,
                supports_tools=True,
            ),
        ]
        cred_mgr.save_model_list("openai", models, default_model="gpt-4o")
        loaded = cred_mgr.get_model_list("openai")
        assert len(loaded) == 1
        assert loaded[0].model_id == "gpt-4o"
        assert loaded[0].supports_tools is True
        assert cred_mgr.get_default_model("openai") == "gpt-4o"

    def test_status_flow(self, cred_mgr):
        assert cred_mgr.get_status("deepseek") == InitStatusEnum.NOT_CONFIGURED
        cred_mgr.save_api_key("deepseek", "sk-test")
        assert cred_mgr.get_status("deepseek") == InitStatusEnum.KEY_SAVED
        # save_model_list auto-sets default_model to first model → jumps to READY
        cred_mgr.save_model_list("deepseek", [ModelInfo(model_id="ds-chat")])
        assert cred_mgr.get_status("deepseek") == InitStatusEnum.READY

    def test_overall_status(self, cred_mgr):
        assert cred_mgr.get_overall_status()["status"] == InitStatusEnum.NOT_CONFIGURED.value
        cred_mgr.save_api_key("deepseek", "sk-test")
        cred_mgr.save_model_list("deepseek", [ModelInfo(model_id="ds-chat")], default_model="ds-chat")
        overall = cred_mgr.get_overall_status()
        assert overall["status"] == InitStatusEnum.READY.value
        assert "deepseek" in overall["ready_providers"]

    def test_persistence(self, temp_dir):
        key = Fernet.generate_key().decode()
        os.environ["FERNET_KEY"] = key
        mgr1 = CredentialManager(config_dir=temp_dir)
        mgr1.save_api_key("groq", "sk-groq")
        mgr1.save_model_list("groq", [ModelInfo(model_id="llama-70b")], default_model="llama-70b")

        mgr2 = CredentialManager(config_dir=temp_dir)
        assert mgr2.get_api_key("groq") == "sk-groq"
        assert mgr2.get_default_model("groq") == "llama-70b"