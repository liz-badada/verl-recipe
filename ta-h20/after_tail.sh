#!/bin/bash
# after_tail.sh <after-384-tag> <new-tag>: once after_384.sh is through (TA 512, forced-subagent TA 256), re-measure the
# ThunderAgent CC 64 arm (its 10150700 run shared GPUs 0-3 with a foreign job from minute 27 on), then run the SGLang
# pass that after_sglang.sh could not (FSDP actor now loads with SDPA): leak smoke, then both arms at CC 256.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; PREV=$1; TAG=$2
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
until grep -q 'AFTER_384 DONE' $H/runs/after_384-$PREV.log; do sleep 60; done
log "after_384 done; recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
sleep 90
CCS="64" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "CC64 TA RERUN DONE"
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261015
sleep 90
bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG.log | grep -q LEAK_SMOKE_PASS || { log "SGLANG SMOKE FAILED; arms not run"; exit 5; }
sleep 90
CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_TAIL DONE"
