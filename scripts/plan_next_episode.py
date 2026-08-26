#!/usr/bin/env python3
"""
Read the night's experiments and report what the next episode should use.

Written deliberately as a REPORT rather than a generator. Every episode so far
was authored by hand against known capabilities; tonight changes what is known,
and the sensible thing is to summarise what changed and let the next script be
written against it -- not to auto-generate a script from numbers.

Reads whatever the experiments left behind:
    /workspace/review/two_shot/verdict.json      two characters in one frame
    /workspace/review/lora_sweep/*.json          a usable LoRA strength on S2V
    /workspace/review/variants/*.json            camera moves, alternate takes
"""
import json
import sys
from pathlib import Path


def main():
    print("\n  WHAT TONIGHT ESTABLISHED\n")

    v = Path("/workspace/review/two_shot/verdict.json")
    if v.exists():
        d = json.loads(v.read_text())
        if d.get("usable"):
            print(f"  TWO-SHOTS: usable via '{d['best']}'. The next episode "
                  f"should use them for reaction and listening coverage -- one "
                  f"speaks, the other is in frame not speaking, which is how a "
                  f"two-shot is actually used.")
        else:
            print("  TWO-SHOTS: no variant held both characters. Conversations "
                  "stay as singles; spend the effort on reaction CUTS instead, "
                  "which need no new capability.")
    else:
        print("  TWO-SHOTS: not tested")

    sw = sorted(Path("/workspace/review/lora_sweep").glob("*.json")) \
        if Path("/workspace/review/lora_sweep").exists() else []
    if sw:
        best = None
        for f in sw:
            for r in json.loads(f.read_text()):
                if r["strength"] > 0 and r["cel"] >= 0.5:
                    base = json.loads(f.read_text())[0]["identity"]
                    if r["identity"] > base + 0.005 and (
                            best is None or r["identity"] > best[1]):
                        best = (r["strength"], r["identity"])
        print(f"\n  S2V LoRA: " + (
            f"strength {best[0]} adds identity without losing the style. "
            f"Character LoRAs can come back on dialogue shots -- roughly 80% "
            f"of every film."
            if best else
            "no strength both helped identity and kept the cel style. "
            "Dialogue shots stay untrained; the honest fix is a LoRA trained "
            "against the S2V family, which musubi cannot do."))
    else:
        print("\n  S2V LoRA: not tested")

    var = Path("/workspace/review/variants")
    cams = sorted(var.glob("*.json")) if var.exists() else []
    if cams:
        print(f"\n  CAMERA / COVERAGE: {len(cams)} shot(s) rendered in "
              f"variants. Check each JSON for whether a prompted move raised "
              f"motion WITHOUT lowering identity -- if it did, real parallax "
              f"beats the post-crop and shots should be written with moves.")
    else:
        print("\n  CAMERA / COVERAGE: not tested")

    print("\n  Write the next episode against whatever held up.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
