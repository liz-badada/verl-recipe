#!/bin/bash
# Sweep 2: once the baseline sweep's global arm has finished, stop the baseline run (its kv arm is
# dropped for GPU time) and run the three arms again at real CC=256 with the subagent prompt.
H=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20; export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
first=$(ls -t $H/runs/run_all-h20-*.log | head -1)
until grep -q -E 'arm global done|ALL DONE' "$first"; do sleep 30; done
sleep 5
for p in $(pgrep -f 'run_all.sh h20-'); do kill $p 2>/dev/null; done
for p in $(pgrep -f 'run_arm.sh kv kv-h20-'); do kill $p 2>/dev/null; done
sleep 5
docker ps -q --filter name=kv-h20- --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1
for i in $(seq 1 40); do [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>2000{c++} END{print c+0}')" -eq 0 ] && break; sleep 15; done
sleep 60
TAG=h20sub-$(date +%m%d%H%M)
SKIP_SMOKE=1 CONCURRENCY=256 RAY_NUM_CPUS=320 KV_BYTES=64424509440 TP=4 TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml \
  bash $H/run_all.sh $TAG > $H/runs/run_all-$TAG.log 2>&1
