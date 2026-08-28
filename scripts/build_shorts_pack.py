#!/usr/bin/env python3
"""
Assemble the complete shorts pack -- the whole project, one folder, scp-able.

Three things happen here.

1. Every short becomes a PLAYABLE video. 26 of the 35 are evidence cards
   (a still frame carrying the number and the note) because the finding they
   record was a still: a green face, a contaminated plate, a caption that lied.
   A still is fine as evidence and useless as a short, so each is rendered to a
   six-second vertical clip with a slow push. The pack then contains a video for
   every entry rather than a mix the editor has to sort out.

2. The SOURCE MATERIAL comes along. The numbered folders 01-18 hold the raw
   renders each finding came from, /workspace/archive holds the earlier phase
   with its before/after pairs and the exact prompts, and youtube_package holds
   the three long-form cuts. A short is a claim; these are the receipts.

3. Both READMEs are regenerated from manifest.json, so the running order in the
   pack is the running order in the trace and neither can drift from the other.

Hardlinks are used where the filesystem allows, so 600 MB of material costs
almost nothing until it is tarred.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

SERIES = Path("/workspace/video_assets/SHORTS_SERIES")
ASSETS = Path("/workspace/video_assets")
ARCHIVE = Path("/workspace/archive")
YT = Path("/workspace/youtube_package")
PACK = Path("/workspace/shorts_pack")
CARD_SECONDS, FPS = 6, 25
BLURB = {
    "WORKED": "it worked, and the number says by how much",
    "SURPRISE": "the result contradicted what I expected",
    "BROKEN": "it was broken and reported success",
    "FAILED": "it did not work, and that is the finding",
}


def card_to_clip(png: Path, out: Path) -> bool:
    """Six seconds of slow push on a still. Pre-scaling keeps zoompan smooth."""
    if out.exists() and out.stat().st_size > 10000:
        return True
    n = CARD_SECONDS * FPS
    vf = (f"scale=2160:3840,zoompan=z='1+0.055*on/{n - 1}':d={n}"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={FPS},"
          f"fade=t=in:st=0:d=0.4,fade=t=out:st={CARD_SECONDS - 0.5}:d=0.5")
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(png),
         "-t", str(CARD_SECONDS), "-vf", vf, "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    if r.returncode:
        print(f"    ffmpeg: {r.stderr.strip()[:120]}")
    return out.exists()


def copy_tree(src: Path, dst: Path):
    """Hardlink if the filesystem allows it, else copy."""
    if dst.exists():
        shutil.rmtree(dst)
    try:
        shutil.copytree(src, dst, copy_function=lambda a, b: Path(b).hardlink_to(a))
    except Exception:                                          # noqa: BLE001
        shutil.copytree(src, dst)


def series_readme(man):
    L = [f"# The shorts series — {len(man)} episodes", "",
         "One finding each, in the order they were found. Every entry has a",
         "playable vertical clip, a script with timed beats, and the render or",
         "frame that proves it. `manifest.json` is the running trace: it holds",
         "the sequence, so shorts can be added without renumbering by hand.", "",
         "| # | verdict | short | number on screen |",
         "|---|---------|-------|------------------|"]
    for m in man:
        L.append(f"| {m['id']} | {m['verdict']} | {m['title']} | `{m['number']}` |")
    L += ["", "## What the verdicts mean", ""]
    for k, v in BLURB.items():
        n = sum(1 for m in man if m["verdict"] == k)
        L.append(f"- **{k}** ({n}) — {v}")
    L += ["", "## Suggested running order", "",
          "Numeric order is chronological and it is not the best watch order.",
          "S24–S35 are the earliest material (they were recovered from the",
          "production archive after the later shorts were cut), so opening at",
          "S24 gives the project in the order it actually happened.", "",
          "- **Chronological** — S24 → S35, then S01 → S23.",
          "- **Best hooks first** — S24 (a green man), S30 (a LoRA that did",
          "  nothing), S13 (a feature used three times that never ran),",
          "  S15 (a seven-minute film that played in 86 seconds).",
          "- **One theme** — everything BROKEN, in number order, is a single",
          "  argument: this pipeline warns and continues, so a wrong",
          "  configuration and a right one both print JOB COMPLETE.", ""]
    return "\n".join(L)


def pack_readme(man, folders, films):
    n_clip = sum(1 for m in man if m["kind"] == "clip")
    L = [f"# Tír na nÓg — the complete shorts pack", "",
         f"Everything the project has produced, arranged so it can be cut into",
         f"short-form video one piece at a time. {len(man)} shorts, each with a",
         f"playable vertical clip; {n_clip} are real renders and the rest are",
         "evidence cards rendered to video.", "",
         "## Where to start", "",
         "`SHORTS_SERIES/README.md` — the running order and what each one says.",
         "Then `SHORTS_SERIES/S24_the_green_ogre/` for the earliest finding, or",
         "`films/` if you want to see the output before the post-mortems.", "",
         "## Layout", "",
         "```",
         "SHORTS_SERIES/     the series. One folder per short:",
         "                     clip.mp4    1080x1920, ready to upload",
         "                     script.md   hook / beat / turn / punch",
         "                     *.png|mp4   the evidence it is built on",
         "                   manifest.json is the running trace",
         "films/             30s excerpts of the finished cuts",
         "source_material/   the raw renders each finding came from",
         "youtube_package/   three long-form cuts, already scripted",
         "series/            bible, episode JSON, reference images",
         "VIDEO_NOTES.md     the full written record, Parts One to Three",
         "```", "",
         "## Source material", ""]
    for f in folders:
        L.append(f"- `source_material/{f}`")
    L += ["", "## Films", ""]
    for f in films:
        L.append(f"- `films/{f.name}`")
    L += ["", "## Using it", "",
          "The clips are 1080x1920 and safe to upload as they are. If you would",
          "rather show the real render at its native 832x480, every short's",
          "folder keeps the original file beside the vertical version — put it",
          "in the middle of the frame with the hook above and the number below.",
          "That reads better than upscaling a 480p render to fill a phone.", ""]
    return "\n".join(L)


def main():
    man = json.loads((SERIES / "manifest.json").read_text())

    print(f"  rendering {sum(1 for m in man if m['kind'] != 'clip')} cards to video")
    made = 0
    for m in man:
        d = SERIES / m["slug"]
        clip = d / "clip.mp4"
        if m["kind"] == "clip":
            src = d / m["asset"]
            if src.exists() and not clip.exists():
                shutil.copy(src, clip)
        else:
            png = d / m["asset"]
            if png.exists() and card_to_clip(png, clip):
                made += 1
    print(f"    {made} rendered")

    (SERIES / "README.md").write_text(series_readme(man))

    if PACK.exists():
        shutil.rmtree(PACK)
    PACK.mkdir(parents=True)
    copy_tree(SERIES, PACK / "SHORTS_SERIES")

    src_dir = PACK / "source_material"
    src_dir.mkdir()
    folders = []
    for d in sorted(ASSETS.iterdir()):
        if not (d.is_dir() and d.name[0].isdigit()):
            continue
        if d.name == "05_the_films":
            # The full cuts live here (film_v3 alone is 232 MB) and films/
            # already carries an excerpt of each. Take the notes, not the reel.
            t = src_dir / d.name
            t.mkdir(parents=True)
            for f in list(d.glob("*.md")) + list(d.glob("extend_15s_proof.mp4")):
                shutil.copy(f, t / f.name)
            (t / "FULL_FILMS.txt").write_text(
                "The full cuts are on the pod; see ../../films/FULL_FILMS.txt\n")
        else:
            copy_tree(d, src_dir / d.name)
        folders.append(d.name)
    if ARCHIVE.exists():
        copy_tree(ARCHIVE, src_dir / "archive")
        folders.append("archive  (the earlier phase: 22 entries, before/after "
                       "pairs and the exact prompts)")
    if YT.exists():
        copy_tree(YT, PACK / "youtube_package")

    # Films: 30s excerpts, not the originals. complete_v3.mp4 alone is 433 MB
    # and the four full cuts come to 1.1 GB -- a pack whose subject is the
    # shorts should not be dominated by material already delivered, and a
    # 1.4 GB tarball is a worse artifact than a 284 MB one. The originals stay
    # on the pod and FULL_FILMS.txt says where.
    films = PACK / "films"
    films.mkdir()
    seen = []
    for f in sorted((ASSETS / "05_the_films" / "excerpts").glob("*.mp4")):
        shutil.copy(f, films / f.name)
        seen.append(f)
    proof = ASSETS / "05_the_films" / "extend_15s_proof.mp4"
    if proof.exists():
        shutil.copy(proof, films / proof.name)
        seen.append(proof)
    (films / "FULL_FILMS.txt").write_text(
        "These are 30 second excerpts, taken 30s in.\n\n"
        "The full cuts are on the pod and run 200-430 MB each:\n"
        "  /workspace/review/post/complete_v3.mp4   7:12, 55 shots\n"
        "  /workspace/review/post/film_v4.mp4\n"
        "  /workspace/review/post/prelude_v2.mp4\n"
        "  /workspace/video_assets/05_the_films/film_v3.mp4\n")
    print(f"    films: {len(seen)} excerpts")

    for name in ("VIDEO_NOTES.md",):
        p = ASSETS / name
        if p.exists():
            shutil.copy(p, PACK / name)
    # The bible, the episode JSON and the character anchors -- what a viewer
    # needs to read a short. sets/ is 144 MB of location plates and belongs
    # with the renders, not here.
    sp = Path("/workspace/text-to-video/series/tir-na-nog-legend")
    if sp.exists():
        (PACK / "series").mkdir()
        for sub in ("episodes", "reference_images", "continuity"):
            if (sp / sub).is_dir():
                copy_tree(sp / sub, PACK / "series" / sub)
        if (sp / "bible.json").exists():
            shutil.copy(sp / "bible.json", PACK / "series" / "bible.json")

    (PACK / "README.md").write_text(pack_readme(man, folders, seen))

    nf = sum(1 for _ in PACK.rglob("*") if _.is_file())
    nv = sum(1 for _ in PACK.rglob("*.mp4"))
    mb = subprocess.run(["du", "-sm", str(PACK)], capture_output=True,
                        text=True).stdout.split()[0]
    print(f"\n  {PACK}: {nf} files, {nv} videos, {mb} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
