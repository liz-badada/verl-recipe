#!/bin/bash
# after_tail11.sh <tag>: re-run of the SGLang global CC 256 arm with scheduler stats. The first run
# (global-h20sgcc256-<tag>-nostats) completed 508/512 sessions but verl's native sglang server logs at
# log_level=error, so it left no engine throughput lines; run_arm.sh now passes log_level=info for sglang global.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b
CCS="256" ARMS="global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "SGLANG GLOBAL RERUN DONE"
log "AFTER_TAIL11 DONE"
