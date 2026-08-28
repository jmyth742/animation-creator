#!/usr/bin/env python3
"""
Shorts for the earlier phase of the project, from the production archive.

The numbered series covered the last few days. The archive holds 22 entries
from before that -- the green ogre, a LoRA trained on the wrong style, two
visual styles in one episode -- each already carrying its before/after images,
its measurement and, where one exists, the exact prompt that caused it.

That material is better than anything written from memory, because it was
recorded at the moment the thing was found rather than reconstructed
afterwards. This turns each into a short and continues the numbering.
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import build_story_cards as bsc                                # noqa: E402

ARCHIVE = Path("/workspace/archive")
OUT = Path("/workspace/video_assets/SHORTS_SERIES")
W, H = 1080, 1920
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
MONO, MONO_B = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
BG, INK, DIM = (13, 14, 17), (233, 230, 221), (132, 129, 123)
COL = {"WORKED": (120, 190, 130), "FAILED": (222, 176, 92),
       "BROKEN": (214, 96, 88), "SURPRISE": (140, 165, 220)}

# id -> (verdict, title, number, note, beats)
PICK = {
 "green-ogre": ("BROKEN", "The green ogre",
   "3 of 3",
   "Moving the style to the front of the prompt cured one bug and caused this "
   "one: it put 'restrained palette of greens' immediately before the "
   "character's name, so 'greens' landed on HIM instead of the art direction.",
   "HOOK: show the frame. He is green.\nBEAT: this was caused by my own fix "
   "for a different problem.\nTURN: '...palette of greens. Oisin.' The colour "
   "word landed on the next noun.\nPUNCH: word ORDER in a prompt is not "
   "cosmetic. Colour moved to the back and he went back to being a man."),
 "stale-lora-photoreal": ("BROKEN", "A LoRA trained on the wrong style",
   "inconsistent",
   "Trained on photoreal portraits, applied at full strength to a cel-shaded "
   "render. Not uniformly bad -- INCONSISTENT, which is worse. One character "
   "came back cel, the other photoreal, in the same episode.",
   "HOOK: two shots from one episode. One is a cartoon, one is a photograph.\n"
   "BEAT: same series, same day, same settings.\nTURN: the LoRAs were trained "
   "on the old photoreal portraits. Image-to-video leans on its seed and "
   "survived; speech-to-video does not and lost.\nPUNCH: my own style test had "
   "missed it, because it built its workflows WITHOUT the LoRAs. I validated a "
   "configuration next to the one I was shipping."),
 "style-split-2styles-one-episode": ("BROKEN", "Three shots, three different looks",
   "0 seeds",
   "One came back smooth 3D-CGI. One came back 1980s anime with plate armour "
   "instead of the leather jerkin in the bible. One was correct. The anime one "
   "had no seed image at all.",
   "HOOK: three shots from one episode, side by side.\nBEAT: they look like "
   "three different shows.\nTURN: the odd one had NO seed image -- with "
   "nothing anchoring it, the model free-associated from the words.\nPUNCH: "
   "'cel-shaded 2D animation' came back as 1980s anime, in plate armour."),
 "photoreal-training-data": ("BROKEN", "Training data for the wrong show",
   "41 vs 28",
   "The latent cache held 41 photoreal entries while the dataset directory "
   "held 28 cel ones. It caches by DIRECTORY, not by content, so a rebuilt "
   "dataset trained on the old images without a word of warning.",
   "HOOK: 'I rebuilt the training set and retrained.'\nBEAT: the result was "
   "identical.\nTURN: the latent cache keys on the directory, not the "
   "contents. 41 old entries, 28 new images.\nPUNCH: it trained on data I had "
   "deleted."),
 "dataset-captions-lie": ("BROKEN", "Captions describing eight shots of one photo",
   "8 -> 1",
   "The captions claimed eight different framings. Every one described the "
   "same head-and-shoulders picture. The model was told a close-up and a wide "
   "shot look identical.",
   "HOOK: read two captions. They describe different shots.\nBEAT: show the "
   "images. They are the same photo.\nTURN: eight captions, one framing.\n"
   "PUNCH: I taught it that framing means nothing."),
 "lipsync-drift": ("BROKEN", "The subtitles drifted four seconds late",
   "+4.5s",
   "Timing cues against the sum of clip lengths ignores that every crossfade "
   "removes time. Over sixteen shots the error compounds to about four and a "
   "half seconds.",
   "HOOK: play the end of the film. The subtitle arrives after the line.\n"
   "BEAT: at the start it was perfect.\nTURN: each crossfade removes 0.3s from "
   "the timeline. Sixteen shots later that is 4.5 seconds.\nPUNCH: the "
   "beginning of a film cannot tell you the end is right."),
 "lora-probe-failed": ("SURPRISE", "The LoRA that trained, installed, and did nothing",
   "+0.006",
   "It trained without error, resolved correctly, and was wired into the right "
   "node. It moved identity by six thousandths. The trigger word had never "
   "reached the prompt.",
   "HOOK: 'I trained a character LoRA. It worked perfectly.'\nBEAT: +0.006.\n"
   "TURN: the trigger word was never in the prompt, so the LoRA had nothing to "
   "attach to.\nPUNCH: it trained, installed, loaded and did nothing, and "
   "every step reported success."),
 "seeding-fix-wide": ("WORKED", "A wide shot needs a plate, not a portrait",
   "+0.195",
   "Two wide shots scored 0.632 and 0.669. Seeded from a staged plate instead "
   "they scored 0.827 and 0.834. A portrait cannot fill a landscape, and an "
   "empty location has no face in it at all.",
   "HOOK: two versions of the same wide shot.\nBEAT: 0.632 and 0.827.\nTURN: "
   "the difference is what it was seeded from. A head-and-shoulders portrait "
   "cannot fill a landscape frame.\nPUNCH: +0.195, and it reproduced to three "
   "decimal places on a re-render."),
 "lora-cross-family": ("FAILED", "A LoRA that works on one model destroys another",
   "0.999 -> 0.001",
   "The same character LoRA that helps image-to-video collapsed the cel style "
   "on speech-to-video: identity -0.138 and the style score from 0.999 to "
   "0.001. Different model family.",
   "HOOK: 'One LoRA, two models, same character.'\nBEAT: on one it helps. On "
   "the other the style score goes from 0.999 to 0.001.\nTURN: they are "
   "different model families.\nPUNCH: footnote worth its own video -- when I "
   "re-tested this months later, it did not reproduce."),
 "plate-contamination": ("BROKEN", "Three people in a reference image",
   "0.316",
   "Every shot seeded from that plate inherited them. The contamination check "
   "scored it 0.316 against a 0.75 threshold and passed it.",
   "HOOK: 'Who are these people?'\nBEAT: they are in the reference plate.\n"
   "TURN: every shot seeded from it inherits them.\nPUNCH: the check built to "
   "catch exactly this passed it."),
 "overfitted-rule": ("SURPRISE", "I wrote down a rule from seven results",
   "7 up, 7 down",
   "I concluded close-ups should keep the portrait, from seven shots that got "
   "worse. Reading it properly: seven improved and seven regressed, splitting "
   "by neither shot type nor render mode.",
   "HOOK: 'I found a rule and wrote it in the docs.'\nBEAT: seven shots got "
   "worse with a plate.\nTURN: seven also got BETTER. I had read half a table."
   "\nPUNCH: then I called the other seven noise -- also wrong. Renders are "
   "deterministic. Every difference was real; none of it was a rule."),
 "probe-confound": ("SURPRISE", "I changed two things and credited one",
   "two variables",
   "A probe rendered each shot with a new LoRA AND new seeding, then compared "
   "against a baseline that had neither. The plate's contribution was credited "
   "to the LoRA.",
   "HOOK: 'The LoRA improved identity by 0.116.'\nBEAT: except I had also "
   "changed the seeding.\nTURN: comparing a two-change render against a "
   "two-change-old baseline tells you the SUM, not which half did the work.\n"
   "PUNCH: isolated properly, the LoRA's own effect on those shots was +0.000."),
}


def _wrap(d, t, f, mw):
    out, cur = [], ""
    for w in t.split():
        s = (cur + " " + w).strip()
        if d.textbbox((0, 0), s, font=f)[2] > mw and cur:
            out.append(cur); cur = w
        else:
            cur = s
    if cur:
        out.append(cur)
    return out


def frame(verdict, title, number, note, img_path, dst):
    plate = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(plate)
    c = COL[verdict]
    fv = ImageFont.truetype(MONO_B, 38)
    bw = d.textbbox((0, 0), verdict, font=fv)[2] + 60
    d.rounded_rectangle([60, 90, 60 + bw, 160], 10, fill=c)
    d.text((90, 104), verdict, font=fv, fill=BG)
    y = 210
    for ln in _wrap(d, title, ImageFont.truetype(SERIF_B, 52), W - 120)[:3]:
        d.text((60, y), ln, font=ImageFont.truetype(SERIF_B, 52), fill=INK)
        y += 66
    top = 560
    if img_path and Path(img_path).exists():
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            ih = int(W * im.height / im.width)
            plate.paste(im.resize((W, ih)), (0, top))
        by = top + ih + 80
    else:
        by = top + 100
    fn = ImageFont.truetype(MONO_B, 76)
    bb = d.textbbox((0, 0), number, font=fn)
    d.text(((W - (bb[2]-bb[0])) / 2, by), number, font=fn, fill=c)
    by += 130
    for ln in _wrap(d, note, ImageFont.truetype(MONO, 27), W - 120)[:8]:
        d.text((60, by), ln, font=ImageFont.truetype(MONO, 27), fill=DIM)
        by += 40
    plate.save(dst)
    return dst


def main():
    idx = json.loads((ARCHIVE / "index.json").read_text())
    items = idx if isinstance(idx, list) else idx.get("entries", [])
    by_id = {e.get("id"): e for e in items}
    man_p = OUT / "manifest.json"
    man = json.loads(man_p.read_text())
    n = max(m["n"] for m in man)
    added = []
    for aid, (verdict, title, number, note, beats) in PICK.items():
        e = by_id.get(aid)
        n += 1
        num = f"S{n:02d}"
        slug = f"{num}_" + "".join(ch if ch.isalnum() else "_"
                                  for ch in title.lower())[:44].strip("_")
        d = OUT / slug
        d.mkdir(exist_ok=True)
        files = (e or {}).get("files") or (e or {}).get("assets") or []
        src = None
        for f in files:
            p = ARCHIVE / f if not str(f).startswith("/") else Path(f)
            if p.exists() and p.suffix.lower() in (".png", ".jpg"):
                shutil.copy(p, d / p.name)
                src = src or p
        frame(verdict, title, number, note, src, d / "frame.png")
        (d / "script.md").write_text(
            f"# {num} — {title}\n\n**Verdict:** {verdict}  \n"
            f"**Number on screen:** {number}\n\n## Beats\n\n{beats}\n\n"
            f"## The note under the number\n\n{note}\n\n---\n\n"
            f"From the production archive, recorded when it was found rather "
            f"than reconstructed later.\n")
        man.append({"n": n, "id": num, "slug": slug, "verdict": verdict,
                    "title": title, "number": number, "kind": "card",
                    "asset": "frame.png", "recorded": False,
                    "source": f"archive/{aid}"})
        added.append((num, verdict, title))
        print(f"  {num}  {verdict:8} {title[:50]}")
    man_p.write_text(json.dumps(man, indent=2))
    print(f"\n  {len(added)} added; series is now {len(man)} shorts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
