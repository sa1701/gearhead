"""Central config. Loads the secret key from .env so it never touches code."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


LOCAL_INTERVIEW_CHUNKS = 8
CLOUD_INTERVIEW_CHUNKS = 20


class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("GEARHEAD_MODEL", "claude-opus-4-8")
    # Cheap workhorse for offline bulk jobs (Fix DB extraction) — NOT the brain.
    extract_model: str = os.getenv("GEARHEAD_EXTRACT_MODEL", "claude-haiku-4-5-20251001")

    # Which brain to use: "claude", "ollama", or "auto" (claude if a key is set).
    provider: str = os.getenv("GEARHEAD_PROVIDER", "auto")
    ollama_model: str = os.getenv("GEARHEAD_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    ollama_host: str = os.getenv("GEARHEAD_OLLAMA_HOST", "http://127.0.0.1:11434")
    # GPU layers for Ollama. Unset = let Ollama decide; 0 = force CPU (useful when the GPU is throttled).
    ollama_num_gpu: str | None = os.getenv("GEARHEAD_OLLAMA_NUM_GPU")

    # How manual chunks are picked: "rerank" (search wide, then a local cross-encoder
    # re-orders) or "expand" (the older LLM query-expansion path).
    retrieval: str = os.getenv("GEARHEAD_RETRIEVAL", "rerank")
    rerank_model: str = os.getenv("GEARHEAD_RERANK_MODEL", "ms-marco-MiniLM-L-12-v2")
    rerank_pool: int = int(os.getenv("GEARHEAD_RERANK_POOL", "40"))  # candidates read by the reranker
    # Manual chunks the interview reasons over. Unset = pick by brain (see interview_chunk_count).
    interview_chunks: str | None = os.getenv("GEARHEAD_INTERVIEW_CHUNKS")

    manuals_dir: Path = PROJECT_ROOT / "manuals"
    chroma_dir: Path = PROJECT_ROOT / "chroma_db"
    images_dir: Path = PROJECT_ROOT / "page_images"
    models_dir: Path = PROJECT_ROOT / "models"

    def interview_chunk_count(self) -> int:
        """How many manual chunks the interview loads.

        A local model reads its context slowly (about 8 minutes for 20 chunks on a
        laptop CPU), so it gets the 8 best. A cloud model reads 20 in seconds.
        """
        if self.interview_chunks:
            return int(self.interview_chunks)
        return LOCAL_INTERVIEW_CHUNKS if self.resolved_provider() == "ollama" else CLOUD_INTERVIEW_CHUNKS

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
