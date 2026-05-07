from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from desktop_assistant.config import ModelProviderConfig, ProviderConfigStore


class ProviderConfigStoreTests(unittest.TestCase):
    @contextmanager
    def _config_path(self):
        base_dir = Path.cwd() / "runtime" / "test_config"
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"{uuid4().hex}.json"
        try:
            if path.exists():
                path.unlink()
            yield path
        finally:
            if path.exists():
                path.unlink()

    def test_round_trip_save_and_load(self) -> None:
        with self._config_path() as config_path:
            store = ProviderConfigStore(path=config_path)
            config = ModelProviderConfig(
                provider_name="OpenAI",
                base_url="https://example.com",
                wire_api="responses",
                model="gpt-5.4",
                review_model="gpt-5.4",
                model_reasoning_effort="xhigh",
                disable_response_storage=True,
                requires_openai_auth=True,
                api_key="sk-test-secret",
            )

            store.save(config)
            loaded = store.load()

            self.assertEqual(loaded.base_url, "https://example.com")
            self.assertEqual(loaded.model, "gpt-5.4")
            self.assertEqual(loaded.api_key, "sk-test-secret")

    def test_load_plaintext_api_key_config(self) -> None:
        with self._config_path() as config_path:
            config_path.write_text(
                """
                {
                  "provider_name": "OpenAI",
                  "base_url": "https://example.com",
                  "wire_api": "responses",
                  "model": "gpt-5.4",
                  "review_model": "gpt-5.4",
                  "model_reasoning_effort": "xhigh",
                  "disable_response_storage": true,
                  "requires_openai_auth": true,
                  "api_key": "sk-plain-test"
                }
                """,
                encoding="utf-8",
            )

            loaded = ProviderConfigStore(path=config_path).load()

            self.assertEqual(loaded.base_url, "https://example.com")
            self.assertEqual(loaded.api_key, "sk-plain-test")

    def test_load_plaintext_api_key_config_with_utf8_bom(self) -> None:
        with self._config_path() as config_path:
            config_path.write_text(
                '\ufeff{"base_url":"https://example.com","model":"gpt-5.4","review_model":"gpt-5.4","api_key":"sk-bom-test"}',
                encoding="utf-8",
            )

            loaded = ProviderConfigStore(path=config_path).load()

            self.assertEqual(loaded.api_key, "sk-bom-test")

    def test_save_keeps_existing_file_when_atomic_replace_fails(self) -> None:
        with self._config_path() as config_path:
            config_path.write_text('{"api_key":"old"}', encoding="utf-8")
            store = ProviderConfigStore(path=config_path)
            config = ModelProviderConfig(
                provider_name="OpenAI",
                base_url="https://example.com",
                wire_api="responses",
                model="gpt-5.4",
                review_model="gpt-5.4",
                model_reasoning_effort="xhigh",
                disable_response_storage=True,
                requires_openai_auth=True,
                api_key="sk-test-secret",
            )

            with patch("desktop_assistant.storage.json_files.os.replace", side_effect=OSError("disk busy")):
                with self.assertRaises(OSError):
                    store.save(config)

            self.assertEqual(config_path.read_text(encoding="utf-8"), '{"api_key":"old"}')

    def test_load_quarantines_invalid_provider_config(self) -> None:
        with self._config_path() as config_path:
            config_path.write_text('{"provider_name":"OpenAI"}', encoding="utf-8")

            with self.assertRaises((KeyError, ValueError)):
                ProviderConfigStore(path=config_path).load()

            self.assertFalse(config_path.exists())
            quarantined = list(config_path.parent.glob(f"{config_path.name}.corrupt*"))
            self.assertEqual(len(quarantined), 1)


if __name__ == "__main__":
    unittest.main()
