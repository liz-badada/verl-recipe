#!/bin/bash
# after_tail9.sh <tag>: fourth SGLang attempt. after_tail8's smoke brought the engines up and died in the first
# weight sync: HTTP 413 from the dynamo worker's system server (2 MiB body limit) because the recipe posts each
# 2048 MiB bucket's CUDA-IPC handles TP times over, every parameter carrying all TP ranks' handles. The bench now
# syncs in 256 MiB buckets (run_arm.sh). SGLang smoke, then the SGLang CC 256 pair.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018
if bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG-4.log | grep -q LEAK_SMOKE_PASS; then
  sleep 90
  CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
  log "SGLANG DONE"
else
  log "SGLANG SMOKE FAILED; sglang arms not run"
fi
log "AFTER_TAIL9 DONE"
