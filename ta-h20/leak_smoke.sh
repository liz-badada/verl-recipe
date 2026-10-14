#!/bin/bash
# leak_smoke.sh: ThunderAgent arm at small scale with a 4-minute Claude Code timeout, so most sessions
# end mid-turn. Passes when no "program was not released" error appears and the router's program
# count returns to the sessions still alive.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig KV_BYTES=${KV_BYTES:-64424509440}
busy() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}'; }
while [ "$(busy)" -ne 0 ]; do echo "[$(date +%T)] waiting: $(busy) GPUs in use"; sleep 120; done
name=leaksmoke-ta-$TAG
BATCH=8 N=4 CONCURRENCY=32 RAY_NUM_CPUS=320 ROLLOUT_MAX_S=2400 TASK_CONFIG=/h20/task_config_claude_code_docker.leaksmoke.yaml bash $H/run_arm.sh ta-native $name > /dev/null 2>&1
R=$H/runs/$name
echo "not_released=$(grep -rc 'program was not released' $R/ray/session_*/logs/worker-*.err 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')"
echo "cancelled_turns=$(grep -rhc 'turn(s) in flight; cancelled' $R/ray/session_*/logs/worker-*.err 2>/dev/null | awk '{s+=$1} END{print s+0}')"
grep "scheduler state changed" $R/dynamo/verl_dynamo_replica0_frontend.log | tail -1 | grep -oE "programs=.*"
grep -E '"(sessions_done|finished_trajectories)"' $R/summary.txt | tr -d ' \n'; echo
echo "LEAK_SMOKE_DONE"
