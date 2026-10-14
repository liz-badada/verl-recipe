#!/bin/bash
# rerun_ta.sh [tag]: re-measure every ThunderAgent arm after the gateway close fix (recipe 9f32e49),
# plus every global arm again, so all published points come from one recipe revision and one methodology.
# Order: the blog-regime points first. Each arm waits for free GPUs and retries a failed engine start.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
log() { echo "[$(date +%T)] $*"; }
log "recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
CCS="512 256 384" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
CCS="128 64" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
# sweep 2 regime: 256 concurrency, prompt forcing three subagents
SITE=h20sub TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml CCS="256" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
# global baselines last: the fix does not touch their path, these re-measure them on the same revision
CCS="256 384 512" ARMS="global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "RERUN DONE"
