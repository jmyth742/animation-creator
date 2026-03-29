#!/usr/bin/env bash
# =============================================================================
# Sync — push datasets to pod, pull LoRA results back
# Usage: bash scripts/sync.sh <command> [args]
#
# Commands:
#   push-dataset <dir>  — Upload a local dataset directory to the pod
#   push-config         — Upload training configs to the pod
#   push-all            — Upload the entire training/ directory to the pod
#   pull-lora [name]    — Download trained LoRA to local ComfyUI/models/loras/
#   pull-logs           — Download training logs
#   list-outputs        — List available LoRA outputs on pod
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$TRAINING_DIR")"
ENV_FILE="$TRAINING_DIR/.env"
LORA_DIR="$PROJECT_DIR/ComfyUI/models/loras"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "Error: $ENV_FILE not found."
    exit 1
fi

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY in $ENV_FILE}"
: "${POD_ID:?Set POD_ID in $ENV_FILE}"

API="https://api.runpod.io/graphql"

# Get SSH connection details
get_ssh_info() {
    local info
    info=$(curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $RUNPOD_API_KEY" \
        -d "{\"query\": \"query { pod(input: { podId: \\\"$POD_ID\\\" }) { runtime { ports { ip isIpPublic privatePort publicPort type } } machine { podExternalIp } } }\"}")

    SSH_IP=$(echo "$info" | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']['pod']
ext = data.get('machine', {}).get('podExternalIp')
if ext: print(ext)
else:
    for p in data.get('runtime',{}).get('ports',[]):
        if p.get('privatePort')==22 and p.get('isIpPublic'): print(p['ip']); break
" 2>/dev/null)

    SSH_PORT=$(echo "$info" | python3 -c "
import sys, json
for p in json.load(sys.stdin)['data']['pod'].get('runtime',{}).get('ports',[]):
    if p.get('privatePort')==22: print(p.get('publicPort',22)); break
" 2>/dev/null)

    if [ -z "$SSH_IP" ] || [ -z "$SSH_PORT" ]; then
        echo "Error: Could not get SSH connection info. Is the pod running?"
        exit 1
    fi
}

scp_to_pod() {
    local src="$1" dst="$2"
    scp -o StrictHostKeyChecking=no -P "$SSH_PORT" -r "$src" "root@$SSH_IP:$dst"
}

scp_from_pod() {
    local src="$1" dst="$2"
    scp -o StrictHostKeyChecking=no -P "$SSH_PORT" -r "root@$SSH_IP:$src" "$dst"
}

ssh_cmd() {
    ssh -o StrictHostKeyChecking=no "root@$SSH_IP" -p "$SSH_PORT" "$@"
}

cmd_push_dataset() {
    local dir="${1:?Usage: sync.sh push-dataset <local-dataset-dir>}"
    if [ ! -d "$dir" ]; then
        echo "Error: Directory not found: $dir"
        exit 1
    fi
    get_ssh_info
    local name
    name=$(basename "$dir")
    echo "Uploading dataset '$name' to pod..."
    ssh_cmd "mkdir -p /workspace/datasets/$name"
    scp_to_pod "$dir/"* "/workspace/datasets/$name/"
    echo "Done. Dataset available at /workspace/datasets/$name on pod."
}

cmd_push_config() {
    get_ssh_info
    echo "Uploading training configs..."
    ssh_cmd "mkdir -p /workspace/training/configs"
    scp_to_pod "$TRAINING_DIR/configs/"* "/workspace/training/configs/"
    echo "Done."
}

cmd_push_all() {
    get_ssh_info
    echo "Uploading entire training directory..."
    ssh_cmd "mkdir -p /workspace/training"
    scp_to_pod "$TRAINING_DIR/setup.sh" "/workspace/training/"
    scp_to_pod "$TRAINING_DIR/train.sh" "/workspace/training/"
    scp_to_pod "$TRAINING_DIR/configs" "/workspace/training/"
    echo "Done. Run 'bash /workspace/training/setup.sh' on the pod to bootstrap."
}

cmd_pull_lora() {
    local name="${1:-}"
    get_ssh_info

    if [ -z "$name" ]; then
        echo "Available LoRA outputs:"
        ssh_cmd "find /workspace/outputs -name '*.safetensors' -type f 2>/dev/null" || echo "  (none found)"
        echo ""
        echo "Usage: sync.sh pull-lora <name>"
        echo "  e.g., sync.sh pull-lora style_lora"
        return
    fi

    echo "Downloading LoRA files matching '$name'..."
    mkdir -p "$LORA_DIR"

    # Find and download all safetensors from the output dir
    local files
    files=$(ssh_cmd "find /workspace/outputs/$name -name '*.safetensors' -type f 2>/dev/null" || true)

    if [ -z "$files" ]; then
        echo "No .safetensors files found in /workspace/outputs/$name"
        echo "Checking all outputs..."
        ssh_cmd "find /workspace/outputs -name '*.safetensors' -type f 2>/dev/null" || echo "  (none)"
        return
    fi

    while IFS= read -r f; do
        local basename
        basename=$(basename "$f")
        echo "  Pulling: $basename → $LORA_DIR/"
        scp_from_pod "$f" "$LORA_DIR/$basename"
    done <<< "$files"

    echo ""
    echo "LoRA files saved to: $LORA_DIR/"
    echo "Available for ComfyUI inference immediately."
    ls -la "$LORA_DIR/"*.safetensors 2>/dev/null || true
}

cmd_pull_logs() {
    get_ssh_info
    echo "Downloading training logs..."
    mkdir -p "$TRAINING_DIR/logs"
    scp_from_pod "/workspace/outputs/*/training.log" "$TRAINING_DIR/logs/" 2>/dev/null || true
    scp_from_pod "/workspace/outputs/*/logs/*" "$TRAINING_DIR/logs/" 2>/dev/null || true
    echo "Logs saved to: $TRAINING_DIR/logs/"
}

cmd_list_outputs() {
    get_ssh_info
    echo "LoRA outputs on pod:"
    ssh_cmd "find /workspace/outputs -name '*.safetensors' -type f -exec ls -lh {} \; 2>/dev/null" || echo "  (none)"
}

# --- Dispatch ---
case "${1:-help}" in
    push-dataset) cmd_push_dataset "${2:-}" ;;
    push-config)  cmd_push_config ;;
    push-all)     cmd_push_all ;;
    pull-lora)    cmd_pull_lora "${2:-}" ;;
    pull-logs)    cmd_pull_logs ;;
    list-outputs) cmd_list_outputs ;;
    help|*)
        echo "Usage: bash scripts/sync.sh <command> [args]"
        echo ""
        echo "Commands:"
        echo "  push-dataset <dir>  Upload dataset directory to pod"
        echo "  push-config         Upload training configs to pod"
        echo "  push-all            Upload training dir (setup + configs)"
        echo "  pull-lora [name]    Download LoRA to ComfyUI/models/loras/"
        echo "  pull-logs           Download training logs"
        echo "  list-outputs        List LoRA outputs on pod"
        ;;
esac
