from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class SupabaseConfig(BaseModel):
    url: str = ""
    key: str = ""
    enabled: bool = False


_DEFAULT_CONFIG_PATH: Path | None = None


def default_config_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "supabase_config.json"


class SupabaseConfigStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    def load(self) -> SupabaseConfig:
        if not self.path.exists():
            return SupabaseConfig()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            return SupabaseConfig.model_validate(payload)
        except Exception:
            return SupabaseConfig()

    def save(self, config: SupabaseConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def describe(self) -> str:
        config = self.load()
        if not config.enabled:
            return "Supabase sync: disabled"
        masked = config.key[:10] + "..." if len(config.key) > 10 else config.key
        return f"Supabase sync: enabled (url={config.url}, key={masked})"
