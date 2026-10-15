#!/bin/bash
# after_384.sh <sweep-tag> <new-tag>: once the running global 384 arm has written its summary, re-measure CC 64 and
# 128 (both arms, 32x16=512 trajectories like every other point) FIRST, then the remaining global 512 arm, then
# the two headline ThunderAgent arms on the current recipe revision (33fac10). Replaces the tail of rerun_ta.sh
# plus after_rerun.sh / after_rerun2.sh, whose order left CC 64 / 128 for last.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; PREV=$1; TAG=$2
log() { echo "[$(date +%T)] $*"; }
S=$H/runs/global-h20cc384-$PREV/summary.txt
until grep -q '"sessions_done": [0-9]' $S 2>/dev/null; do sleep 120; done
log "global 384 ($PREV) finished: $(grep -E 'sessions_done|wall_s|model_tokens_per_s' $S | tr -d ' \n')"
sleep 120
log "recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
CCS="64 128" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "CC64_128 DONE"
CCS="512" ARMS="global" N_OVERRIDE=16 bash $H/sweep_cc.sh $PREV
CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
SITE=h20sub TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml CCS="256" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_384 DONE"
