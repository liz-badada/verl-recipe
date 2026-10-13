#!/bin/bash
# stat_local.sh: progress of the newest arm/smoke run on this node
H=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20; export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
cd $H/runs; d=$(docker ps --format "{{.Names}}" | grep -E "^(smoke-ta|ta-native|kv|global)-h20" | head -1); [ -n "$d" ] || d=$(ls -dt smoke-ta-h20* ta-native-h20* kv-h20* global-h20* 2>/dev/null | head -1); cd $d; echo "== $d $(date +%T)"
echo "sessions: $(ls -d agent_logs/step_1/session-* 2>/dev/null | wc -l) created, $(ls agent_logs/step_1/*/trajectory.json 2>/dev/null | wc -l) done; claude finished: $(grep -l 'claude finished' agent_logs/step_1/*/task.log 2>/dev/null | wc -l); sandboxes: $(docker ps -q --filter name=uni-agent- | wc -l)"
echo "errors: NO-TOKEN-IDS=$(grep -c 'NO TOKEN IDS' console.log) gw4xx5xx=$(grep -c -E 'status_code=(4|5)[0-9][0-9]' console.log) sandbox-fail=$(grep -h -c 'sandbox failed to start' agent_logs/step_1/*/task.log 2>/dev/null | awk '{s+=$1} END{print s+0}') RuntimeError=$(grep -c 'RuntimeError' console.log)"
fe=dynamo/verl_dynamo_replica0_frontend.log; [ -f $fe ] && echo "frontend: ok=$(grep -c 'outcome=\"success\"' $fe) rejected=$(grep -c 'outcome=\"rejected\"' $fe) err=$(grep -c -E 'status=(4|5)[0-9][0-9]' $fe) $(grep -i -E 'WARN.*thunderagent|forcibly' $fe | tail -1 | cut -c1-120)"
echo "gpu util,mem: $(tail -8 gpu.csv | cut -d, -f3,4 | tr '\n' ' ')"
grep -E 'Training Progress|generate_sequences summary' console.log | tail -1 | cut -c1-160
tail -2 $(ls -t $H/runs/run_all-h20*.log | head -1)
