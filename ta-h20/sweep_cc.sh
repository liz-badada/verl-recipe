#!/bin/bash
# sweep_cc.sh [tag]: concurrency sweep for the blog-style regime chart (default Claude Code prompt).
# CC 256 and 384 keep the full 32x16=512 sessions; CC 128 / 64 use 2 waves (32x8 / 32x4) so each
# arm stays inside the 3 h wall cap. Model tok/s is a rate over the scored window, same as the other sweeps.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
export KV_BYTES=${KV_BYTES:-64424509440}
log() { echo "[$(date +%T)] $*"; }
busy() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}'; }
[ "$(busy)" -eq 0 ] || { log "GPUs busy ($(busy) in use); abort"; exit 3; }
for cc in ${CCS:-256 384 128 64}; do
  case $cc in 64) n=4;; 128) n=8;; *) n=16;; esac
  cpus=$(( cc + 128 )); [ $cpus -lt 320 ] && cpus=320
  for arm in ${ARMS:-ta-native global}; do
    name=$arm-h20cc$cc-$TAG
    log "arm $arm cc=$cc n=$n start ($name)"
    BATCH=32 N=$n CONCURRENCY=$cc RAY_NUM_CPUS=$cpus bash $H/run_arm.sh $arm $name > /dev/null 2>&1
    log "arm $arm cc=$cc done: $(grep -E 'sessions_done|wall_s|model_tokens_per_s' $H/runs/$name/summary.txt 2>/dev/null | tr -d ' \n')"
    docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; sleep 90
    for i in $(seq 1 20); do [ "$(busy)" -eq 0 ] && break; sleep 15; done
  done
done
log "SWEEP DONE"
