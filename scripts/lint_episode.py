#!/usr/bin/env python3
"""
Check an episode against what the models will actually deliver.

Every rule here was learned by rendering something that came back wrong. The
pipeline cannot make an arbitrary shot; it makes a narrow set of shots very
well. Writing to that set is the difference between an episode that looks
authored and one that looks like it fought its tools.

    lint_episode.py <series>                  every episode
    lint_episode.py <series> --episode 12
    lint_episode.py <series> --strict         exit non-zero on any error

THE EVIDENCE BEHIND EACH RULE

  R1  Dialogue cannot be wide.
      Six of eight shots authored as wides with a line in them rendered as
      head-and-shoulders close-ups, all correctly seeded from full-body
      plates. S2V is a talking-head model and pulls to the face.

  R2  Dialogue cannot move.
      Verbs measured inside a dialogue shot: step 3.85, turn 3.78, gesture
      3.47, sit 3.40, still 2.87. The best a talking shot manages is 3.85.
      A silent I2V shot of the same character walking measures 12.13.
      Asking a dialogue shot to move buys 34% of what a silent one gives.

  R3  One speaker per shot.
      S2V drives ONE face from one audio track. A second speaking character
      in the same scene has no mechanism to be driven and distorts.

  R4  Movement wants a full-body plate.
      Same walk, two seeds: full_body framing 12.13 motion / 42.3 travel,
      walking_away framing 5.17 / 30.1. The plate chooses the movement.

  R5  A line must fit three chunks.
      S2V chains to 3 x 81 frames = 15.19s. Longer is silently truncated.

  R6  Two characters in one frame is a SPLIT PANEL, not a two-shot.
      From a composite seed both faces render recognisably (0.888 / 0.790)
      but the result is a hard vertical seam with the two at different
      scales. Usable as a deliberate diptych; not as naturalistic staging.
      Without a composite seed both collapse (0.62 / 0.68).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import showrunner as sr                                        # noqa: E402

WIDE = re.compile(r"\b(wide|very wide|long shot|distant|far off|small (?:and )?"
                  r"(?:alone|among|against)|full body|full-body|figure in the)\b", re.I)
MOVE = re.compile(r"\b(walk|walks|walking|run|runs|running|ride|rides|riding|"
                  r"cross(?:es|ing)?|approach(?:es|ing)?|climb(?:s|ing)?|"
                  r"stride|strides|striding|march(?:es|ing)?|enter(?:s|ing)?|"
                  r"exit(?:s|ing)?|leave(?:s|ing)?|step(?:s)? (?:for|to|away))\b", re.I)
FULLBODY_PLATE = re.compile(r"(full_body|walking_away|three_quarter|wide_figure)", re.I)

ERR, WARN = "ERROR", "warn "


def lint_scene(scene: dict, series: str) -> list[tuple[str, str, str]]:
    """Return [(level, rule, message)] for one scene."""
    out = []
    sid = scene.get("id", "?")
    visual = scene.get("visual") or ""
    dialogue = scene.get("dialogue") or []
    chars = scene.get("characters") or []
    speakers = {d.get("character") for d in dialogue if d.get("character")}

    if dialogue:
        if WIDE.search(visual):
            out.append((ERR, "R1", "dialogue shot authored as a WIDE — it will "
                                   "render as a close-up. Move the line to a "
                                   "medium/close shot, or make this shot silent "
                                   "and lay the voice over it."))
        m = MOVE.search(visual)
        if m:
            out.append((ERR, "R2", f"dialogue shot asks for movement "
                                   f"('{m.group(0)}') — a talking shot tops out "
                                   f"at 3.85 motion against 12.13 for a silent "
                                   f"one. Split it: he moves, then he speaks."))
        if len(speakers) > 1:
            out.append((ERR, "R3", f"{len(speakers)} speakers in one shot "
                                   f"({', '.join(sorted(speakers))}) — S2V drives "
                                   f"one face from one track. Split into "
                                   f"shot/reverse-shot."))
        if len(chars) > 1:
            out.append((WARN, "R3", f"{len(chars)} characters in frame with "
                                    f"dialogue; the non-speaking one is "
                                    f"undriven and may distort. Prefer one "
                                    f"character per dialogue shot."))
        for d in dialogue:
            words = len((d.get("line") or "").split())
            # ~2.6 words/second measured for these voices
            if words / 2.6 > sr.MAX_S2V_CHUNKS * sr.S2V_CHUNK_FRAMES / 16:
                out.append((ERR, "R5", f"line is ~{words} words (~{words/2.6:.1f}s), "
                                       f"over the {sr.MAX_S2V_CHUNKS * sr.S2V_CHUNK_FRAMES/16:.1f}s "
                                       f"ceiling — it will be truncated. Split it."))
    else:
        if MOVE.search(visual):
            seed = sr.get_scene_seed_image(scene, series, None)
            if seed and not FULLBODY_PLATE.search(str(seed)):
                out.append((WARN, "R4", f"movement shot seeded from "
                                        f"'{Path(str(seed)).name}' — a full-body "
                                        f"plate gives 12.13 motion against 5.17 "
                                        f"for a tighter one."))
    if len(chars) > 1 and not dialogue:
        seed = sr.get_scene_seed_image(scene, series, None)
        if seed and "composite" not in str(seed).lower():
            out.append((WARN, "R6", "two characters in frame without a composite "
                                    "seed — both identities collapse (0.62/0.68). "
                                    "Use a composite plate, and expect a split "
                                    "panel rather than a staged two-shot."))
    return [(lvl, rule, f"{sid}: {msg}") for lvl, rule, msg in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    sr.set_current_series(a.series)
    eps = ([a.episode] if a.episode else
           sorted(int(p.stem.replace("ep", ""))
                  for p in (sr.series_path(a.series) / "episodes").glob("ep*.json")))

    errs = warns = 0
    for n in eps:
        p = sr.episode_path(a.series, n)
        if not p.exists():
            continue
        ep = sr.load_json(p)
        found = []
        for scene in ep["scenes"]:
            found += lint_scene(scene, a.series)
        e = sum(1 for l, _, _ in found if l == ERR)
        w = len(found) - e
        errs += e; warns += w
        mark = "clean" if not found else f"{e} error(s), {w} warning(s)"
        print(f"\n  ep{n:02d}  {len(ep['scenes']):2} shots — {mark}")
        for lvl, rule, msg in found:
            print(f"    [{lvl}] {rule}  {msg}")

    print(f"\n  ═══ {errs} error(s), {warns} warning(s) across {len(eps)} episode(s) ═══")
    if errs:
        print("  Errors are shots the models will not deliver as written.")
    return 1 if (a.strict and errs) else 0


if __name__ == "__main__":
    sys.exit(main())
