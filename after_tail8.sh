#!/bin/bash
# after_tail8.sh <tag>: third SGLang attempt. after_tail7's smoke passed config validation and then failed in the
# recipe's etcd spawn: the sglang base image ships neither etcd nor nats-server (the vLLM bench image inherits
# both). Image rust-ta-uniagent-sglang-20261018 adds them. Waits for after_tail7's TA CC 512 re-run, then the
# SGLang smoke and the SGLang CC 256 pair.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
until grep -q 'AFTER_TAIL7 DONE' $H/runs/after_tail7-$TAG.log 2>/dev/null; do sleep 60; done
log "after_tail7 done (TA CC 512 re-run finished)"
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018
sleep 90
if bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG-3.log | grep -q LEAK_SMOKE_PASS; then
  sleep 90
  CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
  log "SGLANG DONE"
else
  log "SGLANG SMOKE FAILED; sglang arms not run"
fi
log "AFTER_TAIL8 DONE"
