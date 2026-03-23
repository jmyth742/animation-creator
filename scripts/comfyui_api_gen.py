#!/usr/bin/env python3
"""ComfyUI API automation for HunyuanVideo workflows."""

import argparse
import json
import sys
import uuid

import requests
import websocket

SERVER = "http://localhost:8188"
WS_SERVER = "ws://localhost:8188/ws"


def load_workflow(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def queue_workflow(workflow: dict, client_id: str | None = None) -> tuple[str, str]:
    """Queue a workflow and return (prompt_id, client_id)."""
    if client_id is None:
        client_id = str(uuid.uuid4())
    r = requests.post(
        f"{SERVER}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    r.raise_for_status()
    return r.json()["prompt_id"], client_id


def wait_for_completion(prompt_id: str, client_id: str):
    """Connect via websocket and wait for the prompt to finish."""
    ws = websocket.WebSocket()
    ws.settimeout(600)  # 10 min timeout for VAE decode
    ws.connect(f"{WS_SERVER}?clientId={client_id}")
    try:
        while True:
            try:
                msg = ws.recv()
            except websocket.WebSocketConnectionClosedException:
                print("\n  WebSocket closed. Checking if job completed...")
                import time
                time.sleep(5)
                outputs = get_outputs(prompt_id)
                if outputs:
                    print("  Job completed successfully!")
                    return outputs
                print("  Job may have failed. Check ComfyUI logs.")
                return None
            if isinstance(msg, str):
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "progress":
                    d = data["data"]
                    pct = d["value"] / d["max"] * 100
                    print(f"\r  Progress: {pct:.0f}% ({d['value']}/{d['max']})", end="", flush=True)
                elif msg_type == "executing":
                    node = data["data"].get("node")
                    if node:
                        print(f"\r  Executing node {node}...                    ", end="", flush=True)
                    elif data["data"].get("prompt_id") == prompt_id:
                        print("\n  Done!")
                        return data["data"]
                elif msg_type == "executed" and data["data"].get("prompt_id") == prompt_id:
                    print("\n  Done!")
                    return data["data"]
                elif msg_type == "execution_error":
                    print(f"\n  ERROR: {data['data']}")
                    return None
    finally:
        ws.close()


def get_outputs(prompt_id: str) -> dict:
    """Get output file info for a completed prompt."""
    r = requests.get(f"{SERVER}/history/{prompt_id}")
    r.raise_for_status()
    history = r.json()
    if prompt_id in history:
        return history[prompt_id].get("outputs", {})
    return {}


def main():
    parser = argparse.ArgumentParser(description="Queue HunyuanVideo workflows via ComfyUI API")
    parser.add_argument("workflow", help="Path to workflow JSON file")
    parser.add_argument("--prompt", "-p", help="Override the text prompt")
    parser.add_argument("--seed", "-s", type=int, help="Override the seed")
    parser.add_argument("--steps", type=int, help="Override inference steps")
    parser.add_argument("--frames", type=int, help="Override frame count (must be 4n+1)")
    parser.add_argument("--width", type=int, help="Override width")
    parser.add_argument("--height", type=int, help="Override height")
    parser.add_argument("--no-wait", action="store_true", help="Queue and exit without waiting")
    args = parser.parse_args()

    wf = load_workflow(args.workflow)

    # Detect workflow version by looking for node types
    is_v15 = any(
        n.get("class_type") == "EmptyHunyuanVideo15Latent" for n in wf.values()
    )

    # Find nodes by class_type for reliable overrides
    def find_node(class_type):
        for nid, node in wf.items():
            if node.get("class_type") == class_type:
                return nid
        return None

    prompt_node = find_node("CLIPTextEncode") or find_node("HunyuanVideoTextEncode")
    latent_node = find_node("EmptyHunyuanVideo15Latent") or find_node("EmptyHunyuanLatentVideo")
    seed_node = find_node("RandomNoise")
    scheduler_node = find_node("BasicScheduler")
    sampler_node = find_node("HunyuanVideoSampler")

    # Apply overrides
    if args.prompt and prompt_node:
        wf[prompt_node]["inputs"]["text"] = args.prompt
    if args.seed is not None:
        if seed_node:
            wf[seed_node]["inputs"]["noise_seed"] = args.seed
        elif sampler_node:
            wf[sampler_node]["inputs"]["seed"] = args.seed
    if args.steps:
        if scheduler_node:
            wf[scheduler_node]["inputs"]["steps"] = args.steps
        elif sampler_node:
            wf[sampler_node]["inputs"]["steps"] = args.steps
    if args.frames and latent_node:
        wf[latent_node]["inputs"]["length"] = args.frames
    if args.width and latent_node:
        wf[latent_node]["inputs"]["width"] = args.width
    if args.height and latent_node:
        wf[latent_node]["inputs"]["height"] = args.height

    # Display info
    prompt_text = wf[prompt_node]["inputs"]["text"][:80] if prompt_node else "N/A"
    res_w = wf[latent_node]["inputs"].get("width", "?") if latent_node else "?"
    res_h = wf[latent_node]["inputs"].get("height", "?") if latent_node else "?"
    frames = wf[latent_node]["inputs"].get("length", "?") if latent_node else "?"
    steps = (wf[scheduler_node]["inputs"].get("steps", "?") if scheduler_node
             else wf[sampler_node]["inputs"].get("steps", "?") if sampler_node else "?")

    print(f"Queuing workflow: {args.workflow} ({'v1.5' if is_v15 else 'v1.0'})")
    print(f"  Prompt: {prompt_text}...")
    print(f"  Resolution: {res_w}x{res_h}")
    print(f"  Frames: {frames}, Steps: {steps}")

    try:
        prompt_id, client_id = queue_workflow(wf)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to ComfyUI at {SERVER}. Is it running?")
        sys.exit(1)

    print(f"  Prompt ID: {prompt_id}")

    if args.no_wait:
        print("Queued. Use --no-wait=false to wait for completion.")
        return

    print("Waiting for completion...")
    result = wait_for_completion(prompt_id, client_id)

    if result:
        outputs = get_outputs(prompt_id)
        print(f"Outputs: {json.dumps(outputs, indent=2)}")


if __name__ == "__main__":
    main()
