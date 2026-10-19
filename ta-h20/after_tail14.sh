#!/bin/bash
# after_tail14.sh <tag>: the whole SGLang sweep again with the KV pool matched to the vLLM arms (2,621,440 tokens per
# engine via --max-total-tokens / engine_kwargs.sglang.max_total_tokens) and the global arm's chunked_prefill_size,
# page_size and context_length aligned to the TA arm. Ascending CC, TA then global at each CC, 512 trajectories per
# arm. Replaces the 10160955 sglang runs (mem_fraction_static 0.78 alone = ~3.76M tokens, ~87 GiB/GPU), which stay
# as raw data only.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=$1
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
log() { echo "[$(date +%T)] $*"; }
export ENGINE=sglang SITE=h20sg IMAGE=verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b
CCS="64 128 256 384 512" ARMS="ta-native global" N_OVERRIDE=16 bash $H/sweep_cc.sh $TAG
log "SGLANG SWEEP DONE"
log "AFTER_TAIL14 DONE"
