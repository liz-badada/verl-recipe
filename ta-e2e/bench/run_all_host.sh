#!/bin/bash
# One container per variant: complete process isolation between runs.
E=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-e2e
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
for v in ${VARIANTS:-ta-subagent ta-main kv-router round-robin}; do
  timeout 1500 docker run --rm \
    -v /home/jinyanc/workspace/jinyanc/github/dynamo/components/src:/src \
    -v /home/jinyanc/workspace/jinyanc/github/dynamo-main-wt/components/src:/src-main \
    -v $E:/e2e -e HF_HOME=/e2e/hf -e HOME=/tmp \
    -e SESSIONS=${SESSIONS:-48} -e SUBAGENTS=${SUBAGENTS:-3} -e TURNS=${TURNS:-3} -e CONC=${CONC:-12} -e BLOCKS=${BLOCKS:-2048} -e REQ_TIMEOUT=${REQ_TIMEOUT:-60} \
    dynamo-nightly-ci:20261009 bash /e2e/bench/run_variant.sh $v 2>&1 | grep "^\[$v"
done
echo "ALL VARIANTS DONE"
