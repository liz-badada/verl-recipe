#!/bin/bash
# after_v029e.sh [tag]: top-priority vLLM 0.29 curve on the merged uni-agent main (7ea3874, PR #270 squashed in): two
# smokes, then TA and global at 512 / 256 / 128 / 64 / 384 (signal-bearing CCs first), 512 trajectories per arm, KV cap
# 60 GiB per GPU, then 1024 and 2048 to match the colleague's H100 curve. Afterwards the #16885 SGLang CC 384 arm that was stopped to make room is re-run under its own tag.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
d=$H/runs/ta-native-h20sgfxcc384-10201700; [ -d $d ] && [ ! -f $d/summary.txt ] && mv $d $d-aborted-$(date +%H%M) && log "parked the partial sgfx 384 run"
export STACK=verl010 SITE=h20v29 ENGINE=vllm IMAGE=verl-recipe-thunderagent:vllm029-uniagent-20261020 KV_BYTES=64424509440 UNIAGENT=$H/uni-agent-7ea3874
log "vLLM 0.29 stack on uni-agent $(git -C $UNIAGENT rev-parse --short HEAD); smokes"
for arm in ta-native global; do
  name=smoke-$arm-h20v29-$TAG
  BATCH=4 N=2 CONCURRENCY=8 RAY_NUM_CPUS=320 ROLLOUT_MAX_S=2400 bash $H/run_arm.sh $arm $name > /dev/null 2>&1
  log "smoke $arm: $(grep -E 'sessions_done|finished_trajectories' $H/runs/$name/summary.txt 2>/dev/null | tr -d ' \n')"
  grep -q '"sessions_done": [1-9]' $H/runs/$name/summary.txt 2>/dev/null || { log "smoke $arm produced no sessions; abort"; echo "AFTER_V029 ABORT"; exit 1; }
  docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; sleep 60
done
log "smokes passed; vLLM 0.29 sweep"
CCS="512 256 128 64 384" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE (64-512)"; echo "AFTER_V029 DONE"
# The colleague's H100 curve also has 1024 and 2048; attempted here with 32 x 32 and 32 x 64 sessions so the concurrency is real
# (192 CPUs on this node: the sandboxes, not the engines, will set the ceiling; a failed start is retried by sweep_cc, a 3 h cap applies).
CCS="1024" ARMS="ta-native global" N_OVERRIDE=32 bash $H/sweep_cc.sh $TAG
CCS="2048" ARMS="ta-native global" N_OVERRIDE=64 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE (1024/2048)"; echo "AFTER_V029_HIGH DONE"
unset STACK UNIAGENT
ENGINE=sglang SITE=h20sgfx IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b-pr16885 CCS="384" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh 10201700
log "PR16885 SGLANG 384 DONE"; echo "AFTER_PR16885 DONE"
