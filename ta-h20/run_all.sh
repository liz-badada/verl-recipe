#!/bin/bash
# run_all.sh [tag]: smoke tests, then the three arms back to back on the free 8xH20 node.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d-%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
IMG=${IMAGE:-verl-recipe-thunderagent:rust-ta-uniagent-20261012}
log() { echo "[$(date +%T)] $*"; }
busy() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}'; }
docker ps -q --filter name=uni-agent- --filter name=smoke- --filter name=tabench- | xargs -r docker rm -f >/dev/null 2>&1  # stale containers from an aborted run
[ "$(busy)" -eq 0 ] || { log "GPUs busy ($(busy) in use); abort"; exit 3; }
if [ "${SKIP_SMOKE:-0}" != 1 ]; then
 if [ "${SKIP_DYNAMO_SMOKE:-0}" != 1 ]; then
  log "smoke: dynamo frontend + native TA + vLLM 0.24 worker on GPU 7"
  [ -f $H/models/Qwen2.5-0.5B-Instruct/config.json ] || { mkdir -p $H/models; docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $H/models:/models $IMG \
    python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-0.5B-Instruct', local_dir='/models/Qwen2.5-0.5B-Instruct')" > /dev/null 2>&1; }
  rm -rf $H/runs/smoke-dynamo; mkdir -p $H/runs/smoke-dynamo
  timeout 900 docker run --rm --name smoke-dynamo --gpus '"device=7"' --network host --shm-size 8g --user $(id -u):$(id -g) -e HOME=/tmp -e USER=$(id -un) -e LOGNAME=$(id -un) \
    -v $H:/h20:ro -v $H/models:/models:ro -v $H/overlay/handlers.py:/usr/local/lib/python3.12/dist-packages/dynamo/vllm/handlers.py:ro -v $H/runs/smoke-dynamo:/tmp/smoke -e LOGDIR=/tmp/smoke -e VLLM_USE_FLASHINFER_SAMPLER=0 \
    $IMG bash /h20/smoke_dynamo.sh > $H/runs/smoke-dynamo/console.log 2>&1
  grep -q '"choices"' $H/runs/smoke-dynamo/console.log || { log "dynamo smoke FAILED"; tail -20 $H/runs/smoke-dynamo/console.log; exit 4; }
  log "dynamo smoke ok: $(grep -c '"choices"' $H/runs/smoke-dynamo/console.log) completions; TA lines: $(grep -ci thunderagent $H/runs/smoke-dynamo/frontend.log)"
 fi
  log "smoke: tiny ta-native full stack (2 prompts x 2)"
  BATCH=2 N=2 CONCURRENCY=4 bash $H/run_arm.sh ta-native smoke-ta-$TAG > /dev/null 2>&1
  grep -q '"sessions_done": [1-9]' $H/runs/smoke-ta-$TAG/summary.txt || { log "full-stack smoke FAILED"; grep -i -E 'error|Traceback' $H/runs/smoke-ta-$TAG/console.log | tail -15; exit 5; }
  log "full-stack smoke ok: $(grep -E 'sessions_done|wall_s|subagent_trajectories' $H/runs/smoke-ta-$TAG/summary.txt | tr -d ' \n')"
fi
for arm in ${ARMS:-ta-native global kv}; do
  log "arm $arm start"
  bash $H/run_arm.sh $arm $arm-$TAG > /dev/null 2>&1
  log "arm $arm done: $(grep -E 'sessions_done|wall_s|model_tokens_per_s|subagent_trajectories' $H/runs/$arm-$TAG/summary.txt | tr -d ' \n')"
  # Let the previous stack's sockets and sandboxes drain before the next arm binds its ports.
  docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; sleep 90
  for i in $(seq 1 20); do [ "$(busy)" -eq 0 ] && break; sleep 15; done
done
log "ALL DONE"
