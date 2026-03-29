#!/usr/bin/env bash
# =============================================================================
# RunPod Pod Manager — start, stop, status, create
# Usage: bash scripts/pod.sh <command> [args]
#
# Commands:
#   create   — Create a new training pod (one-time)
#   start    — Resume a stopped pod
#   stop     — Stop pod (keeps volume, no compute charges)
#   destroy  — Terminate pod permanently
#   status   — Show pod state
#   ssh      — SSH into the pod
#   logs     — Tail training logs via SSH
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$TRAINING_DIR/.env"

# Load config
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "Error: $ENV_FILE not found. Copy .env.example to .env and fill in your values."
    exit 1
fi

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY in $ENV_FILE}"

API="https://api.runpod.io/graphql"

# GraphQL helper
gql() {
    local query="$1"
    curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $RUNPOD_API_KEY" \
        -d "{\"query\": \"$query\"}"
}

cmd_create() {
    local gpu="${GPU_TYPE:-NVIDIA RTX A6000}"
    local volume="${NETWORK_VOLUME_ID:-}"
    local image="${DOCKER_IMAGE:-runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04}"

    echo "Creating training pod..."
    echo "  GPU:    $gpu"
    echo "  Image:  $image"
    [ -n "$volume" ] && echo "  Volume: $volume"

    local volume_field=""
    if [ -n "$volume" ]; then
        volume_field=", networkVolumeId: \\\"$volume\\\""
    fi

    local result
    result=$(gql "mutation { podFindAndDeployOnDemand(input: { \
        name: \\\"hv-training\\\", \
        imageName: \\\"$image\\\", \
        gpuTypeId: \\\"$gpu\\\", \
        gpuCount: 1, \
        cloudType: ALL, \
        containerDiskInGb: 50, \
        volumeInGb: 100, \
        volumeMountPath: \\\"/workspace\\\", \
        startSsh: true, \
        supportPublicIp: true, \
        ports: \\\"22/tcp,6006/http\\\" \
        $volume_field \
    }) { id name desiredStatus machine { podExternalIp } runtime { ports { ip isIpPublic privatePort publicPort type } } } }")

    echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"

    # Extract pod ID and save
    local pod_id
    pod_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['podFindAndDeployOnDemand']['id'])" 2>/dev/null || true)
    if [ -n "$pod_id" ]; then
        echo ""
        echo "Pod created: $pod_id"
        # Update .env with pod ID
        if grep -q "^POD_ID=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s/^POD_ID=.*/POD_ID=$pod_id/" "$ENV_FILE"
        else
            echo "POD_ID=$pod_id" >> "$ENV_FILE"
        fi
        echo "Saved POD_ID=$pod_id to .env"
        echo ""
        echo "Next: wait for pod to be ready, then run:"
        echo "  bash scripts/pod.sh ssh"
        echo "  bash setup.sh"
    fi
}

cmd_start() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE (or run 'create' first)}"
    echo "Starting pod $POD_ID..."
    gql "mutation { podResume(input: { podId: \\\"$POD_ID\\\", gpuCount: 1 }) { id desiredStatus } }" | python3 -m json.tool
}

cmd_stop() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE}"
    echo "Stopping pod $POD_ID (volume preserved, no compute charges)..."
    gql "mutation { podStop(input: { podId: \\\"$POD_ID\\\" }) { id desiredStatus } }" | python3 -m json.tool
}

cmd_destroy() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE}"
    read -rp "Permanently destroy pod $POD_ID? (y/N) " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Terminating pod $POD_ID..."
        gql "mutation { podTerminate(input: { podId: \\\"$POD_ID\\\" }) }" | python3 -m json.tool
    fi
}

cmd_status() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE}"
    gql "query { pod(input: { podId: \\\"$POD_ID\\\" }) { \
        id name desiredStatus \
        runtime { uptimeInSeconds gpus { id gpuUtilPerc memoryUtilPerc } \
                  ports { ip isIpPublic privatePort publicPort type } } \
        machine { podExternalIp gpuDisplayName } \
    } }" | python3 -m json.tool
}

cmd_ssh() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE}"
    echo "Fetching pod connection info..."
    local info
    info=$(gql "query { pod(input: { podId: \\\"$POD_ID\\\" }) { \
        runtime { ports { ip isIpPublic privatePort publicPort type } } \
        machine { podExternalIp } \
    } }")

    local ip port
    ip=$(echo "$info" | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']['pod']
# Try public IP first
ext = data.get('machine', {}).get('podExternalIp')
if ext:
    print(ext)
else:
    ports = data.get('runtime', {}).get('ports', [])
    for p in ports:
        if p.get('privatePort') == 22 and p.get('isIpPublic'):
            print(p['ip'])
            break
" 2>/dev/null)

    port=$(echo "$info" | python3 -c "
import sys, json
ports = json.load(sys.stdin)['data']['pod'].get('runtime', {}).get('ports', [])
for p in ports:
    if p.get('privatePort') == 22:
        print(p.get('publicPort', 22))
        break
" 2>/dev/null)

    if [ -n "$ip" ] && [ -n "$port" ]; then
        echo "Connecting: ssh root@$ip -p $port"
        ssh -o StrictHostKeyChecking=no "root@$ip" -p "$port"
    else
        echo "Could not determine SSH connection. Pod may still be starting."
        echo "Raw info:"
        echo "$info" | python3 -m json.tool 2>/dev/null || echo "$info"
    fi
}

cmd_logs() {
    : "${POD_ID:?Set POD_ID in $ENV_FILE}"
    echo "Fetching training logs..."
    # Reuse ssh connection info logic
    cmd_ssh_exec "tail -f /workspace/outputs/*/training.log 2>/dev/null || echo 'No training log found.'"
}

cmd_ssh_exec() {
    local cmd="$1"
    local info
    info=$(gql "query { pod(input: { podId: \\\"$POD_ID\\\" }) { \
        runtime { ports { ip isIpPublic privatePort publicPort type } } \
        machine { podExternalIp } \
    } }")

    local ip port
    ip=$(echo "$info" | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']['pod']
ext = data.get('machine', {}).get('podExternalIp')
if ext: print(ext)
else:
    for p in data.get('runtime',{}).get('ports',[]):
        if p.get('privatePort')==22 and p.get('isIpPublic'): print(p['ip']); break
" 2>/dev/null)
    port=$(echo "$info" | python3 -c "
import sys, json
for p in json.load(sys.stdin)['data']['pod'].get('runtime',{}).get('ports',[]):
    if p.get('privatePort')==22: print(p.get('publicPort',22)); break
" 2>/dev/null)

    ssh -o StrictHostKeyChecking=no "root@$ip" -p "$port" "$cmd"
}

# --- Dispatch ---
case "${1:-help}" in
    create)  cmd_create ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    destroy) cmd_destroy ;;
    status)  cmd_status ;;
    ssh)     cmd_ssh ;;
    logs)    cmd_logs ;;
    help|*)
        echo "Usage: bash scripts/pod.sh <command>"
        echo ""
        echo "Commands:"
        echo "  create   Create a new training pod"
        echo "  start    Resume a stopped pod"
        echo "  stop     Stop pod (no compute charges)"
        echo "  destroy  Permanently terminate pod"
        echo "  status   Show pod state and GPU utilization"
        echo "  ssh      SSH into the pod"
        echo "  logs     Tail training logs"
        ;;
esac
