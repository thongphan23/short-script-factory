# Short Script Factory

Nhà máy sản xuất kịch bản video ngắn tự động — phần nguyên liệu đầu vào cho TPE Video Factory + Doodle Factory.

## Architecture

```
Brain2 (Obsidian Vault + pgvector)
        ↓ semantic search
Supabase (topic queue + script DB)
        ↓ generate + QA
Short Script Factory
        ↓ dispatch
Video Factory (tpe_videos) / Doodle Factory (input/)
```

## Quick Start

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Edit with your keys

# Generate a script
python cli.py run --topic "5 Sai Lầm Khi Dùng ChatGPT" --channel ai --target doodle

# Worker daemon (auto mode)
python worker.py --once --dry-run   # test first
python worker.py                    # start daemon

# API server (for Dashboard)
python api.py                       # http://localhost:5175
```

## Commands

| Command | Description |
|---------|-------------|
| `generate` | Generate 1 script (manual or from Forge) |
| `qa` | Score existing script |
| `dispatch` | Send approved script to factory |
| `run` | Full pipeline: generate → QA → (retry) → dispatch |
| `batch` | Batch generate from Forge/file |
| `show` | Pretty-print a script by ID |
| `status` | Show stats + metrics |
| `suggest` | AI topic suggestions (Brain2 + Forge) |
| `list-topics` | List Forge suggestions |

## Channels

- `ai` — AI & Công nghệ (Thông Phan — AI for Work)
- `viral` — Viral entertainment (GenZ)
- `tuhoc` — Tự học & Phát triển bản thân

## QA Scoring

5 dimensions × 20 points = 100 max
- Structure, Voice DNA, Hook, Content Depth, Format Compliance
- **AUTO-FAIL**: colon (`:`) or em-dash (`—`) in narration
- Pass threshold: ≥ 75/100

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Pipeline summary (topics, scripts, metrics) |
| `/api/scripts` | GET | List scripts (`?status=&channel=&limit=`) |
| `/api/scripts/:id` | GET | Script detail + formatted preview |
| `/api/generate` | POST | Queue a new topic |
| `/api/queue` | POST | Batch queue multiple topics |
| `/api/dispatch/:id` | POST | Dispatch a script to factory |
| `/api/suggestions` | GET | Topic suggestions (`?channel=&count=`) |
| `/health` | GET | Health check |

## Services

```bash
# Install as macOS launchctl services
bash scripts/install.sh

# Worker health:  http://localhost:5176
# API server:     http://localhost:5175
```

## Environment Variables

See `.env.example` for all configuration options.

Key variables:
- `VERTEX_API_KEY` + `VERTEX_BASE_URL` — LLM calls
- `SUPABASE_*` — Database
- `SUPABASE_DB_*` — PostgreSQL direct (pgvector)
- `EMBEDDING_PROVIDER=auto` — Fallback chain: Vertex → OpenAI → OpenRouter
- `WORKER_MAX_PER_HOUR=10` — Rate limiting

## Testing

```bash
python -m pytest tests/ -v --tb=short
```

96+ unit tests, all mocked (no real API calls in tests).