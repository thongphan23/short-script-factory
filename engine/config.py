"""
Config loader — reads .env from project root.
All secrets stay here; no hardcoding elsewhere.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ── LLM ───────────────────────────────────────────────────────────────────
VERTEX_API_KEY: str = os.getenv("VERTEX_API_KEY", "")
VERTEX_BASE_URL: str = os.getenv("VERTEX_BASE_URL", "https://omega.vertex-key.com/v1")
MODEL_WRITER: str = os.getenv("MODEL_WRITER", "claude-sonnet-4-6")
MODEL_QA: str = os.getenv("MODEL_QA", "gemini-2.0-flash")

# ── Supabase ──────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Embedding providers (fallback chain: openai → openrouter) ─────────────
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "auto")  # auto|openai|openrouter|vertex
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

# ── Supabase Postgres (direct pgvector) ───────────────────────────────────
SUPABASE_DB_HOST: str = os.getenv("SUPABASE_DB_HOST", "")
SUPABASE_DB_PORT: int = int(os.getenv("SUPABASE_DB_PORT", "5432"))
SUPABASE_DB_NAME: str = os.getenv("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER: str = os.getenv("SUPABASE_DB_USER", "")
SUPABASE_DB_PASSWORD: str = os.getenv("SUPABASE_DB_PASSWORD", "")

# ── Paths ──────────────────────────────────────────────────────────────────
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
OUTPUT_SCRIPTS_DIR: Path = OUTPUT_DIR / "scripts"

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
