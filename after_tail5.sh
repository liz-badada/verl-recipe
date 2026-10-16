#!/bin/bash
# after_tail5.sh <tag>: replaces after_tail4.sh. The question is whether TA that knows about subagents differs
# enough from TA that does not. Once the running off arm (CC 256) is done: the heavy regime first, forced-subagent
# CC 512 with tree then off (under-counted load should bite here), then isolated at CC 256, then the TA CC 64
# re-run (user has an earlier copy, not urgent), SGLang smoke + CC 256 pair, TA CC 512 again.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
until grep -q 'arm ta-native cc=256 done' $H/runs/after_tail3-$TAG.log && ! pgrep -f "sweep_cc.sh $TAG" >/dev/null; do sleep 60; done
log "off arm (CC 256) done"
export RECIPE=$H/recipe-ablation TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml
log "ablation recipe $(git -C $RECIPE rev-parse --short HEAD)"
sleep 90
SUBAGENT_PROGRAMS=tree SITE=h20sub    CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "TREE 512 DONE"
sleep 90
SUBAGENT_PROGRAMS=off  SITE=h20suboff CCS="512" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "OFF 512 DONE"
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
log "AFTER_TAIL5 DONE"
