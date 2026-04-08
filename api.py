"""
Short Script Factory — FastAPI webhook for Dashboard integration.

Run:  python api.py          (starts on port 5175)
Test: curl http://localhost:5175/api/status

Endpoints:
  GET  /api/status        — pipeline summary (topics + scripts + metrics)
  GET  /api/scripts       — list scripts (optional ?status=&channel=&limit=)
  GET  /api/scripts/:id   — script detail + formatted preview
  POST /api/generate      — queue a new topic for generation
  POST /api/queue          — batch queue multiple topics
  POST /api/dispatch/:id   — dispatch a script to its factory
  GET  /api/suggestions   — topic suggestions from Brain2 + Forge
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Short Script Factory API", version="1.0")

# ── CORS — allow Dashboard (port 5174) ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    topic: str
    channel: str = "ai"
    target_factory: str = "doodle"
    auto_dispatch: bool = False


class TopicQueueRequest(BaseModel):
    topics: list[str]
    channel: str = "ai"
    target_factory: str = "doodle"
    auto_mode: bool = True


# ── GET /api/status ──────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    """Return pipeline status summary: topics, scripts, metrics."""
    from engine.metrics import get_stats_summary
    from engine.supabase_client import get_client
    client = get_client()

    # Topic counts
    topic_counts: dict[str, int] = {}
    for status in ("queued", "generating", "review", "approved", "dispatched", "rejected", "error"):
        r = client.table("tpe_script_topics").select("id", count="exact").eq("status", status).execute()
        topic_counts[status] = r.count or 0

    # Script counts
    script_counts: dict[str, int] = {}
    for status in ("draft", "qa_pass", "approved", "dispatched", "rejected", "error"):
        r = client.table("tpe_scripts").select("id", count="exact").eq("status", status).execute()
        script_counts[status] = r.count or 0

    metrics = get_stats_summary()

    return {
        "topics": topic_counts,
        "scripts": script_counts,
        "metrics": metrics,
    }


# ── GET /api/scripts ─────────────────────────────────────────────────────────
@app.get("/api/scripts")
async def list_scripts(status: str = None, channel: str = None, limit: int = 20):
    """List scripts with optional filters."""
    from engine.supabase_client import get_client
    client = get_client()

    query = client.table("tpe_scripts").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if channel:
        query = query.eq("channel", channel)

    result = query.execute()
    return {"scripts": result.data, "total": len(result.data)}


# ── GET /api/scripts/{script_id} ─────────────────────────────────────────────
@app.get("/api/scripts/{script_id}")
async def get_script(script_id: str):
    """Get a specific script with formatted preview."""
    from engine.supabase_client import get_client
    from engine.formatter import format_script_for_review

    client = get_client()
    result = client.table("tpe_scripts").select("*").eq("id", script_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Script not found")

    script_row = result.data[0]
    preview = format_script_for_review(script_row["script_json"], script_row["target_factory"])

    return {
        "script": script_row,
        "preview": preview,
    }


# ── POST /api/generate ───────────────────────────────────────────────────────
@app.post("/api/generate")
async def generate_script_endpoint(req: GenerateRequest):
    """Queue a topic for generation."""
    from engine.supabase_client import get_client
    client = get_client()

    topic_row = client.table("tpe_script_topics").insert({
        "topic": req.topic,
        "source": "api",
        "channel": req.channel,
        "target_factory": req.target_factory,
        "auto_mode": req.auto_dispatch,
        "status": "queued",
    }).execute().data[0]

    return {
        "message": "Topic queued for generation",
        "topic_id": topic_row["id"],
        "status": "queued",
    }


# ── POST /api/queue ──────────────────────────────────────────────────────────
@app.post("/api/queue")
async def queue_topics(req: TopicQueueRequest):
    """Batch queue multiple topics."""
    from engine.supabase_client import get_client
    client = get_client()

    inserted: list[str] = []
    for topic in req.topics:
        row = client.table("tpe_script_topics").insert({
            "topic": topic,
            "source": "api",
            "channel": req.channel,
            "target_factory": req.target_factory,
            "auto_mode": req.auto_mode,
            "status": "queued",
        }).execute().data[0]
        inserted.append(row["id"])

    return {
        "message": f"Queued {len(inserted)} topics",
        "topic_ids": inserted,
    }


# ── POST /api/dispatch/{script_id} ───────────────────────────────────────────
@app.post("/api/dispatch/{script_id}")
async def dispatch_script(script_id: str):
    """Dispatch a script to its target factory."""
    import uuid as _uuid
    from engine.dispatcher import dispatch

    try:
        result = dispatch(_uuid.UUID(script_id))
        return {"message": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /api/suggestions ──────────────────────────────────────────────────────
@app.get("/api/suggestions")
async def get_suggestions(channel: str = "ai", count: int = 5):
    """Get topic suggestions from Brain2 + Forge."""
    from engine.topic_engine import suggest_topics
    topics = suggest_topics(channel=channel, count=count)
    return {"suggestions": topics}


# ── GET /api/topics ───────────────────────────────────────────────────────────
@app.get("/api/topics")
async def list_topics(status: str = None, channel: str = None, limit: int = 50):
    """List topics with optional filters."""
    from engine.supabase_client import get_client
    client = get_client()

    query = client.table("tpe_script_topics").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if channel:
        query = query.eq("channel", channel)

    result = query.execute()
    return {"topics": result.data, "total": len(result.data)}


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5175)