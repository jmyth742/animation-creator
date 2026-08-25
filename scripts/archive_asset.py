#!/usr/bin/env python3
"""
Production archive — keep the evidence, not just the output.

Every defect this pipeline has produced looked fine until someone compared two
pictures. Those comparisons are the record of how the show was made, and they
are worth more as footage than they cost in disk. They are also easy to lose:
clips get archived into ep04-badS2V/, scratch frames live in a temp directory
that will not survive the week, and the prompt that produced a shot is
regenerated from a bible that has since changed.

This records an ASSET together with WHY it matters and WHAT PRODUCED IT, so a
frame is still legible months later.

    archive_asset.py add <id> --title "..." --category defect \\
        --files a.png b.mp4 --note "why this matters" \\
        --prompt "the prompt that produced it" --metric "identity 0.632"

    archive_asset.py shot <series> <scene_id>     # snapshot a shot + its prompt
    archive_asset.py list [--category defect]
    archive_asset.py index                        # rebuild INDEX.md

Categories:
    defect      something wrong, with the evidence
    fix         the same thing after, for the before/after cut
    milestone   a finished artifact (an episode, a set library)
    reference   an anchor, plate or dataset sample
    measurement a table, score or baseline
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ARCHIVE = Path("/workspace/archive")
INDEX = ARCHIVE / "index.json"
CATEGORIES = ("defect", "fix", "milestone", "reference", "measurement")


def load_index() -> list:
    if INDEX.exists():
        try:
            return json.loads(INDEX.read_text())
        except json.JSONDecodeError:
            bad = INDEX.with_suffix(".json.corrupt")
            INDEX.rename(bad)
            print(f"  index was unreadable, moved to {bad.name}", file=sys.stderr)
    return []


def save_index(entries: list):
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2) + "\n")
    tmp.replace(INDEX)


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def cmd_add(args):
    entries = load_index()
    if any(e["id"] == args.id for e in entries) and not args.force:
        sys.exit(f"'{args.id}' is already archived (use --force to replace)")
    entries = [e for e in entries if e["id"] != args.id]

    dest = ARCHIVE / "assets" / args.id
    dest.mkdir(parents=True, exist_ok=True)
    stored = []
    for f in args.files or []:
        src = Path(f)
        if not src.exists():
            print(f"  missing, skipped: {src}")
            continue
        out = dest / src.name
        shutil.copy2(src, out)
        stored.append(out.name)
        print(f"  + {src.name}  ({out.stat().st_size // 1024} KB)")
    if not stored and not args.allow_empty:
        shutil.rmtree(dest, ignore_errors=True)
        sys.exit("  no files were stored — nothing archived "
                 "(pass --allow-empty for a note-only entry)")

    entries.append({
        "id": args.id,
        "date": args.date or _stamp(),
        "title": args.title,
        "category": args.category,
        "note": args.note or "",
        "prompt": args.prompt or "",
        "metric": args.metric or "",
        "related": args.related or [],
        "files": stored,
    })
    entries.sort(key=lambda e: (e["date"], e["id"]))
    save_index(entries)
    write_markdown(entries)
    print(f"  archived '{args.id}' ({len(stored)} file(s))")


def cmd_shot(args):
    """Snapshot a rendered shot together with the exact prompt behind it."""
    import showrunner as sr
    sr.set_current_series(args.series)
    bible = sr.load_json(sr.series_path(args.series) / "bible.json")
    ep = sr.load_json(sr.episode_path(args.series, args.episode))
    scene = next((s for s in ep["scenes"] if s["id"] == args.scene), None)
    if not scene:
        sys.exit(f"no scene {args.scene} in episode {args.episode}")

    clip = sr.find_latest_clip(args.scene)
    if not clip:
        sys.exit(f"no rendered clip for {args.scene}")

    tmp = Path("/tmp") / f"{args.scene}_frame.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.2", "-i", clip,
                    "-frames:v", "1", str(tmp)], check=False)

    prompt = sr.build_scene_prompt(scene, bible)
    neg = sr.build_negative_prompt(scene)
    mode = sr.classify_scene_type(scene)
    seed = sr.get_scene_seed_image(scene, args.series, None)

    full = (f"MODE: {mode}\nSEED: {Path(seed).name if seed else 'none'}\n"
            f"SETUP: {scene.get('setup')}  STAGING: {scene.get('staging')}\n\n"
            f"POSITIVE:\n{prompt}\n\nNEGATIVE:\n{neg}\n")

    ns = argparse.Namespace(
        id=args.id or f"{args.series}-{args.scene}",
        title=args.title or f"{args.scene} ({mode})",
        category=args.category, note=args.note or "",
        prompt=full, metric=args.metric or "", related=[],
        files=[str(tmp), clip] if tmp.exists() else [clip],
        date=None, force=args.force, allow_empty=False,
    )
    cmd_add(ns)


def write_markdown(entries: list):
    lines = [
        "# Production archive",
        "",
        "Evidence from building the Tír na nÓg pipeline. Every entry is a thing",
        "that was actually rendered, together with why it mattered and, where it",
        "exists, the prompt that produced it.",
        "",
        f"{len(entries)} entries.",
        "",
    ]
    by_cat = {}
    for e in entries:
        by_cat.setdefault(e["category"], []).append(e)

    for cat in CATEGORIES:
        rows = by_cat.get(cat)
        if not rows:
            continue
        lines += [f"## {cat} ({len(rows)})", ""]
        for e in rows:
            lines.append(f"### {e['title']}")
            lines.append(f"`{e['id']}` · {e['date']}")
            lines.append("")
            if e.get("note"):
                lines += [e["note"], ""]
            if e.get("metric"):
                lines += [f"**Measured:** {e['metric']}", ""]
            if e.get("files"):
                lines.append("Files: " + ", ".join(
                    f"`assets/{e['id']}/{f}`" for f in e["files"]))
                lines.append("")
            if e.get("prompt"):
                lines += ["<details><summary>prompt</summary>", "",
                          "```", e["prompt"].rstrip(), "```", "", "</details>", ""]
            if e.get("related"):
                lines += ["Related: " + ", ".join(f"`{r}`" for r in e["related"]), ""]
    (ARCHIVE / "INDEX.md").write_text("\n".join(lines) + "\n")


def cmd_list(args):
    entries = load_index()
    if args.category:
        entries = [e for e in entries if e["category"] == args.category]
    if not entries:
        print("  archive is empty")
        return
    print(f"  {'id':34} {'cat':12} {'date':17} title")
    print("  " + "-" * 88)
    for e in entries:
        print(f"  {e['id']:34} {e['category']:12} {e['date']:17} {e['title'][:34]}")
    total = sum(1 for e in entries for _ in e["files"])
    print(f"\n  {len(entries)} entries, {total} file(s), {ARCHIVE}")


def cmd_index(args):
    entries = load_index()
    write_markdown(entries)
    print(f"  rebuilt {ARCHIVE / 'INDEX.md'} from {len(entries)} entries")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--category", choices=CATEGORIES, required=True)
    p.add_argument("--files", nargs="*")
    p.add_argument("--note", default="")
    p.add_argument("--prompt", default="")
    p.add_argument("--metric", default="")
    p.add_argument("--related", nargs="*")
    p.add_argument("--date", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-empty", action="store_true")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("shot")
    p.add_argument("series"); p.add_argument("scene")
    p.add_argument("--episode", type=int, default=4)
    p.add_argument("--id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--category", choices=CATEGORIES, default="reference")
    p.add_argument("--note", default="")
    p.add_argument("--metric", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_shot)

    p = sub.add_parser("list")
    p.add_argument("--category", choices=CATEGORIES)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("index")
    p.set_defaults(fn=cmd_index)

    a = ap.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
