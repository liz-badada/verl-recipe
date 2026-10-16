#!/bin/bash
# after_tail6.sh <tag>: replaces after_tail5.sh after its first arm. The off arm at CC 256 reproduced the upstream
# serial-call guard (411 x HTTP 409 in 210/512 sessions), so off at CC 512 is dropped: it would only repeat that.
# Once the running tree CC 512 arm is done: isolated at CC 256, then the TA CC 64 re-run, SGLang smoke + CC 256
# pair, TA CC 512 again.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
until grep -q 'arm ta-native cc=512 done' $H/runs/after_tail5-$TAG.log && ! pgrep -f "sweep_cc.sh $TAG" >/dev/null; do sleep 60; done
log "tree arm (CC 512) done"
export RECIPE=$H/recipe-ablation TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml
log "ablation recipe $(git -C $RECIPE rev-parse --short HEAD)"
sleep 90
SUBAGENT_PROGRAMS=isolated SITE=h20subisolated CCS="256" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "ABLATION DONE"
unset RECIPE TASK_CONFIG
sleep 90
CCS="64" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "CC64 TA RERUN DONE"
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261015
sleep 90
if bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$SITE-$TAG.log | grep -q LEAK_SMOKE_PASS; then
  sleep 90
  CCS="256" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
  log "SGLANG DONE"
else
  log "SGLANG SMOKE FAILED; sglang arms not run"
fi
unset ENGINE SITE IMAGE
sleep 90
CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "AFTER_TAIL6 DONE"
