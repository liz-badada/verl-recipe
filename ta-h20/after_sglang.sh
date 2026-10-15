#!/bin/bash
# after_sglang.sh <after-384-tag> <new-tag>: as soon as after_384.sh has finished the CC 64 / 128 arms, take the GPUs
# for the SGLang pass (its remaining arms are confirmations of existing points and wait on the same GPU check):
# leak smoke on the SGLang image first, then both arms at CC 256 with the sweep's 32x16=512 trajectories.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; PREV=$1; TAG=$2
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261015
log() { echo "[$(date +%T)] $*"; }
until docker image inspect $IMAGE >/dev/null 2>&1; do sleep 120; done; log "image $IMAGE present"
until grep -q 'CC64_128 DONE' $H/runs/after_384-$PREV.log; do sleep 10; done
log "recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD) engine=$ENGINE"
bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG.log | grep -q LEAK_SMOKE_PASS || { log "SGLANG SMOKE FAILED; arms not run"; exit 5; }
sleep 90
CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_SGLANG DONE"
