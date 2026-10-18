#!/bin/bash
# after_tail10.sh <tag>: fifth SGLang attempt. after_tail9's smoke passed weight sync and ran sessions, but every
# rollout failed at reward time: the sglang image had resolved the unpinned swebench to 5.0.2, which dropped
# MAP_REPO_VERSION_TO_SPECS that Uni-Agent's SWE-bench reward imports. Image 20261018b pins 4.1.0 (the vLLM
# image's version). SGLang smoke, then the SGLang CC 256 pair.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b
if bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG-5.log | grep -q LEAK_SMOKE_PASS; then
  sleep 90
  CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
  log "SGLANG DONE"
else
  log "SGLANG SMOKE FAILED; sglang arms not run"
fi
log "AFTER_TAIL10 DONE"
