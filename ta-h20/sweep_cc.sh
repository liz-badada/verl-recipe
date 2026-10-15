#!/bin/bash
# sweep_cc.sh [tag]: concurrency sweep for the blog-style regime chart (default Claude Code prompt).
# CC 256 and 384 keep the full 32x16=512 sessions; CC 128 / 64 use 2 waves (32x8 / 32x4) so each
# arm stays inside the 3 h wall cap. Model tok/s is a rate over the scored window, same as the other sweeps.
# Waits (indefinitely) for all 8 GPUs to be free before each arm, never touching other users' jobs;
# re-running with the same tag skips arms that already have a summary.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
export KV_BYTES=${KV_BYTES:-64424509440}
log() { echo "[$(date +%T)] $*"; }
busy() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}'; }
wait_free() { local w=0; while [ "$(busy)" -ne 0 ]; do [ $((w % 20)) -eq 0 ] && log "waiting: $(busy) GPUs in use by other jobs"; sleep 60; w=$((w+1)); done; }
for cc in ${CCS:-256 384 128 64}; do
  case $cc in 64) n=4;; 128) n=8;; *) n=16;; esac; n=${N_OVERRIDE:-$n}  # N_OVERRIDE=16 gives every CC the same 512 trajectories
  cpus=$(( cc + 128 )); [ $cpus -lt 320 ] && cpus=320
  for arm in ${ARMS:-ta-native global}; do
    name=$arm-${SITE:-h20}cc$cc-$TAG
    if grep -q '"sessions_done": [1-9]' $H/runs/$name/summary.txt 2>/dev/null; then log "skip $name (done)"; continue; fi
    # An arm whose engines never started (another job grabbed the GPUs while we were loading) is retried, not skipped.
    for attempt in 1 2 3 4 5 6; do
      [ -d $H/runs/$name ] && mv $H/runs/$name $H/runs/$name-failed-$(date +%H%M)
      wait_free; sleep 60; wait_free
      log "arm $arm cc=$cc n=$n start ($name, attempt $attempt)"
      BATCH=32 N=$n CONCURRENCY=$cc RAY_NUM_CPUS=$cpus bash $H/run_arm.sh $arm $name > /dev/null 2>&1
      log "arm $arm cc=$cc done: $(grep -E 'sessions_done|wall_s|model_tokens_per_s' $H/runs/$name/summary.txt 2>/dev/null | tr -d ' \n')"
      grep -q '"sessions_done": [1-9]' $H/runs/$name/summary.txt 2>/dev/null && break
      log "arm $arm cc=$cc produced no sessions (GPUs taken during startup?); will retry"
    done
    docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; sleep 90
  done
done
log "SWEEP DONE"
