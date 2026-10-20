#!/bin/bash
# after_v029b.sh [tag]: once the PR #16885 TA arms (after_pr16885) have finished, smoke-test the vLLM 0.29 stack
# (STACK=verl010: verlai/verl uv.cu130.dev4, recipe b85e1b7, Uni-Agent 4f3cd34) with one tiny TA arm and one tiny
# global arm, then run the full concurrency sweep on it (TA then global at 64 / 128 / 256 / 384 / 512, 512 trajectories
# per arm, KV cap 60 GiB per GPU as on the vLLM 0.24 sweep). Stops before the sweep if either smoke produces no session.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
export STACK=verl010 SITE=h20v29 ENGINE=vllm IMAGE=verl-recipe-thunderagent:vllm029-uniagent-20261020 KV_BYTES=64424509440
log() { echo "[$(date +%T)] $*"; }
until grep -qE 'AFTER_PR16885 (DONE|ABORT)' $H/runs/after_pr16885-10201700.log 2>/dev/null; do sleep 300; done
log "pr16885 arms finished; vLLM 0.29 stack smoke (run_arm quotes VERL_USE_EXTERNAL_MODULES now)"
docker image inspect $IMAGE >/dev/null 2>&1 || { log "image $IMAGE missing; abort"; echo "AFTER_V029 ABORT"; exit 1; }
for arm in ta-native global; do
  name=smoke-$arm-h20v29-$TAG
  BATCH=4 N=2 CONCURRENCY=8 RAY_NUM_CPUS=320 ROLLOUT_MAX_S=2400 bash $H/run_arm.sh $arm $name > /dev/null 2>&1
  log "smoke $arm: $(grep -E 'sessions_done|finished_trajectories' $H/runs/$name/summary.txt 2>/dev/null | tr -d ' \n')"
  grep -q '"sessions_done": [1-9]' $H/runs/$name/summary.txt 2>/dev/null || { log "smoke $arm produced no sessions; abort"; echo "AFTER_V029 ABORT"; exit 1; }
  docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; sleep 60
done
log "smokes passed; vLLM 0.29 sweep"
CCS="64 128 256 384 512" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "V029 SWEEP DONE"; echo "AFTER_V029 DONE"
