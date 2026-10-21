#!/bin/bash
# after_v029f.sh [tag]: vLLM 0.29 curve re-ordered on 2026-10-21 17:56 because the colleague's open question is the CC 2048
# point (native vLLM back level with TA on H100): 2048 and 1024 first (32 x 64 and 32 x 32 sessions, one wave each, so the
# nominal concurrency is real; 192 CPUs on this node, the sandboxes, not the engines, set the ceiling), then the remaining
# 256 / 128 / 64 / 384 pairs at 512 trajectories per arm, then the #16885 SGLang 384 re-run. Smokes and the 512 pair are done
# under the same tag and are skipped by sweep_cc.sh. The partial TA 256 run is parked.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-10211100}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
d=$H/runs/ta-native-h20v29cc256-$TAG; [ -d $d ] && [ ! -f $d/summary.txt ] && mv $d $d-aborted-$(date +%H%M) && log "parked the partial TA 256 run"
export STACK=verl010 SITE=h20v29 ENGINE=vllm IMAGE=verl-recipe-thunderagent:vllm029-uniagent-20261020 KV_BYTES=64424509440 UNIAGENT=$H/uni-agent-7ea3874
log "vLLM 0.29 stack on uni-agent $(git -C $UNIAGENT rev-parse --short HEAD); 2048 / 1024 first"
CCS="2048" ARMS="ta-native global" N_OVERRIDE=64 bash $H/sweep_cc.sh $TAG
CCS="1024" ARMS="ta-native global" N_OVERRIDE=32 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE (1024/2048)"; echo "AFTER_V029_HIGH DONE"
CCS="256 128 64 384" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE (64-512)"; echo "AFTER_V029 DONE"
unset STACK UNIAGENT
ENGINE=sglang SITE=h20sgfx IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b-pr16885 CCS="384" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh 10201700
log "PR16885 SGLANG 384 DONE"; echo "AFTER_PR16885 DONE"
