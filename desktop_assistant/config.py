from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from .storage import quarantine_corrupted_file, write_json_atomic

try:
    import win32crypt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - available on Windows in the target env
    win32crypt = None


def default_provider_config_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "model_provider.json"


class ModelProviderConfig(BaseModel):
    provider_name: str = "OpenAI"
    base_url: str
    wire_api: str = "responses"
    model: str
    review_model: str
    model_reasoning_effort: str = "medium"
    disable_response_storage: bool = True
    requires_openai_auth: bool = True
    api_key: str = Field(repr=False)

    @property
    def masked_api_key(self) -> str:
        if len(self.api_key) < 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


class ProviderConfigStore:
    """Persist provider configuration locally.

    Plaintext api_key is supported for simple local development. The encrypted
    field remains supported for older configs.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_provider_config_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ModelProviderConfig:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            quarantine_corrupted_file(
                self.path,
                source="provider_config_store",
                category="provider_config_corrupted",
                reason="Provider config JSON is unreadable.",
            )
            raise ValueError(f"Provider config is unreadable: {self.path}") from exc
        if payload.get("api_key"):
            payload.pop("api_key_encrypted", None)
            try:
                return ModelProviderConfig.model_validate(payload)
            except Exception as exc:
                quarantine_corrupted_file(
                    self.path,
                    source="provider_config_store",
                    category="provider_config_invalid",
                    reason="Provider config fields are invalid.",
                )
                raise ValueError(f"Provider config is invalid: {self.path}") from exc

        encrypted_key = payload.pop("api_key_encrypted", None)
        if not encrypted_key:
            quarantine_corrupted_file(
                self.path,
                source="provider_config_store",
                category="provider_config_invalid",
                reason="Provider config is missing api_key/api_key_encrypted.",
            )
            raise KeyError("Provider config must contain api_key or api_key_encrypted.")
        payload["api_key"] = self._decrypt(encrypted_key)
        try:
            return ModelProviderConfig.model_validate(payload)
        except Exception as exc:
            quarantine_corrupted_file(
                self.path,
                source="provider_config_store",
                category="provider_config_invalid",
                reason="Provider config fields are invalid.",
            )
            raise ValueError(f"Provider config is invalid: {self.path}") from exc

    def save(self, config: ModelProviderConfig) -> None:
        payload = config.model_dump(mode="json")
        api_key = payload.pop("api_key")
        payload["api_key_encrypted"] = self._encrypt(api_key)
        write_json_atomic(self.path, payload)

    def exists(self) -> bool:
        return self.path.exists()

    def load_or_raise(self) -> ModelProviderConfig:
        if not self.exists():
            raise FileNotFoundError(f"Provider config not found: {self.path}")
        return self.load()

    def config_from_env(self) -> ModelProviderConfig | None:
        env_data = {
            "provider_name": os.getenv("DESKTOP_ASSISTANT_PROVIDER_NAME", "OpenAI"),
            "base_url": os.getenv("DESKTOP_ASSISTANT_BASE_URL"),
            "wire_api": os.getenv("DESKTOP_ASSISTANT_WIRE_API", "responses"),
            "model": os.getenv("DESKTOP_ASSISTANT_MODEL"),
            "review_model": os.getenv("DESKTOP_ASSISTANT_REVIEW_MODEL"),
            "model_reasoning_effort": os.getenv("DESKTOP_ASSISTANT_REASONING_EFFORT", "medium"),
            "disable_response_storage": os.getenv("DESKTOP_ASSISTANT_DISABLE_RESPONSE_STORAGE", "true").lower()
            != "false",
            "requires_openai_auth": os.getenv("DESKTOP_ASSISTANT_REQUIRES_OPENAI_AUTH", "true").lower()
            != "false",
            "api_key": os.getenv("DESKTOP_ASSISTANT_API_KEY"),
        }
        if not all([env_data["base_url"], env_data["model"], env_data["review_model"], env_data["api_key"]]):
            return None
        return ModelProviderConfig.model_validate(env_data)

    def bootstrap_from_env(self) -> ModelProviderConfig | None:
        config = self.config_from_env()
        if config is None:
            return None
        self.save(config)
        return config

    @staticmethod
    def _encrypt(value: str) -> str:
        raw = value.encode("utf-8")
        if win32crypt is not None:
            encrypted = win32crypt.CryptProtectData(raw, "desktop-assistant", None, None, None, 0)
            return base64.b64encode(encrypted).decode("ascii")
        return base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _decrypt(payload: str) -> str:
        raw = base64.b64decode(payload)
        if win32crypt is not None:
            return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1].decode("utf-8")
        return raw.decode("utf-8")

    def describe(self) -> dict[str, Any]:
        if not self.exists():
            return {"exists": False, "path": str(self.path)}
        config = self.load()
        return {
            "exists": True,
            "path": str(self.path),
            "provider_name": config.provider_name,
            "base_url": config.base_url,
            "model": config.model,
            "review_model": config.review_model,
            "reasoning_effort": config.model_reasoning_effort,
            "api_key_masked": config.masked_api_key,
        }
