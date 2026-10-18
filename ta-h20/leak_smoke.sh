#!/bin/bash
# leak_smoke.sh [tag]: ThunderAgent arm at small scale with a 4-minute Claude Code timeout, so most sessions
# end mid-turn. Passes when no "program was not released" error appears and the router's program
# count returns to the sessions still alive. Env: TASK_CONFIG, KV_BYTES, GPU_MEM, TP, SITE (see run_arm.sh).
# An attempt whose engines never started (another job took the GPUs while we were loading) is retried;
# a trainer that dies inside two minutes failed on its config, and one whose rollouts all fail did so in the
# image (reward import, sandbox); neither is fixed by a retry, so either ends the smoke.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=${DOCKER_CONFIG:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig} KV_BYTES=${KV_BYTES:-64424509440}
export TASK_CONFIG=${TASK_CONFIG:-/h20/task_config_claude_code_docker.leaksmoke.yaml}
log() { echo "[$(date +%T)] $*"; }
busy() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}'; }
wait_free() { local w=0; while [ "$(busy)" -ne 0 ]; do [ $((w % 10)) -eq 0 ] && log "waiting: $(busy) GPUs in use by other jobs"; sleep 60; w=$((w+1)); done; }
name=leaksmoke-ta-${SITE:-h20}-$TAG; R=$H/runs/$name
for attempt in 1 2 3 4 5 6 7 8; do
  [ -d $R ] && mv $R $R-failed-$(date +%H%M)
  wait_free; sleep 30; wait_free
  log "smoke attempt $attempt ($name)"
  BATCH=8 N=4 CONCURRENCY=32 RAY_NUM_CPUS=320 ROLLOUT_MAX_S=2400 bash $H/run_arm.sh ta-native $name > /dev/null 2>&1
  grep -q '"sessions_done": [1-9]' $R/summary.txt 2>/dev/null && break
  t0=$(grep -oE 'START_EPOCH=[0-9]+' $R/command.txt | cut -d= -f2); t1=$(grep -oE 'END_EPOCH=[0-9]+' $R/command.txt | cut -d= -f2)
  if [ -n "$t0" ] && [ -n "$t1" ] && [ $((t1 - t0)) -lt 120 ] && grep -q 'Error executing job' $R/console.log 2>/dev/null; then
    log "trainer failed on its config after $((t1 - t0)) s: $(grep -oE '^[A-Za-z]*Error: .*' $R/console.log | tail -1 | cut -c1-200)"
    break
  fi
  if grep -q 'All rollouts failed' $R/console.log 2>/dev/null; then
    log "all rollouts failed: $(grep -oE '[A-Za-z._]*(Error|Exception): .*' $R/console.log | grep -v CancelledError | sort | uniq -c | sort -rn | head -1 | cut -c1-220)"
    break
  fi
  log "no sessions ran (GPUs taken during startup?); will retry"
  docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1
done
not_released=$(grep -rc 'program was not released' $R/ray/session_*/logs/worker-*.err 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
cancelled=$(grep -rhc 'turn(s) in flight; cancelled' $R/ray/session_*/logs/worker-*.err 2>/dev/null | awk '{s+=$1} END{print s+0}')
done_n=$(grep -oE '"sessions_done": [0-9]+' $R/summary.txt 2>/dev/null | grep -oE '[0-9]+$'); done_n=${done_n:-0}
echo "not_released=$not_released"; echo "cancelled_turns=$cancelled"; echo "sessions_done=$done_n"
grep "scheduler state changed" $R/dynamo/verl_dynamo_replica0_frontend.log 2>/dev/null | tail -1 | grep -oE "programs=.*"
if [ "$done_n" -gt 0 ] && [ "$not_released" -eq 0 ]; then echo "LEAK_SMOKE_PASS"; else echo "LEAK_SMOKE_FAIL"; fi
echo "LEAK_SMOKE_DONE"
