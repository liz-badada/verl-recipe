#!/bin/bash
# after_tail3.sh <after-384-tag> <new-tag>: replaces after_tail2.sh with the subagent ablation first. After
# after_384.sh is through: TA with identity ignored and TA with a program per agent but no parent (forced-subagent
# prompt, CC 256; the full-tree TA and global points exist), then the ThunderAgent CC 64 re-run, then the SGLang
# smoke + CC 256 pair, then a second TA CC 512 re-run (the 10150700 one shared the GPUs for 20 min).
# The ablation arms mount the recipe worktree that carries the subagent_programs knob (default tree = same code path).
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; PREV=$1; TAG=$2
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
until grep -q 'AFTER_384 DONE' $H/runs/after_384-$PREV.log; do sleep 60; done
log "after_384 done; recipe $(git -C ${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe} rev-parse --short HEAD)"
sleep 90
export RECIPE=$H/recipe-ablation TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml
log "ablation recipe $(git -C $RECIPE rev-parse --short HEAD)"
SUBAGENT_PROGRAMS=off      SITE=h20suboff      CCS="256" ARMS="ta-native" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
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
log "AFTER_TAIL3 DONE"
