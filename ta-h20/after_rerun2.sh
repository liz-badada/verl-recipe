#!/bin/bash
# after_rerun2.sh <after-rerun-tag>: once after_rerun.sh has logged AFTER_RERUN DONE, re-measure CC 64 and 128
# (both arms) with the same 32x16=512 trajectories as the other points. The 128- / 256-trajectory runs
# lasted 20 / 50 min and left one 10-min bucket for the CC 64 steady value.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
log() { echo "[$(date +%T)] $*"; }
until grep -q 'AFTER_RERUN DONE' $H/runs/after_rerun-$TAG.log; do sleep 300; done
log "recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
CCS="64 128" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_RERUN2 DONE"
