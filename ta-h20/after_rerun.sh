#!/bin/bash
# after_rerun.sh <rerun-tag> <new-tag>: once rerun_ta.sh has logged RERUN DONE, re-measure the two headline
# ThunderAgent arms on the current recipe revision (33fac10 defers program releases during an engine pause).
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; PREV=$1; TAG=$2
log() { echo "[$(date +%T)] $*"; }
until grep -q 'RERUN DONE' $H/runs/smoke_then_rerun-$PREV.log; do sleep 300; done
log "recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
SITE=h20sub TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml CCS="256" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_RERUN DONE"
