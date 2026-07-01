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

    manuals_dir: Path = PROJECT_ROOT / "manuals"
    chroma_dir: Path = PROJECT_ROOT / "chroma_db"
    images_dir: Path = PROJECT_ROOT / "page_images"

    def check(self) -> None:
        """Fail loudly with a friendly message if the key isn't set yet."""
        if not self.anthropic_api_key or "PASTE-YOUR-KEY" in self.anthropic_api_key:
            raise RuntimeError(
                "No Anthropic API key found.\n"
                "Open C:\\Projects\\gearhead\\.env and replace the placeholder "
                "with your real key (starts with sk-ant-)."
            )


settings = Settings()
