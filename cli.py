#!/usr/bin/env python3
"""
Short Script Factory — CLI Entry Point

Usage:
  python cli.py generate --topic "..." --channel ai --target doodle
  python cli.py generate --from-forge --channel ai --limit 3
  python cli.py qa --script-id UUID
  python cli.py dispatch --script-id UUID
  python cli.py status
  python cli.py list-topics --channel ai
  python cli.py run --topic "..." --channel ai --target doodle [--auto-dispatch]

Full pipeline (1 lệnh):
  python cli.py run --topic "..." --channel ai --target doodle
  → generate → QA → nếu ≥75 → auto dispatch
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone

from engine.config import OUTPUT_SCRIPTS_DIR

# ── Subcommand handlers ───────────────────────────────────────────────────────
def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a new script (manual input or from Forge)."""
    from engine.script_writer import generate_script
    from engine.brain2_client import get_context_for_topic
    from engine.forge_client import get_forge_suggestions

    if args.from_forge:
        topics = get_forge_suggestions(channel=args.channel, limit=args.limit)
        if not topics:
            print(f"No Forge suggestions for channel={args.channel}")
            return 1
        topic = topics[0]["suggested_topic"]
        forge_context = f"Hook: {topics[0].get('suggested_hook', '')}"
        print(f"[Forge] Using topic: {topic}")
    else:
        topic = args.topic
        forge_context = ""

    brain2_ctx = get_context_for_topic(topic)

    print(f"[Writer] Generating script for: {topic[:60]}...")
    script = generate_script(
        topic=topic,
        channel=args.channel,
        target_factory=args.target,
        brain2_context=brain2_ctx,
        forge_context=forge_context,
    )
    scenes = len(script.get("scenes", []))
    print(f"[Writer] Generated: {scenes} scenes")

    # Save to DB
    from engine.supabase_client import get_client
    from engine.script_qa import score_script

    client = get_client()

    # Insert topic
    topic_row = client.table("tpe_script_topics").insert({
        "topic": topic,
        "source": "manual" if not args.from_forge else "forge",
        "channel": args.channel,
        "target_factory": args.target,
        "brain2_context": [{"query": topic, "similarity": 0.5}],  # simplified
        "status": "generating",
    }).execute().data[0]
    topic_id = topic_row["id"]

    # Insert script
    script_row = client.table("tpe_scripts").insert({
        "topic_id": topic_id,
        "script_json": script,
        "target_factory": args.target,
        "channel": args.channel,
        "status": "draft",
    }).execute().data[0]
    script_id = script_row["id"]
    print(f"[DB] Script saved: {script_id}")

    # QA
    print(f"[QA] Scoring script...")
    result = score_script(script, channel=args.channel, target_factory=args.target)

    # Update script row with QA score
    client.table("tpe_scripts").update({
        "qa_score": result.score,
        "qa_details": result.details,
        "qa_feedback": result.feedback,
        "status": "qa_pass" if result.passed else "draft",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", script_id).execute()

    client.table("tpe_script_topics").update({
        "status": "review" if not result.passed else "approved",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", topic_id).execute()

    print(f"[QA] Score: {result.score}/100 — {'PASS' if result.passed else 'FAIL'}")
    for dim, info in result.details.items():
        print(f"       {dim}: {info['score']}/20")
    if result.feedback:
        for fb in result.feedback:
            print(f"       → {fb}")

    print(f"\n[Script ID] {script_id}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    """Run QA on an existing script by ID."""
    from engine.supabase_client import get_client
    from engine.script_qa import score_script

    client = get_client()
    result = client.table("tpe_scripts").select("*").eq("id", str(args.script_id)).execute()

    if not result.data:
        print(f"Script not found: {args.script_id}")
        return 1

    script_row = result.data[0]
    script = script_row["script_json"]
    channel = script_row["channel"]
    target = script_row["target_factory"]

    print(f"[QA] Script {args.script_id} ({channel}, {target})")
    result_qa = score_script(script, channel=channel, target_factory=target)

    print(f"Score: {result_qa.score}/100 — {'PASS' if result_qa.passed else 'FAIL'}")
    for dim, info in result_qa.details.items():
        print(f"  {dim}: {info['score']}/20")
    if result_qa.feedback:
        print("Feedback:")
        for fb in result_qa.feedback:
            print(f"  → {fb}")

    client.table("tpe_scripts").update({
        "qa_score": result_qa.score,
        "qa_details": result_qa.details,
        "qa_feedback": result_qa.feedback,
        "status": "qa_pass" if result_qa.passed else script_row["status"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", str(args.script_id)).execute()
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Dispatch an approved script to its target factory."""
    from engine.dispatcher import dispatch

    script_id = uuid.UUID(str(args.script_id))
    print(f"[Dispatch] Dispatching script {script_id}...")
    summary = dispatch(script_id)
    print(f"[Dispatch] {summary}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Pretty-print a script by ID."""
    from engine.supabase_client import get_client
    from engine.formatter import format_script_for_review

    client = get_client()
    result = client.table("tpe_scripts").select("*").eq("id", str(args.script_id)).execute()

    if not result.data:
        print(f"Script not found: {args.script_id}")
        return 1

    row = result.data[0]
    script = row["script_json"]
    target = row.get("target_factory", "doodle")
    qa_score = row.get("qa_score", 0)
    status = row.get("status", "unknown")

    print(f"=== Script {args.script_id} ===")
    print(f"Status: {status}  |  QA Score: {qa_score}/100")
    print(format_script_for_review(script, target_factory=target))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show overview of all topics, scripts, and metrics."""
    from engine.supabase_client import get_client
    from engine.metrics import get_stats_summary

    client = get_client()

    # Topics counts
    topic_counts = {}
    for status in ("queued", "generating", "review", "approved", "dispatched", "rejected", "error"):
        r = client.table("tpe_script_topics").select("id", count="exact").eq("status", status).execute()
        topic_counts[status] = r.count or 0

    print("=== Topics ===")
    total_topics = sum(topic_counts.values())
    print(f"Total: {total_topics}")
    for s, n in topic_counts.items():
        if n > 0:
            print(f"  {s}: {n}")

    # Scripts counts
    script_counts = {}
    for status in ("draft", "qa_pass", "approved", "dispatched", "rejected", "error"):
        r = client.table("tpe_scripts").select("id", count="exact").eq("status", status).execute()
        script_counts[status] = r.count or 0

    print("\n=== Scripts ===")
    total_scripts = sum(script_counts.values())
    print(f"Total: {total_scripts}")
    for s, n in script_counts.items():
        if n > 0:
            print(f"  {s}: {n}")

    # QA scores summary
    scored = client.table("tpe_scripts").select("qa_score").gt("qa_score", 0).execute()
    if scored.data:
        scores = [r["qa_score"] for r in scored.data if r["qa_score"]]
        avg = sum(scores) / len(scores)
        print(f"\nQA avg: {avg:.1f}/100 ({len(scores)} scored)")

    # Metrics summary
    stats = get_stats_summary()
    if stats["total"] > 0:
        print(f"\n=== Metrics ===")
        print(f"  Total generations: {stats['total']}")
        print(f"  Avg QA score: {stats['avg_qa']}/100")
        print(f"  Pass rate: {stats['pass_rate']:.0%}")
        for ch, info in stats.get("by_channel", {}).items():
            ch_rate = f"{info['passed']/info['total']:.0%}" if info["total"] else "0%"
            print(f"    {ch}: {info['total']} total, {ch_rate} pass")

    return 0


def cmd_list_topics(args: argparse.Namespace) -> int:
    """List Forge suggestions for a channel."""
    from engine.forge_client import get_forge_suggestions

    topics = get_forge_suggestions(channel=args.channel, limit=args.limit)
    if not topics:
        print(f"No Forge suggestions for channel={args.channel}")
        return 0

    print(f"=== Forge Suggestions ({args.channel}, {len(topics)} items) ===")
    for t in topics:
        score = t.get("total_score", "?")
        hook = t.get("suggested_hook", "")
        print(f"[{score}] {t['suggested_topic']}")
        if hook:
            print(f"      hook: {hook[:80]}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Batch generate multiple scripts from Forge or a topics file."""
    from engine.script_writer import generate_script
    from engine.brain2_client import get_context_for_topic
    from engine.supabase_client import get_client
    from engine.script_qa import score_script
    from pathlib import Path

    if args.source == "forge":
        from engine.forge_client import get_forge_suggestions
        topics = get_forge_suggestions(channel=args.channel, limit=args.count)
        topic_list = [t["suggested_topic"] for t in topics]
    elif args.source == "manual" and args.topics_file:
        lines = Path(args.topics_file).read_text(encoding="utf-8").strip().split("\n")
        topic_list = [l.strip() for l in lines if l.strip()]
    else:
        print("ERROR: --source forge or --source manual --topics-file required")
        return 1

    topic_list = topic_list[: args.count]
    results: list[dict] = []
    client = get_client()

    for i, t in enumerate(topic_list, 1):
        print(f"\n[{i}/{len(topic_list)}] {t[:60]}...")
        try:
            brain2_ctx = get_context_for_topic(t)
            script = generate_script(
                topic=t,
                channel=args.channel,
                target_factory=args.target,
                brain2_context=brain2_ctx,
                forge_context="",
            )
            scenes = len(script.get("scenes", []))
            print(f"  Generated: {scenes} scenes")

            # Save to DB
            topic_row = client.table("tpe_script_topics").insert({
                "topic": t,
                "source": "manual",
                "channel": args.channel,
                "target_factory": args.target,
                "status": "generating",
            }).execute().data[0]
            topic_id = topic_row["id"]

            script_row = client.table("tpe_scripts").insert({
                "topic_id": topic_id,
                "script_json": script,
                "target_factory": args.target,
                "channel": args.channel,
                "status": "draft",
            }).execute().data[0]
            script_id = script_row["id"]

            qa = score_script(script, channel=args.channel, target_factory=args.target)
            client.table("tpe_scripts").update({
                "qa_score": qa.score,
                "qa_details": qa.details,
                "qa_feedback": qa.feedback,
                "status": "qa_pass" if qa.passed else "draft",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", script_id).execute()
            client.table("tpe_script_topics").update({
                "status": "approved" if qa.passed else "review",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", topic_id).execute()

            results.append({"topic": t, "script_id": script_id, "score": qa.score, "passed": qa.passed})
            status_icon = "PASS" if qa.passed else "FAIL"
            print(f"  QA: {qa.score}/100 — {status_icon}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({"topic": t, "script_id": None, "score": 0, "passed": False})

    # Summary
    print("\n=== BATCH RESULTS ===")
    passed_n = sum(1 for r in results if r["passed"])
    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  [{icon}] [{r['score']}/100] {r['topic'][:50]}")
    print(f"\nTotal: {len(results)}, Passed: {passed_n}/{len(results)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: generate → QA → (optional retry) → (optional auto-dispatch)."""
    from engine.script_writer import generate_script
    from engine.brain2_client import get_context_for_topic
    from engine.supabase_client import get_client
    from engine.script_qa import score_script
    from engine.dispatcher import dispatch

    topic = args.topic
    brain2_ctx = get_context_for_topic(topic)
    max_retries = min(max(0, args.max_retries), 3)
    qa_feedback: list[str] = []
    client = get_client()

    # Save topic to DB first
    topic_row = client.table("tpe_script_topics").insert({
        "topic": topic,
        "source": "manual",
        "channel": args.channel,
        "target_factory": args.target,
        "status": "generating",
    }).execute().data[0]
    topic_id = topic_row["id"]

    # Generate + QA loop (with optional retry)
    revision = 0
    script = None
    qa_result = None
    script_id = None

    while True:
        attempt = "initial" if revision == 0 else f"retry {revision}"
        print(f"[Run] Generating ({attempt}): {topic[:60]}...")

        # Catch schema validation errors → treat as QA fail with feedback
        try:
            script = generate_script(
                topic=topic,
                channel=args.channel,
                target_factory=args.target,
                brain2_context=brain2_ctx,
                forge_context="",
                qa_feedback=qa_feedback or None,
            )
        except ValueError as exc:
            schema_errors = str(exc)
            print(f"[Run] Schema validation failed: {schema_errors[:100]}")
            if revision >= max_retries:
                print(f"[Run] Max retries ({max_retries}) reached.")
                client.table("tpe_script_topics").update({
                    "status": "error",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", topic_id).execute()
                return 1
            qa_feedback = [f"Schema error: {schema_errors[:200]}"]
            revision += 1
            continue

        scenes = len(script.get("scenes", []))
        print(f"[Run] Generated: {scenes} scenes")

        print(f"[QA] Scoring...")
        qa_result = score_script(script, channel=args.channel, target_factory=args.target)
        print(f"[QA] Score: {qa_result.score}/100 — {'PASS' if qa_result.passed else 'FAIL'}")

        if revision == 0:
            script_row = client.table("tpe_scripts").insert({
                "topic_id": topic_id,
                "script_json": script,
                "target_factory": args.target,
                "channel": args.channel,
                "status": "draft",
                "revision_count": revision,
            }).execute().data[0]
            script_id = script_row["id"]
        else:
            # Insert new revision as new row
            script_row = client.table("tpe_scripts").insert({
                "topic_id": topic_id,
                "script_json": script,
                "target_factory": args.target,
                "channel": args.channel,
                "status": "draft",
                "revision_count": revision,
            }).execute().data[0]
            script_id = script_row["id"]

        client.table("tpe_scripts").update({
            "qa_score": qa_result.score,
            "qa_details": qa_result.details,
            "qa_feedback": qa_result.feedback,
            "status": "qa_pass" if qa_result.passed else "draft",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", script_id).execute()

        if qa_result.passed:
            break

        if revision >= max_retries:
            print(f"[Run] Max retries ({max_retries}) reached. Giving up.")
            client.table("tpe_script_topics").update({
                "status": "error",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", topic_id).execute()
            return 1

        print(f"[Run] QA failed. Feedback:")
        for fb in (qa_result.feedback or [])[:3]:
            print(f"      → {fb}")
        qa_feedback = qa_result.feedback or []
        revision += 1

    # Final update
    client.table("tpe_script_topics").update({
        "status": "approved",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", topic_id).execute()

    if args.auto_dispatch:
        print(f"[Dispatch] Auto-dispatching...")
        dispatch(uuid.UUID(script_id))
        print("[Dispatch] Done!")
    else:
        print(f"[Run] Script {script_id} approved (qa_pass). Dispatch manually with:")
        print(f"      python cli.py dispatch --script-id {script_id}")

    return 0


# ── Argument parser ──────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="short-script",
        description="Short Script Factory — generate video scripts with AI.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # generate
    g = sub.add_parser("generate", help="Generate a new script")
    g.add_argument("--topic", help="Topic (required if not --from-forge)")
    g.add_argument("--from-forge", action="store_true", help="Use topic from Forge Engine")
    g.add_argument("--channel", default="ai", choices=["ai", "viral", "tuhoc"])
    g.add_argument("--target", default="doodle", choices=["video", "doodle"])
    g.add_argument("--limit", type=int, default=5)
    g.set_defaults(func=cmd_generate)

    # qa
    q = sub.add_parser("qa", help="Run QA on existing script")
    q.add_argument("--script-id", required=True, help="Script UUID")
    q.set_defaults(func=cmd_qa)

    # dispatch
    d = sub.add_parser("dispatch", help="Dispatch approved script to factory")
    d.add_argument("--script-id", required=True, help="Script UUID")
    d.set_defaults(func=cmd_dispatch)

    # status
    s = sub.add_parser("status", help="Show overview stats")
    s.set_defaults(func=cmd_status)

    # show
    sh = sub.add_parser("show", help="Pretty-print a script by ID")
    sh.add_argument("--script-id", required=True, help="Script UUID")
    sh.set_defaults(func=cmd_show)

    # list-topics
    lt = sub.add_parser("list-topics", help="List Forge suggestions")
    lt.add_argument("--channel", default="ai", choices=["ai", "viral", "tuhoc"])
    lt.add_argument("--limit", type=int, default=10)
    lt.set_defaults(func=cmd_list_topics)

    # batch
    b = sub.add_parser("batch", help="Batch generate multiple scripts")
    b.add_argument("--channel", default="ai", choices=["ai", "viral", "tuhoc"])
    b.add_argument("--target", default="doodle", choices=["video", "doodle"])
    b.add_argument("--count", type=int, default=5, help="Number of scripts to generate")
    src_group = b.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--source", choices=["forge", "manual"],
                          help="'forge' = from Forge suggestions, 'manual' = from --topics-file")
    b.add_argument("--topics-file", help="Path to text file with one topic per line")
    b.set_defaults(func=cmd_batch)

    # run
    r = sub.add_parser("run", help="Full pipeline: generate → QA → dispatch")
    r.add_argument("--topic", required=True, help="Topic")
    r.add_argument("--channel", default="ai", choices=["ai", "viral", "tuhoc"])
    r.add_argument("--target", default="doodle", choices=["video", "doodle"])
    r.add_argument("--auto-dispatch", action="store_true", help="Auto dispatch if QA pass")
    r.add_argument("--max-retries", type=int, default=0,
                   help="Auto-retry with QA feedback (0=no retry, max=3)")
    r.set_defaults(func=cmd_run)

    return parser


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
