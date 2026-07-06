"""Central config. Loads the secret key from .env so it never touches code."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("GEARHEAD_MODEL", "claude-opus-4-8")
    # Cheap workhorse for offline bulk jobs (Fix DB extraction) — NOT the brain.
    extract_model: str = os.getenv("GEARHEAD_EXTRACT_MODEL", "claude-haiku-4-5-20251001")

    # Which brain to use: "claude", "ollama", or "auto" (claude if a key is set).
    provider: str = os.getenv("GEARHEAD_PROVIDER", "auto")
    ollama_model: str = os.getenv("GEARHEAD_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    ollama_host: str = os.getenv("GEARHEAD_OLLAMA_HOST", "http://127.0.0.1:11434")

    manuals_dir: Path = PROJECT_ROOT / "manuals"
    chroma_dir: Path = PROJECT_ROOT / "chroma_db"
    images_dir: Path = PROJECT_ROOT / "page_images"

    def resolved_provider(self) -> str:
        if self.provider in ("claude", "ollama"):
            return self.provider
        has_key = bool(self.anthropic_api_key) and "PASTE-YOUR-KEY" not in self.anthropic_api_key
        return "claude" if has_key else "ollama"

    def check(self) -> None:
        """Fail loudly with a friendly message if the key isn't set yet."""
        if not self.anthropic_api_key or "PASTE-YOUR-KEY" in self.anthropic_api_key:
            raise RuntimeError(
                "No Anthropic API key found.\n"
                "Open C:\\Projects\\gearhead\\.env and replace the placeholder "
                "with your real key (starts with sk-ant-)."
            )


settings = Settings()
