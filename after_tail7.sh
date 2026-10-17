#!/bin/bash
# after_tail7.sh <tag>: replaces the tail of after_tail6.sh. Its SGLang smoke never got an engine up: run_arm.sh
# passed ulysses_sequence_parallel_size=4 next to use_remove_padding=false for sglang, verl refused the config
# in 14 s eight times, and leak_smoke.sh read that as "GPUs taken". With SP=1 for sglang: smoke, SGLang CC 256
# pair, then the TA CC 512 re-run that after_tail6 was still waiting on.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261015
if bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG-2.log | grep -q LEAK_SMOKE_PASS; then
  sleep 90
  CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
  log "SGLANG DONE"
else
  log "SGLANG SMOKE FAILED; sglang arms not run"
fi
unset ENGINE SITE IMAGE
sleep 90
CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_TAIL7 DONE"
