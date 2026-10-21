#!/bin/bash
# after_v029g.sh [tag]: remainder of the vLLM 0.29 curve after CC 2048 proved infeasible on this one 192-core node
# (2026-10-21 21:54: 585 sandboxes in the first 10 min drove the load average to 1600 and RSS to 1.1 TB of 2 TB, the engines
# fell from 779 to ~150 tok/s and all 64 ray tasks died at 65 min; 1024 would need ~1.9 TB for its sandboxes and is skipped
# for the same reason). Runs global 256 again (the first try lost its wave-2 sandboxes at the old 7200 s runtime_timeout),
# then the 128 / 64 / 384 pairs, then the #16885 SGLang 384 arm. Arms with a summary are skipped by sweep_cc.sh.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-10211100}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
for d in $H/runs/*h20v29cc2048-$TAG $H/runs/*h20v29cc1024-$TAG; do [ -d $d ] && [ ! -f $d/summary.txt ] && mv $d $d-aborted-$(date +%H%M) && log "parked $(basename $d)"; done
export STACK=verl010 SITE=h20v29 ENGINE=vllm IMAGE=verl-recipe-thunderagent:vllm029-uniagent-20261020 KV_BYTES=64424509440 UNIAGENT=$H/uni-agent-7ea3874
log "vLLM 0.29 stack on uni-agent $(git -C $UNIAGENT rev-parse --short HEAD); remaining pairs"
CCS="256 128 64 384" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE (64-512)"; echo "AFTER_V029 DONE"
unset STACK UNIAGENT
ENGINE=sglang SITE=h20sgfx IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b-pr16885 CCS="384" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh 10201700
log "PR16885 SGLANG 384 DONE"; echo "AFTER_PR16885 DONE"
